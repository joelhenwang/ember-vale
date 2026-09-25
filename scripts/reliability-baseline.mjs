#!/usr/bin/env node
/**
 * Reliability and beat-latency baseline (REL-BASE-001, corrected semantics).
 *
 * Fixed small scenario against the real API, no prompt/model/budget/retry
 * changes: story setup -> travel beat -> question beat (Wren asks Ash) ->
 * follow-up beat (Wren asks again; Ash's committed answer is traced, never
 * authored by the harness) -> ordinary watcher advance -> reload reads.
 * An optional read-only browser pass measures room rendering only and never
 * commits a beat, so the four-advance live cap holds exactly.
 *
 * What each layer establishes — and what it does not:
 * - validation 'accepted' means HTTP 200 with a well-formed envelope. It is
 *   not a gameplay-success measurement.
 * - committed means the advance response carries event ids (not a duplicate).
 * - retrieval means EVERY committed event of the beat is re-readable from
 *   the timeline (all of them, not merely one) with non-empty narration text.
 * - narration reports the server status per scene (narrated/fallback/failed).
 * - browser display is 'measured' only when the read-only browser pass
 *   renders the room; otherwise 'failed' (retained) or 'skipped'.
 * - answer usefulness is always 'unevaluated': nothing here establishes an
 *   answered question or accepted model output.
 *
 * Timing splits per beat: client wall (submit -> response), server
 * slot-claim vs execution (X-Worldsim-Slot-Claim-Ms /
 * X-Worldsim-Execution-Ms headers; slot-claim is the execution-slot wait,
 * not run admission), per-role generation from the model-runs audit (each
 * traced call already includes its retries), and read-only browser render.
 * End-to-end wall is recorded separately from summed call durations; summed
 * durations double-count concurrent calls, so both are reported.
 *
 * Failure handling: every beat checkpoints to disk immediately; the final
 * report is written in a `finally` block, so timeouts and seat-change
 * failures leave a partial report behind. Transport failures distinguish
 * timeouts from connection errors and other transport errors.
 *
 * Usage:
 *   EMBER_VALE_API_KEY=<operator key> node scripts/reliability-baseline.mjs \
 *     [--api http://localhost:8101/api/v1] [--mode fake|live] \
 *     [--out docs/evidence/reliability-baseline-v1] [--title "Baseline"] \
 *     [--no-browser] [--base http://127.0.0.1:5173] \
 *     [--pin-profile <id> --pin-revision <n>]
 *
 * --mode fake pins the story to a throwaway fake-echo provider profile, so
 * the run is deterministic. --mode live uses the normal environment default
 * (capped at exactly four committed advances plus reads). --pin-profile with
 * --pin-revision pins either mode to an explicit profile revision (e.g. for
 * a future pinned-budget comparison with sampling otherwise unchanged).
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
let storyId = null
let worldId = null
const note = (text) => {
  notes.push(text)
  console.log(`note: ${text}`)
}

function transportKind(err) {
  const message = String(err)
  if (err instanceof Error && err.name === 'TimeoutError') return 'timeout'
  if (/fetch failed|ECONNREFUSED|ENOTFOUND|EHOSTUNREACH/i.test(message)) return 'connection'
  return 'transport'
}

/**
 * Classify one beat into outcome layers. HTTP 200 is reported as
 * validation 'accepted' — never as gameplay success. Display requires
 * every committed event to be retrievable, not merely one. Answer
 * usefulness is always 'unevaluated'.
 */
function classify(kind, advanceRes, modelRuns, timelineEntries, narrationBeats) {
  const layers = {
    provider: 'unknown',
    validation: 'unknown',
    committed: 'unknown',
    narration: 'unknown',
    display: 'unknown'
  }
  const reasons = []
  if (!advanceRes) return { layers, reasons: ['no advance response recorded'] }
  if (advanceRes.transport_error) {
    return {
      layers,
      reasons: [
        `advance ${advanceRes.transport_error} after ~${advanceRes.wallMs ?? '?'}ms: ` +
          `${(advanceRes.message ?? '').slice(0, 200)} (retained, not retried)`
      ]
    }
  }
  if (!advanceRes.ok) {
    layers.validation = 'rejected'
    layers.committed = 'no'
    layers.provider = 'not-applicable'
    layers.narration = 'not-applicable'
    layers.display = 'no'
    reasons.push(`advance rejected: HTTP ${advanceRes.status} ${advanceRes.errorBody}`)
    return { layers, reasons, answer_usefulness: 'unevaluated' }
  }
  const body = advanceRes.json ?? {}
  layers.validation = 'accepted'
  if (body.duplicate === true) reasons.push('duplicate replay (no new canon)')

  const failed = (modelRuns ?? []).filter((c) => c.status === 'failed')
  const unfinished = (modelRuns ?? []).filter(
    (c) => c.status !== 'succeeded' && c.status !== 'failed'
  )
  if ((modelRuns ?? []).length === 0) {
    layers.provider = 'no-calls'
    reasons.push('no traced model calls for this phase')
  } else if (failed.length === 0 && unfinished.length === 0) {
    layers.provider = 'ok'
  } else if (failed.length > 0) {
    layers.provider = 'degraded'
    reasons.push(`provider degraded: ${failed.map((c) => `${c.role}:${c.error_code}`).join(', ')}`)
  } else {
    layers.provider = 'failed'
    reasons.push('no provider call reached a terminal state with success')
  }
  for (const c of unfinished) reasons.push(`call ${c.call_id} (${c.role}) left ${c.status}`)

  const scenes = body.scenes ?? []
  const committedEvents = scenes.map((s) => s.event_id).filter(Boolean)
  const committed = committedEvents.length > 0 && body.duplicate !== true
  layers.committed = committed ? 'yes' : 'no'
  if (!committed) reasons.push('no committed events in the advance response')

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
  const missing = committedEvents.filter((id) => !visibleIds.has(id))
  const beatTexts = (narrationBeats ?? []).filter((b) => (b.text ?? '').trim().length > 0)
  const retrievalComplete = committed && missing.length === 0 && beatTexts.length > 0
  layers.display = retrievalComplete ? 'yes' : 'no'
  if (!retrievalComplete)
    reasons.push(
      `retrieval: ${committedEvents.length - missing.length}/${committedEvents.length} ` +
        `committed events in timeline, ${beatTexts.length} non-empty beats read back` +
        (missing.length > 0 ? `; missing ${missing.join(',')}` : '')
    )

  return {
    layers,
    reasons,
    advancement: { committed, retrieval_complete: retrievalComplete, narration: layers.narration },
    answer_usefulness: 'unevaluated',
    kind
  }
}

async function providerSnapshot(story) {
  const res = await call('GET', `/stories/${story}/provider`)
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

async function modelRunsFor(run) {
  const res = await call('GET', `/stage1/model-runs?phase_run_id=${run}`)
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

function summarizeCalls(calls) {
  const byRole = {}
  let prompt_tokens = 0
  let completion_tokens = 0
  let reasoning_tokens = 0
  let attempts = 0
  let reasoning_only_failures = 0
  const error_codes = {}
  for (const c of calls) {
    byRole[c.role] = byRole[c.role] ?? { calls: 0, failed: 0, latency_ms: 0, attempts: 0 }
    byRole[c.role].calls += 1
    if (c.status === 'failed') {
      byRole[c.role].failed += 1
      if (c.error_code) error_codes[c.error_code] = (error_codes[c.error_code] ?? 0) + 1
      if (c.reasoning_only === true) reasoning_only_failures += 1
    }
    byRole[c.role].latency_ms += c.latency_ms ?? 0
    byRole[c.role].attempts += (c.attempts ?? []).length
    prompt_tokens += c.prompt_tokens ?? 0
    completion_tokens += c.completion_tokens ?? 0
    reasoning_tokens += c.reasoning_tokens ?? 0
    attempts += (c.attempts ?? []).length
  }
  return {
    byRole,
    prompt_tokens,
    completion_tokens,
    reasoning_tokens,
    attempts,
    reasoning_only_failures,
    error_codes
  }
}

async function currentIndex(world) {
  const res = await call('GET', `/stories/${world}`)
  if (!res.ok) throw new Error(`story detail -> ${res.status}: ${res.errorBody}`)
  return res.json.absolute_index
}

async function readTimeline(world) {
  const res = await call('GET', `/stage2/timeline?world_id=${world}&after=0&limit=100`)
  if (!res.ok) return { error: res.errorBody, entries: [] }
  return { entries: res.json.entries ?? [], wallMs: res.wallMs }
}

async function readNarrations(sceneIds, roleHeaders) {
  const beatList = []
  let wallMs = 0
  for (const sceneId of sceneIds) {
    const res = await call('GET', `/stage1/scenes/${sceneId}/narration`, undefined, roleHeaders)
    wallMs += res.wallMs
    if (res.ok) for (const b of res.json ?? []) beatList.push(b)
  }
  return { beats: beatList, wallMs }
}

/** Committed scenes with their intents: traces decisions to their sources. */
async function readCommittedSources(run, roleHeaders) {
  const list = await call('GET', `/stage1/scenes?phase_run_id=${run}`, undefined, roleHeaders)
  if (!list.ok) return { error: list.errorBody, scenes: [] }
  const scenes = []
  for (const summary of list.json ?? []) {
    const detail = await call('GET', `/stage1/scenes/${summary.id}`, undefined, roleHeaders)
    if (!detail.ok) {
      scenes.push({ scene_id: summary.id, error: detail.errorBody })
      continue
    }
    const d = detail.json
    scenes.push({
      scene_id: summary.id,
      event_id: d.event_id ?? summary.event_id ?? null,
      status: d.status,
      resolution: d.resolution ?? null,
      participants: (d.participants ?? []).map((p) => p.character_id),
      intents: (d.intents ?? []).map((i) => ({
        author_character_id: i.author_character_id,
        family: i.family,
        topic: i.detail?.topic ?? null
      }))
    })
  }
  return { scenes }
}

/** One measured advance. Failures and timeouts are recorded, never thrown. */
async function measuredAdvance(kind, world, absoluteIndex, playerIntents, roleHeaders) {
  let res
  try {
    const body = { world_id: world, absolute_index: absoluteIndex }
    if (playerIntents !== undefined) body.player_intents = playerIntents
    res = await call('POST', '/stage1/advance', body, roleHeaders)
  } catch (err) {
    const failure = transportKind(err)
    return {
      kind,
      advance: {
        transport_error: failure,
        wallMs: BEAT_TIMEOUT_MS,
        message: String(err)
      },
      modelRuns: [],
      callSummary: summarizeCalls([]),
      timelineEntries: 0,
      narrationBeats: 0,
      committed_sources: [],
      classification: classify(kind, {
        transport_error: failure,
        wallMs: BEAT_TIMEOUT_MS,
        message: String(err)
      })
    }
  }
  const run = res.json?.run_id ?? null
  const modelRuns = run ? await modelRunsFor(run) : { error: 'no run_id', calls: [] }
  const timeline = await readTimeline(world)
  const narrations = await readNarrations(
    (res.json?.scenes ?? []).map((s) => s.scene_id).filter(Boolean),
    roleHeaders
  )
  const record = {
    kind,
    absolute_index: absoluteIndex,
    story_id: storyId,
    world_id: world,
    run_id: run,
    duplicate: res.json?.duplicate ?? null,
    client_wall_ms: res.wallMs,
    slot_claim_ms: Number.isFinite(res.slotClaimMs) ? res.slotClaimMs : null,
    execution_ms: Number.isFinite(res.executionMs) ? res.executionMs : null,
    http_status: res.status,
    scenes: (res.json?.scenes ?? []).map((s) => ({
      scene_id: s.scene_id,
      event_id: s.event_id,
      resolution_outcome: s.resolution_outcome,
      narration: s.narration
    })),
    provider: await providerSnapshot(world),
    modelRuns: modelRuns.calls ?? [],
    modelRunsError: modelRuns.error ?? null,
    callSummary: summarizeCalls(modelRuns.calls ?? []),
    timelineEntries: (timeline.entries ?? []).length,
    timelineWallMs: timeline.wallMs ?? null,
    narrationBeats: narrations.beats.length,
    narrationReadMs: narrations.wallMs,
    committed_sources: [],
    classification: null
  }
  record.classification = classify(kind, res, record.modelRuns, timeline.entries, narrations.beats)
  if (!res.ok) record.rejection = res.errorBody
  beats.push(record)
  checkpoint()
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
    const failure = transportKind(err)
    note(`seat ${role} failed (${failure}, retained): ${String(err).slice(0, 200)}`)
    return { ok: false, kind: failure, message: String(err).slice(0, 300) }
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
  await measuredAdvance('travel', worldId, (await currentIndex(worldId)) + 1, undefined, {})

  // Beat 2: question (Wren asks Ash; player seat, headers alone lose to the grant).
  await setSeat(worldId, 'player', cast.wrenId)
  await measuredAdvance(
    'question',
    worldId,
    (await currentIndex(worldId)) + 1,
    communicate(cast.wrenId, cast.ashId, 'What did the market bell mean at dawn?'),
    playerHeaders(cast.wrenId)
  )

  // Beat 3: follow-up (Wren stays controlled and asks again). Ash's answer,
  // if any, must be Ash's own committed communicate intent — traced below,
  // never authored by this harness.
  await measuredAdvance(
    'follow-up',
    worldId,
    (await currentIndex(worldId)) + 1,
    communicate(cast.wrenId, cast.ashId, 'And what does the open north road mean for us?'),
    playerHeaders(cast.wrenId)
  )

  // Beat 4: ordinary advance, no intents.
  await setSeat(worldId, 'watcher')
  await measuredAdvance(
    'ordinary-advance',
    worldId,
    (await currentIndex(worldId)) + 1,
    undefined,
    {}
  )

  // Post-hoc source tracing under the watcher seat: committed intents per
  // scene plus whether Ash produced a committed answer to Wren's questions.
  for (const beat of beats) {
    if (!beat.run_id) continue
    const sources = await readCommittedSources(beat.run_id, {})
    beat.committed_sources = sources.scenes ?? []
    if (sources.error) note(`${beat.kind} scene read failed (retained): ${sources.error}`)
    if (beat.kind === 'question' || beat.kind === 'follow-up') {
      const answers = (beat.committed_sources ?? []).flatMap((s) =>
        (s.intents ?? [])
          .filter((i) => i.author_character_id === cast.ashId && i.family === 'communicate')
          .map((i) => ({ scene_id: s.scene_id, topic: i.topic }))
      )
      beat.npc_answer = {
        responder: 'Ash',
        committed: answers.length > 0,
        answers
      }
      note(`${beat.kind}: Ash committed answer: ${answers.length > 0}`)
    }
    checkpoint()
  }

  // Beat 5: reload — fresh reads only, proving committed beats retrieve.
  // Not counted among advances and never 'useful': it measures retrieval.
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
        validation: detail.ok ? 'accepted' : 'rejected',
        committed: 'not-applicable',
        narration: 'not-applicable',
        display: missing.length === 0 && detail.ok ? 'yes' : 'no'
      },
      reasons:
        missing.length === 0 ? [] : [`${missing.length} committed events absent after reload`],
      answer_usefulness: 'unevaluated'
    }
  })
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

function range(values) {
  const xs = values.filter((v) => typeof v === 'number' && Number.isFinite(v))
  if (xs.length === 0) return null
  return { n: xs.length, min: Math.min(...xs), max: Math.max(...xs) }
}

function buildReport(display, complete, fatal) {
  const advances = beats.filter((b) => b.kind !== 'reload')
  const committed = advances.filter((b) => b.classification?.advancement?.committed)
  return {
    tool: 'reliability-baseline',
    schema: 2,
    mode: MODE,
    title: TITLE,
    run: RUN,
    complete,
    fatal: fatal ?? null,
    started_at: startedAt,
    finished_at: new Date().toISOString(),
    api: API,
    story_id: storyId,
    world_id: worldId,
    pin: PIN_PROFILE ? { profile_id: PIN_PROFILE, revision: Number(PIN_REVISION) } : null,
    config_frozen: {
      note: 'prompts, models, budgets, and retry behavior unchanged during collection'
    },
    beats,
    display: display ?? { status: 'skipped', steps: [] },
    notes,
    summary: {
      advances: advances.length,
      advances_committed: committed.length,
      retrieval_complete: committed.filter((b) => b.classification?.advancement?.retrieval_complete)
        .length,
      provider_ok_advances: advances.filter((b) => b.classification?.layers?.provider === 'ok')
        .length,
      narration: {
        narrated: committed.filter((b) => b.classification?.layers?.narration === 'narrated')
          .length,
        fallback: committed.filter((b) => b.classification?.layers?.narration === 'fallback')
          .length,
        failed: committed.filter((b) => b.classification?.layers?.narration === 'failed').length
      },
      browser_display: display?.status ?? 'skipped',
      answer_usefulness: 'unevaluated',
      client_wall_ms: range(advances.map((b) => b.client_wall_ms)),
      slot_claim_ms: range(advances.map((b) => b.slot_claim_ms)),
      execution_ms: range(advances.map((b) => b.execution_ms)),
      timeline_read_ms: range(beats.map((b) => b.timelineWallMs)),
      narration_read_ms: range(beats.map((b) => b.narrationReadMs))
    }
  }
}

function checkpoint() {
  fs.writeFileSync(PARTIAL_PATH, JSON.stringify(buildReport(null, false, null), null, 2))
}

let startedAt = ''

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
    fs.writeFileSync(FINAL_PATH, JSON.stringify(buildReport(display, complete, fatal), null, 2))
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
      `[${b.kind}] wall=${b.client_wall_ms}ms slot-claim=${b.slot_claim_ms ?? '-'} ` +
        `exec=${b.execution_ms ?? '-'} committed=${c?.advancement?.committed ?? '?'} ` +
        `retrieval=${c?.advancement?.retrieval_complete ?? '?'} ` +
        `narration=${c?.layers?.narration} provider=${c?.layers?.provider} ` +
        `answer=${c?.answer_usefulness}` +
        `${(c?.reasons ?? []).length ? ` :: ${(c.reasons ?? []).join('; ')}` : ''}`
    )
  }
  const final = JSON.parse(fs.readFileSync(FINAL_PATH, 'utf8'))
  console.log(
    `wrote ${FINAL_PATH} complete=${final.complete} ` +
      `committed=${final.summary.advances_committed}/${final.summary.advances} ` +
      `browser=${final.summary.browser_display} answers=${final.summary.answer_usefulness}`
  )
  if (fatal !== null) process.exitCode = 1
}

await main()
