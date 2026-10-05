#!/usr/bin/env node
/**
 * Live beat latency measurement.
 *
 * Creates a fresh watcher story (Wren and Ash share the Hearth, so every
 * beat exercises decide -> react -> resolve -> narrate), advances --beats
 * beats against the running API, and records for each beat:
 *   - wall time seen by the client,
 *   - the per-stage breakdown from X-Worldsim-Phase-Timings,
 *   - every model call from /stage1/model-runs (role, latency, tokens,
 *     reasoning tokens, finish reason, errors),
 *   - estimated spend from OpenRouter's public per-token prices.
 *
 * Spends real provider credit when the API runs a live profile; the
 * --max-usd guard stops between beats once the estimate passes it.
 * Results go to --out/<label>.json; existing files are never overwritten.
 *
 * Usage:
 *   EMBER_VALE_API_KEY=<operator key> node scripts/beat-latency.mjs \
 *     --label baseline --beats 3 --model deepseek/deepseek-v4-flash-0731 \
 *     [--out docs/evidence/beat-latency-001] [--max-usd 0.15]
 */

import { execSync } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'

const args = process.argv.slice(2)
const opt = (name, fallback) => {
  const i = args.indexOf(name)
  return i >= 0 && args[i + 1] ? args[i + 1] : fallback
}

const API = opt('--api', 'http://localhost:8101/api/v1')
const LABEL = opt('--label', 'run')
const BEATS = Number(opt('--beats', '3'))
const MODEL = opt('--model', '')
const OUT = opt('--out', 'docs/evidence/beat-latency-001')
const MAX_USD = Number(opt('--max-usd', '0.15'))
const KEY = process.env.EMBER_VALE_API_KEY || process.env.WORLDSIM_SECURITY__API_KEY || ''
if (!KEY) throw new Error('set EMBER_VALE_API_KEY (the compose operator key)')
if (!MODEL) throw new Error('pass --model (the OpenRouter model id the API runs)')

const outFile = path.join(OUT, `${LABEL}.json`)
if (fs.existsSync(outFile)) throw new Error(`${outFile} exists; evidence is never overwritten`)

const COMMIT = execSync('git rev-parse --short HEAD', { stdio: 'pipe' }).toString().trim()
const RUN = Date.now().toString(36)
const headers = () => ({
  'Content-Type': 'application/json',
  Authorization: `Bearer ${KEY}`,
  'X-Worldsim-Role': 'watcher'
})

async function raw(method, route, body) {
  const res = await fetch(API + route, {
    method,
    headers: headers(),
    body: body === undefined ? undefined : JSON.stringify(body)
  })
  const text = await res.text()
  if (!res.ok) throw new Error(`${method} ${route} -> ${res.status}: ${text.slice(0, 300)}`)
  return { res, json: text ? JSON.parse(text) : null }
}
const call = async (method, route, body) => (await raw(method, route, body)).json

async function prices(model) {
  const res = await fetch('https://openrouter.ai/api/v1/models')
  const entry = (await res.json()).data.find((m) => m.id === model)
  if (!entry) throw new Error(`no public pricing for ${model}`)
  return { prompt: Number(entry.pricing.prompt), completion: Number(entry.pricing.completion) }
}

async function makeStory() {
  const worlds = await call('GET', '/library/presets?kind=world')
  const vale = worlds.find((p) => p.name === 'Ember Vale')
  const chars = await call('GET', '/library/presets?kind=character')
  const cast = ['Wren', 'Ash'].map((name) => {
    const preset = chars.find((p) => p.name === name)
    return {
      instance_key: name.toLowerCase(),
      preset_id: preset.id,
      preset_revision: preset.current_revision,
      name,
      location_key: 'hearth'
    }
  })
  const draft = await call('POST', '/story-drafts', {
    payload: {
      world: { preset_id: vale.id, preset_revision: vale.current_revision },
      cast,
      mode: { role: 'watcher' },
      story: { title: `Latency ${LABEL} ${RUN}` },
      ai: { art_source: 'curated' }
    },
    current_step: 'review'
  })
  const res = await fetch(API + '/stories', {
    method: 'POST',
    headers: { ...headers(), 'Idempotency-Key': `latency-${LABEL}-${RUN}` },
    body: JSON.stringify({ draft_id: draft.id, expected_draft_version: 1 })
  })
  if (!res.ok) throw new Error(`create story -> ${res.status}: ${await res.text()}`)
  return (await res.json()).world_id
}

function summarize(calls, price) {
  const byRole = {}
  let usd = 0
  for (const c of calls) {
    const r = (byRole[c.role] ??= {
      calls: 0,
      failed: 0,
      latency_ms_sum: 0,
      latency_ms_max: 0,
      prompt_tokens: 0,
      completion_tokens: 0,
      reasoning_tokens: 0,
      finish: {}
    })
    r.calls += 1
    if (c.status !== 'succeeded') r.failed += 1
    r.latency_ms_sum += c.latency_ms
    r.latency_ms_max = Math.max(r.latency_ms_max, c.latency_ms)
    r.prompt_tokens += c.prompt_tokens
    r.completion_tokens += c.completion_tokens
    r.reasoning_tokens += c.reasoning_tokens ?? 0
    const reason = c.finish_reason ?? c.error_code ?? 'unknown'
    r.finish[reason] = (r.finish[reason] ?? 0) + 1
    usd += c.prompt_tokens * price.prompt + c.completion_tokens * price.completion
  }
  return { byRole, usd }
}

const price = await prices(MODEL)
const worldId = await makeStory()
const detail = await call('GET', `/stories/${worldId}`)
console.log(`story ${worldId} at index ${detail.absolute_index}; model ${MODEL}`)

const beats = []
let spent = 0
let index = detail.absolute_index
for (let n = 1; n <= BEATS; n += 1) {
  if (spent >= MAX_USD) {
    console.log(`stopping: estimated spend $${spent.toFixed(4)} reached --max-usd ${MAX_USD}`)
    break
  }
  index += 1
  const started = performance.now()
  let report
  let res
  try {
    ;({ res, json: report } = await raw('POST', '/stage1/advance', {
      world_id: worldId,
      absolute_index: index
    }))
  } catch (error) {
    beats.push({ beat: n, absolute_index: index, error: String(error).slice(0, 500) })
    console.log(`beat ${n}: FAILED ${String(error).slice(0, 200)}`)
    break
  }
  const wallMs = Math.round(performance.now() - started)
  const timings = JSON.parse(res.headers.get('x-worldsim-phase-timings') || '{}')
  const calls = await call('GET', `/stage1/model-runs?phase_run_id=${report.run_id}`)
  const { byRole, usd } = summarize(calls, price)
  spent += usd
  beats.push({
    beat: n,
    absolute_index: index,
    wall_ms: wallMs,
    execution_ms: Number(res.headers.get('x-worldsim-execution-ms')),
    timings_ms: timings,
    scenes: report.scenes.length,
    quiet: report.quiet,
    narrated_scenes: report.scenes.filter((s) => s.narration).length,
    est_usd: Number(usd.toFixed(6)),
    roles: byRole,
    calls: calls.map((c) => ({
      role: c.role,
      status: c.status,
      latency_ms: c.latency_ms,
      prompt_tokens: c.prompt_tokens,
      completion_tokens: c.completion_tokens,
      reasoning_tokens: c.reasoning_tokens,
      max_tokens: c.max_tokens,
      finish_reason: c.finish_reason,
      error_code: c.error_code
    }))
  })
  const stages = Object.entries(timings)
    .map(([k, v]) => `${k}=${(v / 1000).toFixed(1)}s`)
    .join(' ')
  console.log(
    `beat ${n}: ${(wallMs / 1000).toFixed(1)}s, ${calls.length} calls, ~$${usd.toFixed(4)} | ${stages}`
  )
}

fs.mkdirSync(OUT, { recursive: true })
fs.writeFileSync(
  outFile,
  JSON.stringify(
    {
      label: LABEL,
      commit: COMMIT,
      at: new Date().toISOString(),
      model: MODEL,
      price_per_token_usd: price,
      world_id: worldId,
      est_usd_total: Number(spent.toFixed(6)),
      beats
    },
    null,
    2
  ) + '\n'
)
console.log(`wrote ${outFile}; estimated spend $${spent.toFixed(4)}`)
