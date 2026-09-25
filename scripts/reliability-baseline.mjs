#!/usr/bin/env node
/**
 * Reliability and beat-latency baseline (REL-BASE-001).
 *
 * Fixed small scenario against the real API, no prompt/model/budget/retry
 * changes: story setup -> travel beat -> question beat -> follow-up beat ->
 * ordinary advance -> reload reads. An optional browser pass measures
 * display latency in the real room.
 *
 * Outcome layers stay separate: provider response, schema/rule validation,
 * committed action, narration fallback, and display. A successful provider
 * call never counts as a successful game response on its own.
 *
 * Timing splits per beat: client wall (submit -> response), server
 * admission vs execution (X-Worldsim-* headers), per-role generation from
 * the model-runs audit (each traced call already includes its retries),
 * and browser display (click/reload -> rendered). End-to-end wall is
 * recorded separately from summed call durations; summed durations
 * double-count the concurrent character calls, so both are reported.
 *
 * Usage:
 *   EMBER_VALE_API_KEY=<operator key> node scripts/reliability-baseline.mjs \
 *     [--api http://localhost:8101/api/v1] [--mode fake|live] \
 *     [--out docs/evidence/reliability-baseline-v1] [--title "Baseline"] \
 *     [--no-browser] [--base http://127.0.0.1:5173]
 *
 * --mode fake pins the story to a throwaway fake-echo provider profile, so
 * the run is deterministic. --mode live uses the normal environment
 * default (capped at four committed beats plus reads). Timeouts and failed
 * runs are retained in the report, never dropped.
 */

import fs from 'node:fs'
import path from 'node:path'
import { chromium } from 'playwright-core'

const args = process.argv.slice(2)
const opt = (name, fallback) => {
  const i = args.indexOf(name)
  return i >= 0 && args[i + 1] ? args[i + 1] : fallback
}

const API = opt('--api', 'http://localhost:8101/api/v1')
const MODE = opt('--mode', 'fake')
const OUT = opt('--out', 'docs/evidence/reliability-baseline-v1')
const TITLE = opt('--title', 'Reliability baseline')
const BASE = opt('--base', 'http://127.0.0.1:5173')
const WITH_BROWSER = !args.includes('--no-browser')
const KEY = process.env.EMBER_VALE_API_KEY || ''
if (!KEY) throw new Error('set EMBER_VALE_API_KEY (the compose operator key)')
if (!['fake', 'live'].includes(MODE)) throw new Error(`--mode must be fake|live (got ${MODE})`)

const RUN = Date.now().toString(36)
const EDGE = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe'
const NIL_SNAPSHOT = '00000000-0000-0000-0000-000000000000'
const BEAT_TIMEOUT_MS = 180000

fs.mkdirSync(OUT, { recursive: true })

const headers = (extra = {}) => ({
  'Content-Type': 'application/json',
  Authorization: `Bearer ${KEY}`,
  'X-Worldsim-Role': 'watcher',
  ...extra
})

async function call(method, reqPath, body, extraHeaders = {}, timeoutMs = BEAT_TIMEOUT_MS) {
  const started = performance.now()
  const res = await fetch(API + reqPath, {
    method,
    headers: headers(extraHeaders),
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: AbortSignal.timeout(timeoutMs)
  })
  const wallMs = Math.round(performance.now() - started)
  const text = await res.text()
  let json = null
  try {
    json = text ? JSON.parse(text) : null
  } catch {
    /* non-JSON error body */
  }
  return {
    status: res.status,
    ok: res.ok,
    json,
    errorBody: res.ok ? '' : text.slice(0, 300),
    wallMs,
    admissionMs: Number(res.headers.get('x-worldsim-admission-ms') ?? NaN),
    executionMs: Number(res.headers.get('x-worldsim-execution-ms') ?? NaN)
  }
}

const beats = []
const notes = []
const note = (text) => {
  notes.push(text)
  console.log(`note: ${text}`)
}

/** Classify one beat into the five outcome layers. Never throws. */
function classify(kind, advanceRes, modelRuns, timelineEntries, narrationBeats) {
  const layers = {
    provider: 'unknown',
    validation: 'unknown',
    committed: 'unknown',
    narration: 'unknown',
    display: 'unknown'
  }
  const reasons = []
  if (!advanceRes) {
    return { layers, reasons: ['no advance response recorded'], useful: false }
  }
  if (advanceRes.timeout) {
    layers.provider = 'unknown'
    layers.validation = 'unknown'
    layers.committed = 'unknown'
    return {
      layers,
      reasons: [`advance timed out after ${advanceRes.timeoutMs}ms (retained, not retried)`],
      useful: false
    }
  }
  if (!advanceRes.ok) {
    layers.validation = 'rejected'
    layers.committed = 'no'
    layers.provider = 'not-applicable'
    layers.narration = 'not-applicable'
    layers.display = 'no'
    reasons.push(`advance rejected: HTTP ${advanceRes.status} ${advanceRes.errorBody}`)
    return { layers, reasons, useful: false }
  }
  const body = advanceRes.json ?? {}
  layers.validation = 'pass'
  if (body.duplicate === true) reasons.push('duplicate replay (no new canon)')

  const terminal = (modelRuns ?? []).filter(
    (c) => c.status === 'succeeded' || c.status === 'failed'
  )
  const failed = (modelRuns ?? []).filter((c) => c.status === 'failed')
  const unfinished = (modelRuns ?? []).filter(
    (c) => c.status !== 'succeeded' && c.status !== 'failed'
  )
  if ((modelRuns ?? []).length === 0) {
    layers.provider = 'no-calls'
    reasons.push('no traced model calls for this phase')
  } else if (failed.length === 0 && unfinished.length === 0) {
    layers.provider = 'ok'
  } else if (terminal.length > 0 && failed.length > 0) {
    layers.provider = 'degraded'
    reasons.push(`provider degraded: ${failed.map((c) => `${c.role}:${c.error_code}`).join(', ')}`)
  } else {
    layers.provider = 'failed'
    reasons.push('no provider call reached a terminal state with success')
  }
  for (const c of unfinished) reasons.push(`call ${c.call_id} (${c.role}) left ${c.status}`)

  const scenes = body.scenes ?? []
  const committedEvents = scenes.filter((s) => s.event_id)
  layers.committed = committedEvents.length > 0 && body.duplicate !== true ? 'yes' : 'no'
  if (layers.committed === 'no') reasons.push('no committed events in the advance response')

  const kinds = new Set(scenes.map((s) => s.narration))
  if (kinds.size === 0) {
    layers.narration = 'none'
  } else if (kinds.has('failed')) {
    layers.narration = 'failed'
    reasons.push('at least one scene narration failed')
  } else if ([...kinds].every((k) => k === 'fallback' || k === 'skipped')) {
    layers.narration = 'fallback'
  } else {
    layers.narration = 'narrated'
  }

  const visibleIds = new Set((timelineEntries ?? []).map((e) => e.event_id))
  const retrievable = committedEvents.filter((s) => visibleIds.has(s.event_id))
  const beatTexts = (narrationBeats ?? []).filter((b) => (b.text ?? '').trim().length > 0)
  layers.display =
    layers.committed === 'yes' && retrievable.length > 0 && beatTexts.length > 0 ? 'yes' : 'no'
  if (layers.display === 'no')
    reasons.push(
      `display check: ${retrievable.length}/${committedEvents.length} events in timeline, ` +
        `${beatTexts.length} non-empty beats read back`
    )

  // A successful provider call is not a successful game response.
  const useful =
    layers.committed === 'yes' && layers.display === 'yes' && layers.narration !== 'failed'
  if (layers.provider === 'ok' && !useful)
    reasons.push('provider ok but beat is not useful: provider success did not carry the beat')
  return { layers, reasons, useful, kind }
}

async function providerSnapshot(storyId) {
  const res = await call('GET', `/stories/${storyId}/provider`)
  if (!res.ok) return { error: `HTTP ${res.status}: ${res.errorBody}` }
  const p = res.json
  return {
    pin_state: p.pin_state,
    pin_revision: p.pin?.revision ?? null,
    effective_source: p.effective_source,
    effective_adapter: p.effective_adapter,
    effective_model_id: p.effective_model_id,
    effective_revision: p.effective_revision
  }
}

async function modelRunsFor(runId) {
  const res = await call('GET', `/stage1/model-runs?phase_run_id=${runId}`)
  if (!res.ok) return { error: `HTTP ${res.status}: ${res.errorBody}`, calls: [] }
  const calls = (res.json ?? []).map((c) => ({
    call_id: c.call_id,
    role: c.role,
    profile: c.profile,
    status: c.status,
    actor_id: c.actor_id,
    task_run_id: c.task_run_id,
    prompt_tokens: c.prompt_tokens ?? 0,
    completion_tokens: c.completion_tokens ?? 0,
    latency_ms: c.latency_ms,
    error_code: c.error_code,
    max_tokens: c.max_tokens,
    pin_profile_id: c.pin_profile_id,
    pin_profile_revision: c.pin_profile_revision,
    budgets: c.budgets ?? {},
    attempts: c.attempts ?? []
  }))
  return { calls }
}

function summarizeCalls(calls) {
  const byRole = {}
  let prompt_tokens = 0
  let completion_tokens = 0
  let attempts = 0
  for (const c of calls) {
    byRole[c.role] = byRole[c.role] ?? { calls: 0, failed: 0, latency_ms: 0, attempts: 0 }
    byRole[c.role].calls += 1
    if (c.status === 'failed') byRole[c.role].failed += 1
    byRole[c.role].latency_ms += c.latency_ms ?? 0
    byRole[c.role].attempts += (c.attempts ?? []).length
    prompt_tokens += c.prompt_tokens ?? 0
    completion_tokens += c.completion_tokens ?? 0
    attempts += (c.attempts ?? []).length
  }
  return { byRole, prompt_tokens, completion_tokens, attempts }
}

async function currentIndex(worldId) {
  const res = await call('GET', `/stories/${worldId}`)
  if (!res.ok) throw new Error(`story detail -> ${res.status}: ${res.errorBody}`)
  return res.json.absolute_index
}

async function readTimeline(worldId) {
  const res = await call('GET', `/stage2/timeline?world_id=${worldId}&after=0&limit=100`)
  if (!res.ok) return { error: res.errorBody, entries: [] }
  return { entries: res.json.entries ?? [], wallMs: res.wallMs }
}

async function readNarrations(sceneIds, roleHeaders) {
  const beats = []
  let wallMs = 0
  for (const sceneId of sceneIds) {
    const res = await call('GET', `/stage1/scenes/${sceneId}/narration`, undefined, roleHeaders)
    wallMs += res.wallMs
    if (res.ok) for (const b of res.json ?? []) beats.push(b)
  }
  return { beats, wallMs }
}

/** One measured advance. Failures and timeouts are recorded, never thrown. */
async function measuredAdvance(kind, worldId, absoluteIndex, playerIntents, roleHeaders) {
  let res
  try {
    const body = { world_id: worldId, absolute_index: absoluteIndex }
    if (playerIntents !== undefined) body.player_intents = playerIntents
    res = await call('POST', '/stage1/advance', body, roleHeaders)
  } catch (err) {
    return {
      kind,
      advance: { timeout: true, timeoutMs: BEAT_TIMEOUT_MS, message: String(err) },
      modelRuns: [],
      callSummary: summarizeCalls([]),
      timeline: { entries: [] },
      narrations: { beats: [] },
      classification: classify(kind, { timeout: true, timeoutMs: BEAT_TIMEOUT_MS })
    }
  }
  const runId = res.json?.run_id ?? null
  const modelRuns = runId ? await modelRunsFor(runId) : { error: 'no run_id', calls: [] }
  const timeline = await readTimeline(worldId)
  const narrations = await readNarrations(
    (res.json?.scenes ?? []).map((s) => s.scene_id).filter(Boolean),
    roleHeaders
  )
  const record = {
    kind,
    absolute_index: absoluteIndex,
    story_id: null,
    world_id: worldId,
    run_id: runId,
    duplicate: res.json?.duplicate ?? null,
    client_wall_ms: res.wallMs,
    admission_ms: Number.isFinite(res.admissionMs) ? res.admissionMs : null,
    execution_ms: Number.isFinite(res.executionMs) ? res.executionMs : null,
    http_status: res.status,
    scenes: (res.json?.scenes ?? []).map((s) => ({
      scene_id: s.scene_id,
      event_id: s.event_id,
      resolution_outcome: s.resolution_outcome,
      narration: s.narration
    })),
    provider: await providerSnapshot(worldId),
    modelRuns: modelRuns.calls ?? [],
    modelRunsError: modelRuns.error ?? null,
    callSummary: summarizeCalls(modelRuns.calls ?? []),
    timelineEntries: (timeline.entries ?? []).length,
    timelineWallMs: timeline.wallMs ?? null,
    narrationBeats: narrations.beats.length,
    narrationReadMs: narrations.wallMs,
    classification: null
  }
  record.classification = classify(kind, res, record.modelRuns, timeline.entries, narrations.beats)
  if (!res.ok) record.rejection = res.errorBody
  return record
}

async function setupStory() {
  // Presets: Ember Vale world plus Wren and Ash, like the journey script.
  const worlds = await call('GET', '/library/presets?kind=world')
  const emberVale = worlds.json.find((p) => p.name === 'Ember Vale')
  if (!emberVale) throw new Error('Ember Vale world preset missing')
  const chars = await call('GET', '/library/presets?kind=character')
  const wren = chars.json.find((p) => p.name === 'Wren')
  const ash = chars.json.find((p) => p.name === 'Ash')
  if (!wren || !ash) throw new Error('Wren/Ash character presets missing')

  let pin = null
  if (MODE === 'fake') {
    const conn = await call('POST', '/settings/providers', {
      adapter: 'fake',
      name: `Reliability ${RUN}`,
      endpoint: 'http://127.0.0.1:7144/v1',
      allow_local_endpoint: true
    })
    if (!conn.ok) throw new Error(`fake connection -> ${conn.status}: ${conn.errorBody}`)
    const profs = await call('GET', `/settings/providers/${conn.json.id}/profiles`)
    const profile = (profs.json ?? [])[0]
    if (!profile) throw new Error('fake connection created no profile revision')
    pin = { profile_id: profile.id, profile_revision: profile.revision }
    note(`deterministic run pinned to fake profile ${profile.id}@rev${profile.revision}`)
  } else {
    note('live run uses the normal environment default (no pin)')
  }

  const draft = await call('POST', '/story-drafts', {
    payload: {
      world: { preset_id: emberVale.id, preset_revision: emberVale.current_revision },
      cast: [
        {
          instance_key: 'wren',
          preset_id: wren.id,
          preset_revision: wren.current_revision,
          name: 'Wren',
          location_key: 'hearth'
        },
        {
          instance_key: 'ash',
          preset_id: ash.id,
          preset_revision: ash.current_revision,
          name: 'Ash',
          location_key: 'market'
        }
      ],
      mode: { role: 'watcher' },
      story: { title: `${TITLE} ${MODE} ${RUN}` },
      ai: {
        art_source: 'curated',
        ...(pin ? { profile_id: pin.profile_id, profile_revision: pin.profile_revision } : {})
      }
    },
    current_step: 'review'
  })
  if (!draft.ok) throw new Error(`draft -> ${draft.status}: ${draft.errorBody}`)
  const created = await call(
    'POST',
    '/stories',
    { draft_id: draft.json.id, expected_draft_version: 1 },
    { 'Idempotency-Key': `reliability-${RUN}` },
    BEAT_TIMEOUT_MS
  )
  if (!created.ok) throw new Error(`create -> ${created.status}: ${created.errorBody}`)
  const storyId = created.json.story_id
  const worldId = created.json.world_id
  note(`story ${storyId} world ${worldId}`)
  return { storyId, worldId, pin }
}

async function runtimeCast(worldId) {
  const map = await call('GET', `/stage2/map?world_id=${worldId}`)
  if (!map.ok) throw new Error(`map -> ${map.status}: ${map.errorBody}`)
  const byName = Object.fromEntries(map.json.places.map((p) => [p.name, p]))
  if (!byName.Hearth || !byName.Market) throw new Error('Hearth/Market missing from map')
  const wrenIdx = byName.Hearth.occupants.indexOf('Wren')
  return {
    hearth: byName.Hearth,
    market: byName.Market,
    wrenId: byName.Hearth.occupant_ids[wrenIdx],
    ashId: byName.Market.occupant_ids[byName.Market.occupants.indexOf('Ash')]
  }
}

const playerHeaders = (characterId) => ({
  'X-Worldsim-Role': 'player',
  'X-Worldsim-Character': characterId
})

/** Seat selection governs advance auth (a creation-time grant wins over headers). */
async function selectSeat(worldId, role, characterId) {
  const body = { world_id: worldId, role }
  if (characterId !== undefined) body.character_id = characterId
  const res = await call('POST', '/stage2/roles/select', body)
  if (!res.ok) throw new Error(`seat ${role} -> ${res.status}: ${res.errorBody}`)
  return res.json
}

async function runScenario() {
  const { storyId, worldId } = await setupStory()
  const cast = await runtimeCast(worldId)

  // Beat 1: travel (Wren Hearth -> Market), committed by a watcher advance.
  const travel = await call('POST', '/stage2/activities', {
    world_id: worldId,
    character_id: cast.wrenId,
    kind: 'travel',
    to_location_id: cast.market.id
  })
  if (!travel.ok) note(`travel activity rejected: HTTP ${travel.status} ${travel.errorBody}`)
  beats.push({
    ...(await measuredAdvance('travel', worldId, (await currentIndex(worldId)) + 1, undefined, {})),
    story_id: storyId
  })

  // Beat 2: question (Wren asks Ash). The creation grant is watcher, so
  // take the player seat first — headers alone do not override a grant.
  await selectSeat(worldId, 'player', cast.wrenId)
  note('seat: player as Wren')
  beats.push({
    ...(await measuredAdvance(
      'question',
      worldId,
      (await currentIndex(worldId)) + 1,
      {
        [cast.wrenId]: {
          family: 'communicate',
          character_id: cast.wrenId,
          snapshot_id: NIL_SNAPSHOT,
          target_character_id: cast.ashId,
          topic: 'What did the market bell mean at dawn?'
        }
      },
      playerHeaders(cast.wrenId)
    )),
    story_id: storyId
  })

  // Beat 3: follow-up (Ash answers Wren).
  await selectSeat(worldId, 'player', cast.ashId)
  note('seat: player as Ash')
  beats.push({
    ...(await measuredAdvance(
      'follow-up',
      worldId,
      (await currentIndex(worldId)) + 1,
      {
        [cast.ashId]: {
          family: 'communicate',
          character_id: cast.ashId,
          snapshot_id: NIL_SNAPSHOT,
          target_character_id: cast.wrenId,
          topic: 'The bell meant the north road is open again.'
        }
      },
      playerHeaders(cast.ashId)
    )),
    story_id: storyId
  })

  // Beat 4: ordinary advance, no intents.
  await selectSeat(worldId, 'watcher')
  note('seat: watcher')
  beats.push({
    ...(await measuredAdvance(
      'ordinary-advance',
      worldId,
      (await currentIndex(worldId)) + 1,
      undefined,
      {}
    )),
    story_id: storyId
  })

  // Beat 5: reload — fresh reads only, proving committed beats display.
  const reloadStarted = performance.now()
  const detail = await call('GET', `/stories/${worldId}`)
  const timeline = await readTimeline(worldId)
  const sceneIds = beats.flatMap((b) => (b.scenes ?? []).map((s) => s.scene_id).filter(Boolean))
  const narrations = await readNarrations([...new Set(sceneIds)], {})
  const reloadWallMs = Math.round(performance.now() - reloadStarted)
  const committedEvents = beats.flatMap((b) => (b.scenes ?? []).map((s) => s.event_id))
  const visibleIds = new Set((timeline.entries ?? []).map((e) => e.event_id))
  const missing = committedEvents.filter((id) => id && !visibleIds.has(id))
  beats.push({
    kind: 'reload',
    story_id: storyId,
    world_id: worldId,
    client_wall_ms: reloadWallMs,
    detailWallMs: detail.wallMs,
    timelineWallMs: timeline.wallMs ?? null,
    narrationReadMs: narrations.wallMs,
    timelineEntries: (timeline.entries ?? []).length,
    narrationBeats: narrations.beats.length,
    missingEvents: missing,
    provider: await providerSnapshot(worldId),
    classification: {
      layers: {
        provider: 'not-applicable',
        validation: detail.ok ? 'pass' : 'rejected',
        committed: 'not-applicable',
        narration: 'not-applicable',
        display: missing.length === 0 && detail.ok ? 'yes' : 'no'
      },
      reasons:
        missing.length === 0 ? [] : [`${missing.length} committed events absent after reload`],
      useful: missing.length === 0 && detail.ok
    }
  })
  return { storyId, worldId }
}

/**
 * Browser pass: the real room renders the scenario story. Measures initial
 * room render, one in-page beat commit (click -> next beat button, with the
 * advance response headers captured off the wire), and a reload render.
 * Display overhead ~= browser commit wall - server execution wall.
 */
async function runBrowser(storyId, worldId) {
  const display = { story_id: storyId, world_id: worldId, steps: [] }
  const browser = await chromium.launch({ executablePath: EDGE, headless: true })
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
  let lastAdvanceHeaders = {}
  page.on('response', async (resp) => {
    if (resp.url().endsWith('/api/v1/stage1/advance') && resp.request().method() === 'POST') {
      const h = resp.headers()
      lastAdvanceHeaders = {
        admission_ms: Number(h['x-worldsim-admission-ms'] ?? NaN),
        execution_ms: Number(h['x-worldsim-execution-ms'] ?? NaN),
        status: resp.status()
      }
    }
  })
  try {
    let started = performance.now()
    await page.goto(`${BASE}/stories/${storyId}/play`, { waitUntil: 'networkidle' })
    await page.locator('.play__badge').waitFor({ timeout: 30000 })
    await page
      .getByRole('button', { name: /Commit beat/ })
      .first()
      .waitFor({ timeout: 60000 })
    display.steps.push({ name: 'room-render', wall_ms: Math.round(performance.now() - started) })

    const commitLabel = await page
      .getByRole('button', { name: /Commit beat/ })
      .first()
      .textContent()
    const nextIndex = Number((commitLabel ?? '').match(/Commit beat (\d+)/)?.[1] ?? NaN)
    started = performance.now()
    await page
      .getByRole('button', { name: /Commit beat/ })
      .first()
      .click()
    if (Number.isFinite(nextIndex)) {
      await page
        .getByRole('button', { name: `Commit beat ${nextIndex + 1}` })
        .waitFor({ timeout: 180000 })
    } else {
      await page.waitForTimeout(5000)
    }
    const commitWall = Math.round(performance.now() - started)
    const serverExec = Number.isFinite(lastAdvanceHeaders.execution_ms)
      ? lastAdvanceHeaders.execution_ms
      : null
    display.steps.push({
      name: 'browser-commit',
      wall_ms: commitWall,
      server_admission_ms: Number.isFinite(lastAdvanceHeaders.admission_ms)
        ? lastAdvanceHeaders.admission_ms
        : null,
      server_execution_ms: serverExec,
      display_overhead_ms: serverExec === null ? null : commitWall - serverExec,
      advance_http_status: lastAdvanceHeaders.status ?? null
    })

    started = performance.now()
    await page.goto(`${BASE}/stories/${storyId}/play`, { waitUntil: 'networkidle' })
    await page.locator('.play__badge').waitFor({ timeout: 30000 })
    await page
      .getByRole('button', { name: /Commit beat/ })
      .first()
      .waitFor({ timeout: 60000 })
    display.steps.push({
      name: 'room-reload-render',
      wall_ms: Math.round(performance.now() - started)
    })
    await page.screenshot({ path: path.join(OUT, `browser-room-${MODE}.png`) })
  } catch (err) {
    display.steps.push({ name: 'browser-error', error: String(err).slice(0, 300) })
    note(`browser pass failed (retained): ${String(err).slice(0, 200)}`)
  } finally {
    await browser.close()
  }
  return display
}

function range(values) {
  const xs = values.filter((v) => typeof v === 'number' && Number.isFinite(v))
  if (xs.length === 0) return null
  return { n: xs.length, min: Math.min(...xs), max: Math.max(...xs) }
}

async function main() {
  const startedAt = new Date().toISOString()
  const { storyId, worldId } = await runScenario()
  const display = WITH_BROWSER ? await runBrowser(storyId, worldId) : { skipped: true }
  const finishedAt = new Date().toISOString()

  const useful = beats.filter((b) => b.classification?.useful).length
  const report = {
    tool: 'reliability-baseline',
    mode: MODE,
    title: TITLE,
    run: RUN,
    started_at: startedAt,
    finished_at: finishedAt,
    api: API,
    story_id: storyId,
    world_id: worldId,
    config_frozen: {
      note: 'prompts, models, budgets, and retry behavior unchanged during collection'
    },
    beats,
    display,
    notes,
    summary: {
      beats: beats.length,
      useful_beats: useful,
      client_wall_ms: range(beats.map((b) => b.client_wall_ms)),
      admission_ms: range(beats.map((b) => b.admission_ms)),
      execution_ms: range(beats.map((b) => b.execution_ms)),
      timeline_read_ms: range(beats.map((b) => b.timelineWallMs)),
      narration_read_ms: range(beats.map((b) => b.narrationReadMs))
    }
  }
  fs.writeFileSync(path.join(OUT, `baseline-${MODE}-${RUN}.json`), JSON.stringify(report, null, 2))
  for (const b of beats) {
    const c = b.classification
    console.log(
      `${c?.useful ? 'USEFUL' : 'NOT-USEFUL'} [${b.kind}] wall=${b.client_wall_ms}ms ` +
        `admit=${b.admission_ms ?? '-'} exec=${b.execution_ms ?? '-'} ` +
        `layers=${JSON.stringify(c?.layers)}${(c?.reasons ?? []).length ? ` :: ${(c.reasons ?? []).join('; ')}` : ''}`
    )
  }
  console.log(`wrote ${OUT}/baseline-${MODE}-${RUN}.json (${useful}/${beats.length} useful)`)
}

await main()
