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
  recordAdvance,
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
        { id: 'b1', speaker_id: 'ash' },
        { id: 'b2', speaker_id: 'wren' }
      ]
    }
  ]

  it('finds a reaction answer when the decision was WAIT', () => {
    const out = findNpcAnswers(scenes, 'wren', 'ash')
    expect(out.committed).toBe(true)
    expect(out.answers).toHaveLength(1)
    expect(out.answers[0]).toMatchObject({ source: 'reaction', source_id: 'r-ash' })
    expect(out.answers[0].narration_citations).toEqual(['b1'])
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
})
