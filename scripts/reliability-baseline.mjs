#!/usr/bin/env node
/**
 * Reliability and beat-latency baseline (REL-BASE-001, schema 3).
 *
 * Fixed small scenario against the real API, no prompt/model/budget/retry
 * changes: story setup -> travel beat -> question beat (Wren asks Ash) ->
 * follow-up beat (Wren asks a neutral follow-up; Ash's committed answer is
 * traced through intents AND reactions, never authored here) -> ordinary
 * watcher advance -> reload reads. A read-only browser pass measures room
 * rendering only and never commits, so the four-advance live cap holds.
 *
 * Attempt records persist first: the skeleton is stored and checkpointed
 * before the POST, the transport outcome carries actual elapsed time, and
 * each enrichment read failure is retained on the record instead of losing
 * the attempt. A transport error after a POST leaves commit ambiguity, which
 * is probed via the clock and recorded — never silently skipped.
 *
 * Layer semantics: validation 'accepted' is HTTP 200, not gameplay success;
 * display requires EVERY committed event retrievable; answer usefulness is
 * always 'unevaluated'; browser display is 'measured' only by the read-only
 * pass. Core semantics live in reliability-baseline-lib.mjs with vitest
 * coverage; this file wires real dependencies.
 *
 * Usage:
 *   EMBER_VALE_API_KEY=<operator key> node scripts/reliability-baseline.mjs \
 *     [--api http://localhost:8101/api/v1] [--mode fake|live] \
 *     [--out docs/evidence/reliability-baseline-v1] [--title "Baseline"] \
 *     [--no-browser] [--base http://127.0.0.1:5173] \
 *     [--pin-profile <id> --pin-revision <n>]
 */

import fs from 'node:fs'
import path from 'node:path'
import { chromium } from 'playwright-core'
import {
  buildReport,
  findNpcAnswers,
  recordAdvance,
  runPlannedScenario,
  transportKind
} from './reliability-baseline-lib.mjs'

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
const PIN_PROFILE = opt('--pin-profile', '')
const PIN_REVISION = opt('--pin-revision', '')
const KEY = process.env.EMBER_VALE_API_KEY || ''
if (!KEY) throw new Error('set EMBER_VALE_API_KEY (the compose operator key)')
if (!['fake', 'live'].includes(MODE)) throw new Error(`--mode must be fake|live (got ${MODE})`)
if ((PIN_PROFILE && !PIN_REVISION) || (!PIN_PROFILE && PIN_REVISION))
  throw new Error('--pin-profile and --pin-revision must be given together')

const RUN = Date.now().toString(36)
const EDGE = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe'
const NIL_SNAPSHOT = '00000000-0000-0000-0000-000000000000'
const BEAT_TIMEOUT_MS = 180000
const PARTIAL_PATH = path.join(OUT, `baseline-${MODE}-${RUN}.partial.json`)
const FINAL_PATH = path.join(OUT, `baseline-${MODE}-${RUN}.json`)

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
    slotClaimMs: Number(res.headers.get('x-worldsim-slot-claim-ms') ?? NaN),
    executionMs: Number(res.headers.get('x-worldsim-execution-ms') ?? NaN)
  }
}

const beats = []
const notes = []
const blockedSteps = []
let storyId = null
let worldId = null
let startedAt = ''
const note = (text) => {
  notes.push(text)
  console.log(`note: ${text}`)
}

function checkpoint() {
  fs.writeFileSync(
    PARTIAL_PATH,
    JSON.stringify(
      buildReport({
        beats,
        notes,
        display: null,
        complete: false,
        fatal: null,
        blockedSteps,
        meta: {
          mode: MODE,
          title: TITLE,
          run: RUN,
          startedAt,
          finishedAt: new Date().toISOString(),
          api: API,
          storyId,
          worldId,
          pin: PIN_PROFILE ? { profile_id: PIN_PROFILE, revision: Number(PIN_REVISION) } : null
        }
      }),
      null,
      2
    )
  )
}

async function providerSnapshot(story) {
  const res = await call('GET', `/stories/${story}/provider`)
  if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.errorBody}`)
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

async function modelRunsFor(run) {
  const res = await call('GET', `/stage1/model-runs?phase_run_id=${run}`)
  if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.errorBody}`)
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
    finish_reason: c.finish_reason ?? null,
    reasoning_tokens: c.reasoning_tokens ?? 0,
    content_type: c.content_type ?? null,
    content_length: c.content_length ?? null,
    reasoning_only: c.reasoning_only ?? null,
    max_tokens: c.max_tokens,
    pin_profile_id: c.pin_profile_id,
    pin_profile_revision: c.pin_profile_revision,
    budgets: c.budgets ?? {},
    attempts: c.attempts ?? []
  }))
  return { calls }
}

async function currentIndex(world) {
  const res = await call('GET', `/stories/${world}`)
  if (!res.ok) throw new Error(`story detail -> ${res.status}: ${res.errorBody}`)
  return res.json.absolute_index
}

async function readTimeline(world) {
  const res = await call('GET', `/stage2/timeline?world_id=${world}&after=0&limit=100`)
  if (!res.ok) throw new Error(res.errorBody || `timeline -> ${res.status}`)
  return { entries: res.json.entries ?? [], wallMs: res.wallMs }
}

async function readNarrations(sceneIds, roleHeaders) {
  const beatList = []
  let wallMs = 0
  for (const sceneId of sceneIds) {
    const res = await call('GET', `/stage1/scenes/${sceneId}/narration`, undefined, roleHeaders)
    wallMs += res.wallMs
    if (!res.ok) throw new Error(res.errorBody || `narration ${sceneId} -> ${res.status}`)
    for (const b of res.json ?? []) beatList.push({ ...b, scene_id: sceneId })
  }
  return { beats: beatList, wallMs }
}

/** Committed scenes with intents, reactions, and narration citations. */
async function readCommittedSources(run, roleHeaders) {
  const list = await call('GET', `/stage1/scenes?phase_run_id=${run}`, undefined, roleHeaders)
  if (!list.ok) throw new Error(list.errorBody || `scenes -> ${list.status}`)
  const scenes = []
  for (const summary of list.json ?? []) {
    try {
      const detail = await call('GET', `/stage1/scenes/${summary.id}`, undefined, roleHeaders)
      if (!detail.ok) throw new Error(detail.errorBody || `scene ${summary.id} -> ${detail.status}`)
      const d = detail.json
      // A narration read failure must not erase the already-read intents
      // and reactions: the answer stays detectable, narration retrieval is
      // reported separately.
      let narrations = []
      let narrationError = null
      try {
        const beats = await readNarrations([summary.id], roleHeaders)
        narrations = beats.beats.map((b) => ({
          id: b.id,
          speaker_id: b.speaker_id,
          cited_fact_keys: b.cited_fact_keys ?? [],
          snippet: (b.text ?? '').slice(0, 160)
        }))
      } catch (err) {
        narrations = []
        narrationError = String(err).slice(0, 200)
      }
      scenes.push({
        scene_id: summary.id,
        event_id: d.event_id ?? summary.event_id ?? null,
        status: d.status,
        resolution: d.resolution ?? null,
        participants: (d.participants ?? []).map((p) => p.character_id),
        intents: (d.intents ?? []).map((i) => ({
          id: i.id,
          author_character_id: i.author_character_id,
          family: i.family,
          target_character_id: i.detail?.target_character_id ?? null,
          topic: i.detail?.topic ?? null
        })),
        reactions: (d.reactions ?? []).map((r) => ({
          id: r.id,
          reactor_character_id: r.reactor_character_id,
          family: r.family,
          target_character_id: r.detail?.target_character_id ?? null,
          topic: r.detail?.topic ?? null
        })),
        narrations,
        narration_status: narrationError ? 'failed' : 'complete',
        narrationError
      })
    } catch (err) {
      scenes.push({ scene_id: summary.id, error: String(err).slice(0, 300) })
    }
  }
  return { scenes }
}

/**
 * One measured advance, persistence-first via recordAdvance. On a transport
 * error the clock is re-read for context, but the outcome stays unresolved
 * either way: clock equality proves nothing (work may be pending, partial,
 * or finished without a delivered response), and even an advanced clock
 * leaves the response unconfirmed.
 */
async function measuredAdvance(kind, world, absoluteIndex, playerIntents, roleHeaders) {
  const deps = {
    postAdvance: (body, hdrs) => call('POST', '/stage1/advance', body, hdrs),
    getRuns: (run) => modelRunsFor(run),
    getTimeline: (w) => readTimeline(w),
    getNarrations: (ids, hdrs) => readNarrations(ids, hdrs),
    getProvider: (w) => providerSnapshot(w),
    now: () => performance.now()
  }
  const store = { beats, checkpoint }
  const record = await recordAdvance(deps, store, {
    kind,
    world,
    storyId,
    absoluteIndex,
    playerIntents,
    roleHeaders
  })
  if (record.transport_error) {
    try {
      record.post_error_clock = await currentIndex(world)
      if (record.post_error_clock > absoluteIndex) {
        record.resolution = 'committed-unconfirmed'
        record.resolution_reason =
          `clock advanced past attempted index ${absoluteIndex} ` +
          `(now ${record.post_error_clock}) but no response arrived; content unconfirmed`
        record.commit_ambiguous = true
      } else {
        record.commit_ambiguous = false
      }
      note(
        `${kind}: transport ${record.transport_error}, resolution ${record.resolution} ` +
          `(clock ${record.post_error_clock} vs attempted ${absoluteIndex})`
      )
    } catch (err) {
      record.post_error_clock = null
      record.commit_ambiguous = null
      note(`${kind}: post-error clock read failed (retained): ${String(err).slice(0, 200)}`)
    }
    checkpoint()
  }
  return record
}

const playerHeaders = (characterId) => ({
  'X-Worldsim-Role': 'player',
  'X-Worldsim-Character': characterId
})

/** Seat selection governs advance auth (a grant wins over headers). Never throws. */
async function setSeat(world, role, characterId) {
  const body = { world_id: world, role }
  if (characterId !== undefined) body.character_id = characterId
  try {
    const res = await call('POST', '/stage2/roles/select', body)
    if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.errorBody}`)
    note(`seat: ${role}${characterId ? ` as ${characterId.slice(0, 8)}` : ''}`)
    return { ok: true }
  } catch (err) {
    note(`seat ${role} failed (${transportKind(err)}, retained): ${String(err).slice(0, 200)}`)
    return { ok: false, kind: transportKind(err), message: String(err).slice(0, 300) }
  }
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
  if (PIN_PROFILE) {
    pin = { profile_id: PIN_PROFILE, profile_revision: Number(PIN_REVISION) }
    note(`explicit pin ${pin.profile_id}@rev${pin.profile_revision} (sampling otherwise unchanged)`)
  } else if (MODE === 'fake') {
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
  storyId = created.json.story_id
  worldId = created.json.world_id
  note(`story ${storyId} world ${worldId}`)
  return { pin }
}

async function runtimeCast(world) {
  const map = await call('GET', `/stage2/map?world_id=${world}`)
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

const communicate = (actor, target, topic) => ({
  [actor]: {
    family: 'communicate',
    character_id: actor,
    snapshot_id: NIL_SNAPSHOT,
    target_character_id: target,
    topic
  }
})

async function runScenario() {
  await setupStory()
  const cast = await runtimeCast(worldId)

  // Beat 1: travel (Wren Hearth -> Market), committed by a watcher advance.
  const travel = await call('POST', '/stage2/activities', {
    world_id: worldId,
    character_id: cast.wrenId,
    kind: 'travel',
    to_location_id: cast.market.id
  })
  if (!travel.ok) note(`travel activity rejected: HTTP ${travel.status} ${travel.errorBody}`)

  // Advances run in order through the shared driver: any transport error
  // halts further mutation (no seat change or advance may follow) while
  // read-only finalization still runs for the acknowledged attempts.
  // Beat 1 travel (watcher grant from creation, no seat change); beat 2
  // question (player seat — headers alone lose to the grant); beat 3 neutral
  // follow-up with Wren still controlled; beat 4 ordinary watcher advance.
  // Ash's answer, if any, must be Ash's own committed communicate intent or
  // reaction addressed to Wren — traced in finalization, never authored here.
  const steps = [
    { kind: 'travel', seat: null, playerIntents: undefined, roleHeaders: {} },
    {
      kind: 'question',
      seat: { role: 'player', characterId: cast.wrenId },
      playerIntents: communicate(cast.wrenId, cast.ashId, 'What did the market bell mean at dawn?'),
      roleHeaders: playerHeaders(cast.wrenId)
    },
    {
      kind: 'follow-up',
      seat: null,
      playerIntents: communicate(
        cast.wrenId,
        cast.ashId,
        'What should we watch for on the road ahead?'
      ),
      roleHeaders: playerHeaders(cast.wrenId)
    },
    {
      kind: 'ordinary-advance',
      seat: { role: 'watcher' },
      playerIntents: undefined,
      roleHeaders: {}
    }
  ]
  const ops = {
    setSeat: (seat) => setSeat(worldId, seat.role, seat.characterId),
    advance: async (step) =>
      measuredAdvance(
        step.kind,
        worldId,
        (await currentIndex(worldId)) + 1,
        step.playerIntents,
        step.roleHeaders
      ),
    onBlocked: (blocked) => {
      blockedSteps.push(...blocked)
      checkpoint()
    },
    finalize: () => finalizeReads(cast),
    note
  }
  // Blocked steps already persist through onBlocked (with checkpoint) before
  // finalization; appending the returned steps again would double-count them.
  const { blockedSteps: blocked } = await runPlannedScenario(steps, ops)
  if (blocked.length > 0) {
    note(`blocked steps preserved: ${blocked.map((b) => b.kind).join(', ')}`)
  }
}

/**
 * Read-only finalization for previously acknowledged runs: post-hoc source
 * tracing (committed intents, reactions, narration citations per scene, plus
 * whether Ash produced a committed answer) and reload reads. Never changes
 * seats: if the current grant prevents retrieval, that is reported
 * explicitly as source-retrieval-failed.
 */
async function finalizeReads(cast) {
  note('finalizing reads with the current grant; seats are never changed to obtain evidence')
  // Post-hoc source tracing: committed intents and
  // reactions per scene, plus whether Ash produced a committed answer.
  // A failed source read is 'source-retrieval-failed', never 'no answer'.
  for (const beat of beats) {
    if (!beat.run_id) continue
    try {
      const sources = await readCommittedSources(beat.run_id, {})
      beat.committed_sources = sources.scenes ?? []
    } catch (err) {
      beat.committed_sources = []
      beat.sourcesError = `${transportKind(err)}: ${String(err).slice(0, 300)}`
      note(`${beat.kind} scene read failed (retained): ${beat.sourcesError}`)
    }
    if (beat.kind === 'question' || beat.kind === 'follow-up') {
      if (beat.sourcesError || beat.committed_sources.some((s) => s.error)) {
        beat.npc_answer = {
          asker: 'Wren',
          responder: 'Ash',
          status: 'source-retrieval-failed',
          narration_retrieval: 'unknown',
          answers: []
        }
      } else {
        const found = findNpcAnswers(beat.committed_sources, cast.wrenId, cast.ashId)
        beat.npc_answer = {
          asker: 'Wren',
          responder: 'Ash',
          status: found.committed ? 'answered' : 'no-answer',
          narration_retrieval: beat.committed_sources.some((s) => s.narrationError)
            ? 'failed'
            : 'complete',
          answers: found.answers
        }
      }
      note(
        `${beat.kind}: Ash answer status: ${beat.npc_answer.status} ` +
          `(narration retrieval ${beat.npc_answer.narration_retrieval})`
      )
    }
    checkpoint()
  }

  // Beat 5: reload — fresh reads only, proving committed beats retrieve.
  // Not counted among advances and never 'useful': it measures retrieval.
  // The skeleton is recorded before the reads, and each read failure is
  // preserved on the record without discarding the successful reads.
  const reloadStarted = performance.now()
  const reload = {
    kind: 'reload',
    story_id: storyId,
    world_id: worldId,
    client_wall_ms: null,
    detailWallMs: null,
    timelineWallMs: null,
    narrationReadMs: null,
    timelineEntries: 0,
    narrationBeats: 0,
    missingEvents: [],
    provider: null,
    readErrors: [],
    classification: null
  }
  beats.push(reload)
  checkpoint()
  const fail = (name, err) => {
    const entry = `${name}: ${transportKind(err)}: ${String(err).slice(0, 200)}`
    reload.readErrors.push(entry)
    note(`reload ${entry} (retained)`)
  }
  let detail = null
  try {
    detail = await call('GET', `/stories/${worldId}`)
    reload.detailWallMs = detail.wallMs
    if (!detail.ok) reload.readErrors.push(`detail: HTTP ${detail.status} ${detail.errorBody}`)
  } catch (err) {
    fail('detail', err)
  }
  let timelineEntries = []
  try {
    const timeline = await readTimeline(worldId)
    timelineEntries = timeline.entries ?? []
    reload.timelineEntries = timelineEntries.length
    reload.timelineWallMs = timeline.wallMs ?? null
  } catch (err) {
    reload.timelineError = `${transportKind(err)}: ${String(err).slice(0, 200)}`
    fail('timeline', err)
  }
  let narrationBeats = []
  try {
    const sceneIds = beats.flatMap((b) => (b.scenes ?? []).map((s) => s.scene_id).filter(Boolean))
    const narrations = await readNarrations([...new Set(sceneIds)], {})
    narrationBeats = narrations.beats ?? []
    reload.narrationBeats = narrationBeats.length
    reload.narrationReadMs = narrations.wallMs ?? null
  } catch (err) {
    reload.narrationError = `${transportKind(err)}: ${String(err).slice(0, 200)}`
    fail('narrations', err)
  }
  try {
    reload.provider = await providerSnapshot(worldId)
  } catch (err) {
    reload.providerError = `${transportKind(err)}: ${String(err).slice(0, 200)}`
    fail('provider', err)
  }
  reload.client_wall_ms = Math.round(performance.now() - reloadStarted)
  const committedEvents = beats.flatMap((b) => (b.scenes ?? []).map((s) => s.event_id))
  const visibleIds = new Set(timelineEntries.map((e) => e.event_id))
  const missing = committedEvents.filter((id) => id && !visibleIds.has(id))
  reload.missingEvents = missing
  if (missing.length > 0)
    reload.readErrors.push(`${missing.length} committed events absent after reload`)
  const validated = detail && detail.ok
  reload.classification = {
    layers: {
      provider: 'not-applicable',
      validation: detail ? (detail.ok ? 'accepted' : 'rejected') : 'unknown',
      committed: 'not-applicable',
      narration: 'not-applicable',
      display: validated && missing.length === 0 && reload.readErrors.length === 0 ? 'yes' : 'no'
    },
    reasons: [...reload.readErrors],
    answer_usefulness: 'unevaluated'
  }
  checkpoint()
}

/**
 * Read-only browser pass: the real room renders the scenario story (initial
 * render plus a reload render). It never commits a beat, so the four-advance
 * live cap holds exactly. Render timings include app fetch and paint; they
 * are combined display cost, not isolated rendering time.
 */
async function runBrowser() {
  const display = { story_id: storyId, world_id: worldId, status: 'measured', steps: [] }
  const browser = await chromium.launch({ executablePath: EDGE, headless: true })
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
  try {
    let started = performance.now()
    await page.goto(`${BASE}/stories/${storyId}/play`, { waitUntil: 'networkidle' })
    await page.locator('.play__badge').waitFor({ timeout: 30000 })
    await page
      .getByRole('button', { name: /Commit beat/ })
      .first()
      .waitFor({ timeout: 60000 })
    display.steps.push({ name: 'room-render', wall_ms: Math.round(performance.now() - started) })

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
    display.status = 'failed'
    display.steps.push({ name: 'browser-error', error: String(err).slice(0, 300) })
    note(`browser pass failed (retained): ${String(err).slice(0, 200)}`)
  } finally {
    await browser.close()
  }
  return display
}

async function main() {
  startedAt = new Date().toISOString()
  let display = null
  let fatal = null
  try {
    await runScenario()
    if (WITH_BROWSER) display = await runBrowser()
    else display = { status: 'skipped', steps: [] }
  } catch (err) {
    fatal = `${transportKind(err)}: ${String(err).slice(0, 300)}`
    note(`scenario aborted (partial report retained): ${fatal}`)
  } finally {
    const complete = fatal === null
    fs.writeFileSync(
      FINAL_PATH,
      JSON.stringify(
        buildReport({
          beats,
          notes,
          display,
          complete,
          fatal,
          blockedSteps,
          meta: {
            mode: MODE,
            title: TITLE,
            run: RUN,
            startedAt,
            finishedAt: new Date().toISOString(),
            api: API,
            storyId,
            worldId,
            pin: PIN_PROFILE ? { profile_id: PIN_PROFILE, revision: Number(PIN_REVISION) } : null
          }
        }),
        null,
        2
      )
    )
  }
  for (const b of beats) {
    const c = b.classification
    if (b.kind === 'reload') {
      console.log(
        `RELOAD wall=${b.client_wall_ms}ms display=${c?.layers?.display}` +
          `${(c?.reasons ?? []).length ? ` :: ${(c.reasons ?? []).join('; ')}` : ''}`
      )
      continue
    }
    console.log(
      `[${b.kind}] wall=${b.client_wall_ms ?? '?'}ms slot-claim=${b.slot_claim_ms ?? '-'} ` +
        `exec=${b.execution_ms ?? '-'} committed=${c?.advancement?.committed ?? '?'} ` +
        `retrieval=${c?.advancement?.retrieval_complete ?? '?'} ` +
        `narration=${c?.layers?.narration} provider=${c?.layers?.provider} ` +
        `answer=${b.npc_answer?.status ?? c?.answer_usefulness}` +
        `${b.transport_error ? ` transport=${b.transport_error} resolution=${b.resolution ?? '?'}` : ''}` +
        `${b.commit_ambiguous ? ' AMBIGUOUS-COMMIT' : ''}` +
        `${(c?.reasons ?? []).length ? ` :: ${(c.reasons ?? []).join('; ')}` : ''}` +
        `${(b.readErrors ?? []).length ? ` reads: ${b.readErrors.join('; ')}` : ''}`
    )
  }
  for (const blocked of blockedSteps) {
    console.log(`BLOCKED [${blocked.kind}] :: ${blocked.reason}`)
  }
  const final = JSON.parse(fs.readFileSync(FINAL_PATH, 'utf8'))
  console.log(
    `wrote ${FINAL_PATH} complete=${final.complete} ` +
      `committed=${final.summary.advances_committed}/${final.summary.advances} ` +
      `blocked=${final.summary.blocked} ` +
      `browser=${final.summary.browser_display} answers=${final.summary.answer_usefulness}`
  )
  if (fatal !== null) process.exitCode = 1
}

await main()
