/**
 * Deterministic fixtures for the room's attribution rule: spoken lines
 * come from persisted DIALOGUE beats only. Scene resolution outcome never
 * proves an individual utterance committed, so no speech — and no "not
 * committed" — is inferred from it. Shapes mirror the live envelopes.
 */
import { describe, expect, it } from 'vitest'
import type { BeatView, SceneDetail } from '../../../content/clients/worldsim'
import {
  eventLabel,
  collectScenePointers,
  communicateTopics,
  isAttemptRecord,
  isQuotedSpeech,
  readScene,
  sceneCitations
} from './beatReading'

const WREN = 'char-wren'
const ASH = 'char-ash'

function scene(
  overrides: Partial<SceneDetail> & {
    intents?: SceneDetail['intents']
    reactions?: SceneDetail['reactions']
  } = {},
  resolution: SceneDetail['resolution'] = { outcome: 'success', rationale: 'ok', resolver: 'model' }
): SceneDetail {
  return {
    id: 'scene-1',
    world_id: 'world-1',
    phase_run_id: 'run-1',
    status: 'committed',
    beat_budget: 1,
    event_id: 'e1',
    participants: [],
    intents: [],
    attempts: [],
    reactions: [],
    resolution,
    ...overrides
  } as SceneDetail
}

function beat(kind: string, text: string, speaker: string | null = null): BeatView {
  return { id: `b-${kind}-${text.length}`, kind, text, speaker_id: speaker, source_event_id: 'e1' }
}

function communicateIntent(
  topic: string | null,
  author = WREN,
  target = ASH
): NonNullable<SceneDetail['intents']>[number] {
  return {
    id: `intent-${topic ?? 'redacted'}`,
    author_character_id: author,
    family: 'communicate',
    detail: topic === null ? null : { topic, target_character_id: target }
  }
}

describe('beatReading attribution', () => {
  it('a quoted intent plus scene success does not manufacture dialogue', () => {
    const reading = readScene(
      scene({ intents: [communicateIntent('"Dawn bell means buyers."')] }),
      [beat('narration', 'Rain on the stones.')]
    )
    expect(reading.blocks.filter((b) => b.type === 'say')).toHaveLength(0)
    expect(reading.blocks.map((b) => b.type)).toEqual(['prose'])
    expect(reading.records).toEqual([
      { speakerId: WREN, targetId: ASH, topic: '"Dawn bell means buyers."', quoted: true }
    ])
  })

  it('persisted dialogue stays visible with failure/impossible outcomes', () => {
    for (const outcome of ['failure', 'impossible']) {
      const reading = readScene(
        scene(
          { intents: [communicateIntent('Market stalls')] },
          { outcome, rationale: 'no', resolver: 'model' }
        ),
        [beat('dialogue', 'Stalls open at dawn.', ASH)]
      )
      expect(reading.blocks).toContainEqual({
        type: 'say',
        speakerId: ASH,
        text: 'Stalls open at dawn.'
      })
    }
  })

  it('missing narration causes no commitment claim either way', () => {
    const reading = readScene(scene({ intents: [communicateIntent('"Hello?"')] }, null), [])
    expect(reading.blocks).toHaveLength(0)
    expect(reading.records).toEqual([
      { speakerId: WREN, targetId: ASH, topic: '"Hello?"', quoted: true }
    ])
  })

  it('unquoted topics stay records, never speaker-labelled dialogue', () => {
    const reading = readScene(scene({ intents: [communicateIntent('Market stalls')] }), [
      beat('narration', 'Rain on the stones.')
    ])
    expect(reading.blocks.filter((b) => b.type === 'say')).toHaveLength(0)
    expect(reading.records).toEqual([
      { speakerId: WREN, targetId: ASH, topic: 'Market stalls', quoted: false }
    ])
  })

  it('renders nothing for redacted (perspective-hidden) detail', () => {
    const reading = readScene(scene({ intents: [communicateIntent(null)] }), [])
    expect(reading.blocks).toHaveLength(0)
    expect(reading.records).toHaveLength(0)
    expect(communicateTopics(scene({ intents: [communicateIntent(null)] }))).toHaveLength(0)
  })

  it('prefers voiced dialogue and skips no duplicate intent summary', () => {
    const reading = readScene(
      scene({
        reactions: [
          {
            id: 'r1',
            reactor_character_id: ASH,
            family: 'communicate',
            detail: { topic: 'Market stalls', target_character_id: WREN }
          }
        ]
      }),
      [beat('dialogue', 'Stalls open at dawn.', ASH)]
    )
    expect(reading.blocks).toHaveLength(1)
    expect(reading.blocks[0]).toEqual({ type: 'say', speakerId: ASH, text: 'Stalls open at dawn.' })
    expect(reading.records).toHaveLength(1)
  })

  it('keeps narration and dialogue in stored order, never grouped', () => {
    const reading = readScene(scene(), [
      beat('narration', 'First paragraph.'),
      beat('dialogue', 'Spoken line.', ASH),
      beat('narration', 'Second paragraph.')
    ])
    expect(reading.blocks.map((b) => b.type)).toEqual(['prose', 'say', 'prose'])
  })

  it('excludes attempt records from the reading flow', () => {
    expect(isAttemptRecord('attempt:wait: Ash waits')).toBe(true)
    expect(isAttemptRecord('Ash waits.')).toBe(false)
    const reading = readScene(scene(), [beat('narration', 'attempt:wait: Ash waits')])
    expect(reading.blocks).toHaveLength(0)
  })

  it('detects explicit quotation', () => {
    expect(isQuotedSpeech('"Hello."')).toBe(true)
    expect(isQuotedSpeech('Market stalls')).toBe(false)
    expect(isQuotedSpeech('"')).toBe(false)
    expect(isQuotedSpeech('')).toBe(false)
  })
})

describe('collectScenePointers', () => {
  const refs = {
    'e-a': { sceneIds: ['scene-a'], fallback: false },
    'e-b': { sceneIds: ['scene-b1', 'scene-b2'], fallback: true }
  }

  it('aggregates every distinct scene pointer in timeline order', () => {
    const entries = [
      { event_id: 'e-tick' },
      { event_id: 'e-a' },
      { event_id: 'e-tick-2' },
      { event_id: 'e-b' }
    ]
    expect(collectScenePointers(entries, refs)).toEqual([
      { eventId: 'e-a', sceneIds: ['scene-a'], fallback: false },
      { eventId: 'e-b', sceneIds: ['scene-b1', 'scene-b2'], fallback: true }
    ])
  })

  it('dedupes repeated entries and skips pointer-less rows', () => {
    const entries = [{ event_id: 'e-a' }, { event_id: 'e-a' }, { event_id: 'e-none' }]
    expect(collectScenePointers(entries, refs)).toEqual([
      { eventId: 'e-a', sceneIds: ['scene-a'], fallback: false }
    ])
  })

  it('skips pointers with no scenes', () => {
    expect(
      collectScenePointers([{ event_id: 'e-x' }], { 'e-x': { sceneIds: [], fallback: false } })
    ).toEqual([])
  })
})

describe('sceneCitations', () => {
  it('dedupes cited keys in order', () => {
    const narration = [
      beat('dialogue', 'Hi.', ASH),
      { ...beat('narration', 'Prose.'), cited_fact_keys: ['mill.hours', 'market.bell'] },
      { ...beat('narration', 'More.'), cited_fact_keys: ['mill.hours'] }
    ]
    expect(sceneCitations(narration)).toEqual(['mill.hours', 'market.bell'])
  })
})

describe('event labels', () => {
  it('names story events in plain words', () => {
    expect(eventLabel('action_resolved')).toBe('')
    expect(eventLabel('world_seeded')).toBe('The story begins')
    expect(eventLabel('something_new')).toBe('something new')
  })
})
