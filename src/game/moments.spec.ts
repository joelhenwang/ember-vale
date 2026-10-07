import { describe, expect, it } from 'vitest'
import type { BeatView, SceneArtView } from '../../content/clients/worldsim'
import { latestMoment, momentLines, momentTitle, momentWhen, readyMoments } from './moments'

function art(over: Partial<SceneArtView>): SceneArtView {
  return {
    picture_id: 'p',
    scene_id: 's',
    moment: 'arrival',
    caption: 'Mara arrives.',
    status: 'ready',
    asset_id: 'a',
    phase_index: 0,
    ...over
  }
}

function beat(over: Partial<BeatView>): BeatView {
  return { id: 'b', kind: 'narration', text: 'The tide turns.', source_event_id: 'e', ...over }
}

describe('moments', () => {
  it('shows only painted pictures, newest last', () => {
    const list = [
      art({ picture_id: '1' }),
      art({ picture_id: '2', status: 'pending', asset_id: null }),
      art({ picture_id: '3' })
    ]
    expect(readyMoments(list).map((a) => a.picture_id)).toEqual(['1', '3'])
    expect(latestMoment(list)?.picture_id).toBe('3')
    expect(latestMoment([])).toBeNull()
  })

  it('titles older pictures by their kind', () => {
    expect(momentTitle(art({ title: 'A bell beneath the tide' }))).toBe('A bell beneath the tide')
    expect(momentTitle(art({ moment: 'meeting', title: null }))).toBe('A first meeting')
    expect(momentTitle(art({ moment: 'odd', title: '  ' }))).toBe('A moment remembered')
  })

  it('says where and when', () => {
    expect(momentWhen(art({ phase_index: 8 }), 'Oarfall Harbor')).toBe(
      'Oarfall Harbor · Day 1, Night'
    )
    expect(momentWhen(art({ phase_index: 12 }))).toBe('Day 2, Morning')
  })

  it('puts spoken lines beside their speaker', () => {
    const speakers = new Map([['ash', { name: 'Ash', portraitUrl: '/ash.webp' }]])
    const lines = momentLines(
      [
        beat({}),
        beat({ kind: 'dialogue', speaker_id: 'ash', text: 'Well met.' }),
        beat({ kind: 'dialogue', speaker_id: 'stranger', text: 'Who goes?' }),
        beat({ kind: 'system', text: 'hidden' }),
        beat({ text: '   ' })
      ],
      speakers
    )
    expect(lines).toEqual([
      { kind: 'told', text: 'The tide turns.' },
      { kind: 'said', text: 'Well met.', speaker: { name: 'Ash', portraitUrl: '/ash.webp' } },
      { kind: 'said', text: 'Who goes?', speaker: { name: 'Someone', portraitUrl: null } }
    ])
  })
})
