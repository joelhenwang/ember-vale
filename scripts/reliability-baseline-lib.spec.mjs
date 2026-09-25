/**
 * Deterministic harness semantics (REL-BASE-001): attempts persist first,
 * transport outcomes carry actual timing, read failures never discard an
 * attempt, and NPC-answer detection covers reactions with target checks.
 */
import { describe, expect, it, vi } from 'vitest'
import {
  buildReport,
  classify,
  findNpcAnswers,
  markBlocked,
  recordAdvance,
  runPlannedScenario,
  shouldHaltScenario,
  transportKind
} from './reliability-baseline-lib.mjs'

const spec = {
  kind: 'question',
  world: 'world-1',
  storyId: 'story-1',
  absoluteIndex: 7,
  playerIntents: { wren: { family: 'communicate' } },
  roleHeaders: {}
}

const okDeps = () => ({
  postAdvance: async () => ({
    ok: true,
    status: 200,
    json: {
      run_id: 'run-1',
      duplicate: false,
      scenes: [
        { scene_id: 's1', event_id: 'e1', resolution_outcome: 'success', narration: 'fallback' }
      ]
    },
    slotClaimMs: 9,
    executionMs: 400,
    wallMs: 450
  }),
  getRuns: async () => ({ calls: [] }),
  getTimeline: async () => ({ entries: [{ event_id: 'e1' }], wallMs: 20 }),
  getNarrations: async () => ({ beats: [{ text: 'Ash nods.' }], wallMs: 30 }),
  getProvider: async () => ({ effective_adapter: 'fake' }),
  now: () => performance.now()
})

const store = () => {
  const beats = []
  return { beats, checkpoint: vi.fn() }
}

describe('transportKind', () => {
  it('distinguishes timeout, connection, and other transport errors', () => {
    const timeout = new Error('The operation was aborted')
    timeout.name = 'TimeoutError'
    expect(transportKind(timeout)).toBe('timeout')
    expect(transportKind(new TypeError('fetch failed'))).toBe('connection')
    expect(transportKind(new Error('ECONNREFUSED 127.0.0.1:8101'))).toBe('connection')
    expect(transportKind(new Error('unexpected status in test'))).toBe('transport')
  })
})

describe('recordAdvance persistence', () => {
  it('retains a POST timeout with actual elapsed time, not a hardcoded cap', async () => {
    const s = store()
    const deps = okDeps()
    deps.postAdvance = async () => {
      await new Promise((r) => setTimeout(r, 60))
      const err = new Error('The operation was aborted')
      err.name = 'TimeoutError'
      throw err
    }
    const record = await recordAdvance(deps, s, spec)
    expect(s.beats).toHaveLength(1)
    expect(s.beats[0]).toBe(record)
    expect(record.transport_error).toBe('timeout')
    expect(record.client_wall_ms).toBeGreaterThanOrEqual(40)
    expect(record.client_wall_ms).toBeLessThan(10000)
    expect(record.absolute_index).toBe(7)
    expect(record.classification.reasons.join(' ')).toMatch(/timeout/)
    expect(s.checkpoint.mock.calls.length).toBeGreaterThanOrEqual(2)
  })

  it('retains an immediate connection refusal as connection, not timeout', async () => {
    const s = store()
    const deps = okDeps()
    deps.postAdvance = async () => {
      throw new TypeError('fetch failed')
    }
    const record = await recordAdvance(deps, s, spec)
    expect(s.beats).toHaveLength(1)
    expect(record.transport_error).toBe('connection')
    expect(typeof record.client_wall_ms).toBe('number')
    expect(record.run_id).toBeNull()
  })

  it('persists the skeleton before the POST resolves', async () => {
    const s = store()
    let release
    const gate = new Promise((r) => {
      release = r
    })
    const deps = okDeps()
    deps.postAdvance = () => gate.then(() => okDeps().postAdvance())
    const pending = recordAdvance(deps, s, spec)
    await new Promise((r) => setTimeout(r, 10))
    expect(s.beats).toHaveLength(1)
    expect(s.beats[0].run_id).toBeNull()
    expect(s.checkpoint).toHaveBeenCalled()
    release()
    const record = await pending
    expect(record.run_id).toBe('run-1')
  })

  it('keeps a successful POST when a diagnostic GET fails', async () => {
    const s = store()
    const deps = okDeps()
    deps.getRuns = async () => {
      throw new Error('diagnostic store unavailable')
    }
    const record = await recordAdvance(deps, s, spec)
    expect(s.beats).toHaveLength(1)
    expect(record.http_status).toBe(200)
    expect(record.run_id).toBe('run-1')
    expect(record.classification.advancement.committed).toBe(true)
    expect(record.modelRunsError).toMatch(/diagnostic store unavailable/)
    expect(record.readErrors.join(' ')).toMatch(/model-runs/)
    // No traced calls are known, so the provider layer cannot claim success.
    expect(record.classification.layers.provider).toBe('no-calls')
  })
})

describe('classify retrieval', () => {
  it('requires every committed event, naming the missing ones', () => {
    const res = {
      ok: true,
      status: 200,
      json: {
        duplicate: false,
        scenes: [
          { scene_id: 's1', event_id: 'e1', narration: 'fallback' },
          { scene_id: 's2', event_id: 'e2', narration: 'fallback' }
        ]
      }
    }
    const out = classify('travel', res, [], [{ event_id: 'e1' }], [{ text: 'Dawn.' }])
    expect(out.layers.display).toBe('no')
    expect(out.reasons.join(' ')).toMatch(/e2/)
    expect(out.advancement.retrieval_complete).toBe(false)
  })
})

describe('findNpcAnswers', () => {
  const scenes = [
    {
      scene_id: 's1',
      intents: [
        {
          id: 'i-wren',
          author_character_id: 'wren',
          family: 'communicate',
          target_character_id: 'ash',
          topic: 'Q?'
        },
        {
          id: 'i-ash',
          author_character_id: 'ash',
          family: 'wait',
          target_character_id: null,
          topic: null
        }
      ],
      reactions: [
        {
          id: 'r-ash',
          reactor_character_id: 'ash',
          family: 'communicate',
          target_character_id: 'wren',
          topic: 'The bell meant dawn.'
        },
        {
          id: 'r-other',
          reactor_character_id: 'ash',
          family: 'communicate',
          target_character_id: 'birch',
          topic: 'Unrelated aside.'
        }
      ],
      narrations: [
        { id: 'b1', speaker_id: 'ash', cited_fact_keys: ['reaction:r-ash'] },
        { id: 'b2', speaker_id: 'wren', cited_fact_keys: [] }
      ]
    }
  ]

  it('finds a reaction answer when the decision was WAIT', () => {
    const out = findNpcAnswers(scenes, 'wren', 'ash')
    expect(out.committed).toBe(true)
    expect(out.answers).toHaveLength(1)
    expect(out.answers[0]).toMatchObject({ source: 'reaction', source_id: 'r-ash' })
    expect(out.answers[0].narration_citations).toEqual(['b1'])
    expect(out.answers[0].speaker_beats).toEqual(['b1'])
  })

  it('keeps a committed answer when narration retrieval failed', () => {
    const noNarrations = [
      {
        scene_id: 's1',
        narrationError: 'timeout: narration read failed',
        intents: [
          {
            id: 'i-ash',
            author_character_id: 'ash',
            family: 'wait',
            target_character_id: null,
            topic: null
          }
        ],
        reactions: [
          {
            id: 'r-ash',
            reactor_character_id: 'ash',
            family: 'communicate',
            target_character_id: 'wren',
            topic: 'The bell meant dawn.'
          }
        ],
        narrations: []
      }
    ]
    const out = findNpcAnswers(noNarrations, 'wren', 'ash')
    expect(out.committed).toBe(true)
    expect(out.answers[0]).toMatchObject({ source: 'reaction', source_id: 'r-ash' })
    expect(out.answers[0].narration_citations).toEqual([])
    expect(out.answers[0].speaker_beats).toEqual([])
  })

  it('matches citations per reaction, not per speaker', () => {
    const two = [
      {
        scene_id: 's1',
        intents: [],
        reactions: [
          {
            id: 'r1',
            reactor_character_id: 'ash',
            family: 'communicate',
            target_character_id: 'wren',
            topic: 'First.'
          },
          {
            id: 'r2',
            reactor_character_id: 'ash',
            family: 'communicate',
            target_character_id: 'wren',
            topic: 'Second.'
          }
        ],
        narrations: [
          { id: 'b1', speaker_id: 'ash', cited_fact_keys: ['reaction:r1'] },
          { id: 'b2', speaker_id: 'ash', cited_fact_keys: ['reaction:r2'] },
          { id: 'b3', speaker_id: 'ash', cited_fact_keys: ['attempt:wait'] }
        ]
      }
    ]
    const out = findNpcAnswers(two, 'wren', 'ash')
    expect(out.committed).toBe(true)
    expect(out.answers).toHaveLength(2)
    const [first, second] = out.answers
    expect(first.source_id).toBe('r1')
    expect(first.narration_citations).toEqual(['b1'])
    expect(second.source_id).toBe('r2')
    expect(second.narration_citations).toEqual(['b2'])
    expect(first.speaker_beats).toEqual(['b1', 'b2', 'b3'])
  })

  it('still traces a targeted communicate intent', () => {
    const withIntent = [
      {
        scene_id: 's1',
        intents: [
          {
            id: 'i-ash-says',
            author_character_id: 'ash',
            family: 'communicate',
            target_character_id: 'wren',
            topic: 'Follow me.'
          }
        ],
        reactions: []
      }
    ]
    const out = findNpcAnswers(withIntent, 'wren', 'ash')
    expect(out.committed).toBe(true)
    expect(out.answers[0]).toMatchObject({ source: 'intent', source_id: 'i-ash-says' })
  })

  it('reports no answer when Ash stays silent', () => {
    const silent = [
      {
        scene_id: 's1',
        intents: [{ author_character_id: 'ash', family: 'wait', target_character_id: null }],
        reactions: []
      }
    ]
    expect(findNpcAnswers(silent, 'wren', 'ash')).toEqual({ committed: false, answers: [] })
  })
})

describe('buildReport', () => {
  it('retains every attempt with identity, timing, and known outcome', () => {
    const failed = {
      kind: 'travel',
      world_id: 'w',
      absolute_index: 5,
      run_id: null,
      client_wall_ms: 63,
      transport_error: 'connection',
      classification: { layers: { provider: 'unknown' }, advancement: { committed: false } }
    }
    const committed = {
      kind: 'question',
      world_id: 'w',
      absolute_index: 6,
      run_id: 'run-9',
      client_wall_ms: 400,
      slot_claim_ms: 9,
      execution_ms: 380,
      classification: {
        layers: { provider: 'ok', narration: 'fallback' },
        advancement: { committed: true, retrieval_complete: true, narration: 'fallback' }
      }
    }
    const report = buildReport({
      beats: [failed, committed],
      notes: [],
      display: { status: 'skipped', steps: [] },
      complete: false,
      fatal: 'connection: fetch failed',
      meta: {
        mode: 'live',
        title: 't',
        run: 'r1',
        startedAt: 's',
        finishedAt: 'f',
        api: 'a',
        storyId: 'st',
        worldId: 'w',
        pin: null
      }
    })
    expect(report.complete).toBe(false)
    expect(report.beats).toHaveLength(2)
    expect(report.summary.advances).toBe(2)
    expect(report.summary.advances_committed).toBe(1)
    expect(report.beats[0].transport_error).toBe('connection')
    expect(report.beats[1].run_id).toBe('run-9')
  })

  it('carries blocked steps separately from attempted advances', () => {
    const report = buildReport({
      beats: [],
      notes: [],
      display: { status: 'skipped', steps: [] },
      complete: true,
      fatal: null,
      blockedSteps: markBlocked(['follow-up', 'ordinary-advance'], 'halted: unresolved timeout'),
      meta: {
        mode: 'live',
        title: 't',
        run: 'r1',
        startedAt: 's',
        finishedAt: 'f',
        api: 'a',
        storyId: 'st',
        worldId: 'w',
        pin: null
      }
    })
    expect(report.blocked_steps).toHaveLength(2)
    expect(report.blocked_steps[0]).toEqual({
      kind: 'follow-up',
      status: 'blocked',
      reason: 'halted: unresolved timeout'
    })
    expect(report.summary.blocked).toBe(2)
    expect(report.summary.advances).toBe(0)
  })
})

describe('runPlannedScenario finalizes after a halt', () => {
  const travelRec = {
    kind: 'travel',
    world_id: 'w',
    absolute_index: 7,
    run_id: 'r1',
    client_wall_ms: 400,
    transport_error: null,
    classification: {
      layers: { provider: 'ok', narration: 'fallback' },
      advancement: { committed: true, retrieval_complete: true, narration: 'fallback' },
      answer_usefulness: 'unevaluated'
    }
  }
  const questionRec = {
    kind: 'question',
    world_id: 'w',
    absolute_index: 8,
    run_id: 'r2',
    client_wall_ms: 500,
    transport_error: null,
    classification: {
      layers: { provider: 'degraded', narration: 'fallback' },
      advancement: { committed: true, retrieval_complete: true, narration: 'fallback' },
      answer_usefulness: 'unevaluated'
    }
  }
  const timeoutRec = {
    kind: 'follow-up',
    world_id: 'w',
    absolute_index: 9,
    run_id: null,
    client_wall_ms: 180001,
    transport_error: 'timeout',
    resolution: 'unresolved',
    post_error_clock: 9,
    commit_ambiguous: false,
    classification: { layers: {}, reasons: ['timeout'] }
  }

  it('travel ok, question answered, follow-up timeout: blocks ordinary, keeps the answer', async () => {
    const calls = []
    const attempted = []
    const ops = {
      setSeat: async (seat) => {
        calls.push(['seat', seat.role])
        return { ok: true }
      },
      advance: async (step) => {
        calls.push(['advance', step.kind])
        const rec =
          step.kind === 'travel' ? travelRec : step.kind === 'question' ? questionRec : timeoutRec
        attempted.push(rec)
        return rec
      },
      finalize: async (records) => {
        calls.push(['finalize'])
        // Read-only finalization for the acknowledged question run.
        const q = records.find((r) => r.kind === 'question')
        q.committed_sources = [
          {
            scene_id: 's1',
            intents: [
              {
                id: 'i-wren',
                author_character_id: 'wren',
                family: 'communicate',
                target_character_id: 'ash',
                topic: 'Q?'
              }
            ],
            reactions: [
              {
                id: 'r-ash',
                reactor_character_id: 'ash',
                family: 'communicate',
                target_character_id: 'wren',
                topic: 'The bell meant dawn.'
              }
            ],
            narrations: [{ id: 'b1', speaker_id: 'ash', cited_fact_keys: ['reaction:r-ash'] }]
          }
        ]
        const found = findNpcAnswers(q.committed_sources, 'wren', 'ash')
        q.npc_answer = {
          asker: 'Wren',
          responder: 'Ash',
          status: found.committed ? 'answered' : 'no-answer',
          narration_retrieval: 'complete',
          answers: found.answers
        }
        records.push({ kind: 'reload', client_wall_ms: 150 })
      },
      note: () => {}
    }
    const steps = [
      { kind: 'travel', seat: null },
      { kind: 'question', seat: { role: 'player' } },
      { kind: 'follow-up', seat: null },
      { kind: 'ordinary-advance', seat: { role: 'watcher' } }
    ]
    const { blockedSteps } = await runPlannedScenario(steps, ops)

    // No seat change or advance after the unresolved timeout.
    expect(calls.filter((c) => c[0] === 'advance').map((c) => c[1])).toEqual([
      'travel',
      'question',
      'follow-up'
    ])
    expect(calls.filter((c) => c[0] === 'seat').map((c) => c[1])).toEqual(['player'])
    expect(blockedSteps).toEqual([
      {
        kind: 'ordinary-advance',
        status: 'blocked',
        reason: expect.stringMatching(/follow-up timeout/)
      }
    ])
    // Read-only finalization still ran for the acknowledged runs.
    expect(calls).toContainEqual(['finalize'])

    // The question's answer and citations survive in the final report.
    const report = buildReport({
      beats: attempted,
      notes: [],
      display: { status: 'skipped', steps: [] },
      complete: true,
      fatal: null,
      blockedSteps,
      meta: {
        mode: 'live',
        title: 't',
        run: 'r1',
        startedAt: 's',
        finishedAt: 'f',
        api: 'a',
        storyId: 'st',
        worldId: 'w',
        pin: null
      }
    })
    const q = report.beats.find((b) => b.kind === 'question')
    expect(q.npc_answer.status).toBe('answered')
    expect(q.npc_answer.answers).toHaveLength(1)
    expect(q.npc_answer.answers[0]).toMatchObject({
      source: 'reaction',
      source_id: 'r-ash',
      narration_citations: ['b1']
    })
    expect(report.summary.advances).toBe(3)
    expect(report.summary.advances_committed).toBe(2)
    expect(report.summary.blocked).toBe(1)
  })
})

describe('unresolved timeouts halt mutation', () => {
  it('marks a timeout unresolved even when the clock did not advance', async () => {
    const s = store()
    const deps = okDeps()
    deps.postAdvance = async () => {
      await new Promise((r) => setTimeout(r, 30))
      const err = new Error('The operation was aborted')
      err.name = 'TimeoutError'
      throw err
    }
    const record = await recordAdvance(deps, s, spec)
    expect(record.transport_error).toBe('timeout')
    expect(record.resolution).toBe('unresolved')
    // Clock equality proves nothing: halt anyway, with no seat change or
    // further advance issued by this record alone.
    expect(shouldHaltScenario(record)).toBe(true)
    expect(markBlocked(['ordinary-advance'], 'halted after unresolved follow-up')).toEqual([
      { kind: 'ordinary-advance', status: 'blocked', reason: 'halted after unresolved follow-up' }
    ])
  })

  it('does not halt on a known rejection', async () => {
    const s = store()
    const deps = okDeps()
    deps.postAdvance = async () => ({
      ok: false,
      status: 409,
      json: null,
      errorBody: 'previous phase is scenes_assembled',
      wallMs: 40
    })
    const record = await recordAdvance(deps, s, spec)
    expect(record.transport_error).toBeNull()
    expect(record.resolution).toBeNull()
    expect(record.classification.layers.validation).toBe('rejected')
    expect(shouldHaltScenario(record)).toBe(false)
  })
})
