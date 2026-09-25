/**
 * Testable core of the reliability baseline harness (REL-BASE-001).
 *
 * Pure orchestration over injected dependencies: no fetch, no filesystem,
 * no clock of its own. The CLI (`reliability-baseline.mjs`) wires real
 * dependencies; vitest covers the failure semantics here deterministically.
 */

export function transportKind(err) {
  const message = String(err)
  if (err instanceof Error && err.name === 'TimeoutError') return 'timeout'
  if (/fetch failed|ECONNREFUSED|ENOTFOUND|EHOSTUNREACH/i.test(message)) return 'connection'
  return 'transport'
}

/**
 * Classify one beat into outcome layers. HTTP 200 is validation 'accepted'
 * — never gameplay success. Display requires every committed event to be
 * retrievable, not merely one. Answer usefulness is always 'unevaluated'.
 */
export function classify(kind, advanceRes, modelRuns, timelineEntries, narrationBeats) {
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

export function summarizeCalls(calls) {
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

/**
 * NPC-answer detection over committed scene sources. Checks communicate
 * intents AND communicate reactions authored by the responder and addressed
 * to the asker (target match required). Reaction answers cite actual
 * narration citations: beats whose cited_fact_keys contain
 * `reaction:{reaction_id}`. Beats merely voiced by the responder are kept
 * separately as speaker_beats (association, not citation); intents have no
 * established citation key, so they carry speaker_beats only.
 */
export function findNpcAnswers(scenes, askerId, responderId) {
  const answers = []
  for (const s of scenes ?? []) {
    if (!s || s.error) continue
    const beats = s.narrations ?? []
    const speakerBeats = beats.filter((b) => b.speaker_id === responderId).map((b) => b.id)
    for (const i of s.intents ?? []) {
      if (
        i.author_character_id === responderId &&
        i.family === 'communicate' &&
        i.target_character_id === askerId
      ) {
        answers.push({
          source: 'intent',
          scene_id: s.scene_id,
          source_id: i.id ?? null,
          topic: i.topic ?? null,
          narration_citations: [],
          speaker_beats: speakerBeats
        })
      }
    }
    for (const r of s.reactions ?? []) {
      if (
        r.reactor_character_id === responderId &&
        r.family === 'communicate' &&
        r.target_character_id === askerId
      ) {
        const key = `reaction:${r.id}`
        answers.push({
          source: 'reaction',
          scene_id: s.scene_id,
          source_id: r.id ?? null,
          topic: r.topic ?? null,
          narration_citations: beats
            .filter((b) => (b.cited_fact_keys ?? []).includes(key))
            .map((b) => b.id),
          speaker_beats: speakerBeats
        })
      }
    }
  }
  return { committed: answers.length > 0, answers }
}

/**
 * Whether the scenario must stop mutating after this record. Any transport
 * error leaves the outcome unresolved (a delivered response is unconfirmed
 * and clock equality proves nothing), so no further seat change or advance
 * may follow. Rejections are known outcomes and do not halt reads.
 */
export function shouldHaltScenario(record) {
  return !!record?.transport_error
}

export function markBlocked(kinds, reason) {
  return kinds.map((kind) => ({ kind, status: 'blocked', reason }))
}

/**
 * Execute planned advance steps with halt-then-finalize semantics.
 *
 * steps: [{ kind, seat: { role, characterId } | null, ...stepFields }]
 * ops: { setSeat(seat), advance(step), finalize(attempted), note(msg) }
 *
 * Seat changes and advances stop at the first record for which
 * shouldHaltScenario holds; the remaining steps are returned as blocked
 * (never attempted). Blocked steps persist through ops.onBlocked BEFORE
 * finalization, so a failing finalizer cannot lose them. finalize ALWAYS
 * runs afterwards for the acknowledged attempts: it is read-only (source
 * tracing, reload reads) and must not change seats or advance. A throwing
 * finalizer is noted, never propagated. Returns { blockedSteps, attempted }.
 */
export async function runPlannedScenario(steps, ops) {
  const blockedSteps = []
  const attempted = []
  let halted = null
  for (const step of steps) {
    if (halted) {
      blockedSteps.push(...markBlocked([step.kind], halted))
      continue
    }
    if (step.seat) await ops.setSeat(step.seat)
    const record = await ops.advance(step)
    attempted.push(record)
    if (shouldHaltScenario(record)) {
      halted =
        `halted: ${record.kind} ${record.transport_error}, ` +
        `resolution ${record.resolution ?? 'unknown'}`
      ops.note?.(`${record.kind}: ${halted}; no further seat change or advance`)
    }
  }
  if (blockedSteps.length > 0) await ops.onBlocked?.(blockedSteps)
  try {
    await ops.finalize(attempted)
  } catch (err) {
    ops.note?.(
      `finalization failed (attempts and blocked steps retained): ${String(err).slice(0, 200)}`
    )
  }
  return { blockedSteps, attempted }
}

export function range(values) {
  const xs = values.filter((v) => typeof v === 'number' && Number.isFinite(v))
  if (xs.length === 0) return null
  return { n: xs.length, min: Math.min(...xs), max: Math.max(...xs) }
}

/**
 * Record one advance attempt with persistence-first semantics.
 *
 * The skeleton record is appended to store.beats and checkpointed BEFORE
 * the POST, so a transport failure can never lose the attempt. The POST
 * outcome (response or transport error with ACTUAL elapsed time) updates
 * the same record; each enrichment read (runs, timeline, narrations,
 * provider) is recorded separately and its failure retained on the record
 * instead of discarding the attempt.
 *
 * deps: { postAdvance, getRuns, getTimeline, getNarrations, getProvider, now }
 * spec: { kind, world, storyId, absoluteIndex, playerIntents, roleHeaders }
 * store: { beats: [], checkpoint() }
 */
export async function recordAdvance(deps, store, spec) {
  const record = {
    kind: spec.kind,
    absolute_index: spec.absoluteIndex,
    story_id: spec.storyId ?? null,
    world_id: spec.world,
    run_id: null,
    duplicate: null,
    client_wall_ms: null,
    slot_claim_ms: null,
    execution_ms: null,
    http_status: null,
    transport_error: null,
    transport_message: null,
    resolution: null,
    resolution_reason: null,
    scenes: [],
    provider: null,
    providerError: null,
    modelRuns: [],
    modelRunsError: null,
    callSummary: summarizeCalls([]),
    timelineEntries: 0,
    timelineWallMs: null,
    timelineError: null,
    narrationBeats: 0,
    narrationReadMs: null,
    narrationError: null,
    committed_sources: [],
    classification: null
  }
  store.beats.push(record)
  store.checkpoint()

  const t0 = deps.now()
  let res
  try {
    const body = { world_id: spec.world, absolute_index: spec.absoluteIndex }
    if (spec.playerIntents !== undefined) body.player_intents = spec.playerIntents
    res = await deps.postAdvance(body, spec.roleHeaders)
  } catch (err) {
    record.transport_error = transportKind(err)
    record.transport_message = String(err).slice(0, 300)
    record.client_wall_ms = Math.max(0, Math.round(deps.now() - t0))
    // Unresolved until run/event inspection establishes otherwise: the POST
    // may have committed server-side without delivering a response, and no
    // clock reading taken here can settle that.
    record.resolution = 'unresolved'
    record.resolution_reason =
      'transport failed before a response arrived; commit state unknown until inspected'
    record.classification = classify(spec.kind, {
      transport_error: record.transport_error,
      wallMs: record.client_wall_ms,
      message: record.transport_message
    })
    store.checkpoint()
    return record
  }
  record.client_wall_ms = Math.max(0, Math.round(deps.now() - t0))
  record.http_status = res.status
  if (typeof res.slotClaimMs === 'number' && Number.isFinite(res.slotClaimMs))
    record.slot_claim_ms = res.slotClaimMs
  if (typeof res.executionMs === 'number' && Number.isFinite(res.executionMs))
    record.execution_ms = res.executionMs

  if (!res.ok) {
    record.rejection = res.errorBody ?? ''
    record.classification = classify(spec.kind, res, [], [], [])
    store.checkpoint()
    return record
  }
  record.run_id = res.json?.run_id ?? null
  record.duplicate = res.json?.duplicate ?? null
  record.scenes = (res.json?.scenes ?? []).map((s) => ({
    scene_id: s.scene_id,
    event_id: s.event_id,
    resolution_outcome: s.resolution_outcome,
    narration: s.narration
  }))
  store.checkpoint()

  let timelineEntries = []
  try {
    const runs = record.run_id
      ? await deps.getRuns(record.run_id)
      : { error: 'no run_id', calls: [] }
    record.modelRuns = runs.calls ?? []
    record.modelRunsError = runs.error ?? null
    if (runs.error) record.readErrors = [...(record.readErrors ?? []), `model-runs: ${runs.error}`]
  } catch (err) {
    record.modelRunsError = `${transportKind(err)}: ${String(err).slice(0, 200)}`
    record.readErrors = [...(record.readErrors ?? []), `model-runs: ${record.modelRunsError}`]
  }
  record.callSummary = summarizeCalls(record.modelRuns)
  try {
    const timeline = await deps.getTimeline(spec.world)
    timelineEntries = timeline.entries ?? []
    record.timelineEntries = timelineEntries.length
    record.timelineWallMs = timeline.wallMs ?? null
    if (timeline.error)
      record.readErrors = [...(record.readErrors ?? []), `timeline: ${timeline.error}`]
  } catch (err) {
    record.timelineError = `${transportKind(err)}: ${String(err).slice(0, 200)}`
    record.readErrors = [...(record.readErrors ?? []), `timeline: ${record.timelineError}`]
  }
  let narrationBeats = []
  try {
    const narrations = await deps.getNarrations(
      record.scenes.map((s) => s.scene_id).filter(Boolean),
      spec.roleHeaders
    )
    narrationBeats = narrations.beats ?? []
    record.narrationBeats = narrationBeats.length
    record.narrationReadMs = narrations.wallMs ?? null
  } catch (err) {
    record.narrationError = `${transportKind(err)}: ${String(err).slice(0, 200)}`
    record.readErrors = [...(record.readErrors ?? []), `narrations: ${record.narrationError}`]
  }
  try {
    record.provider = await deps.getProvider(spec.world)
  } catch (err) {
    record.providerError = `${transportKind(err)}: ${String(err).slice(0, 200)}`
    record.readErrors = [...(record.readErrors ?? []), `provider: ${record.providerError}`]
  }

  record.classification = classify(
    spec.kind,
    res,
    record.modelRuns,
    timelineEntries,
    narrationBeats
  )
  store.checkpoint()
  return record
}

export function buildReport({ beats, notes, display, complete, fatal, meta, blockedSteps }) {
  const advances = beats.filter((b) => b.kind !== 'reload')
  const committed = advances.filter((b) => b.classification?.advancement?.committed)
  const blocked = blockedSteps ?? []
  return {
    tool: 'reliability-baseline',
    schema: 4,
    mode: meta.mode,
    title: meta.title,
    run: meta.run,
    complete,
    fatal: fatal ?? null,
    started_at: meta.startedAt,
    finished_at: meta.finishedAt,
    api: meta.api,
    story_id: meta.storyId,
    world_id: meta.worldId,
    pin: meta.pin ?? null,
    config_frozen: {
      note: 'prompts, models, budgets, and retry behavior unchanged during collection'
    },
    beats,
    blocked_steps: blocked,
    display: display ?? { status: 'skipped', steps: [] },
    notes,
    summary: {
      advances: advances.length,
      advances_committed: committed.length,
      blocked: blocked.length,
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
