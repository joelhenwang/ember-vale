import { describe, expect, it } from 'vitest'
import {
  packCharacter,
  packWorld,
  slugPlaceKey,
  unpackCharacter,
  unpackWorld
} from './studioFields'
import type { CharacterDraft, WorldDraft } from './studio'

const charDraft: CharacterDraft = {
  want: 'Find their missing brother.',
  avoid: 'Making promises they cannot keep.',
  pressure: 'Jokes first, then direct.',
  contradiction: 'Distrusts authority; wants approval.',
  styleTags: ['Brief sentences', 'Dry humor'],
  withStrangers: 'Friendly, but guarded',
  whenTheyCare: 'Practical help.',
  exampleLine: 'I never said it was a good road.',
  boundaries: 'Will not lie for anyone.',
  secretFear: 'Being forgotten.',
  appearanceSaved: false
}

function worldDraft(): WorldDraft {
  return {
    terrain: ['River valley', 'Woodland'],
    climate: 'Temperate',
    architecture: 'Timber and pale stone.',
    details: 'Mossy riverbanks.',
    exclusions: 'Modern machinery',
    places: [
      {
        id: 'hearth',
        name: 'Hearth',
        type: 'Village inn',
        purpose: 'Warm rest.',
        appearance: 'Low beams.',
        landmark: 'The fire',
        connectedTo: 'Market',
        sounds: 'Kettles.'
      }
    ],
    activePlace: 'hearth'
  }
}

describe('studio field bridge', () => {
  it('packs the character form into valid payload keys only', () => {
    const packed = packCharacter(charDraft)
    expect(Object.keys(packed).sort()).toEqual(['background', 'personality'])
    expect(packed.personality).toContain('Find their missing brother.')
    expect(packed.background).toContain('Will not lie for anyone.')
  })

  it('round-trips the character form through packed fields', () => {
    const restored = unpackCharacter(packCharacter(charDraft) as Record<string, unknown>)
    expect(restored).toMatchObject({
      want: charDraft.want,
      avoid: charDraft.avoid,
      pressure: charDraft.pressure,
      contradiction: charDraft.contradiction,
      withStrangers: charDraft.withStrangers,
      whenTheyCare: charDraft.whenTheyCare,
      exampleLine: charDraft.exampleLine,
      styleTags: charDraft.styleTags,
      boundaries: charDraft.boundaries,
      secretFear: charDraft.secretFear
    })
  })

  it('round-trips multi-line prose via continuation lines', () => {
    const draft = { ...charDraft, want: 'Line one.\nLine two.' }
    const restored = unpackCharacter(packCharacter(draft) as Record<string, unknown>)
    expect(restored.want).toBe('Line one.\nLine two.')
  })

  it('packs the world form into valid payload keys only', () => {
    const packed = packWorld(worldDraft())
    expect(Object.keys(packed).sort()).toEqual([
      'description',
      'locations',
      'lore',
      'starting_location_key'
    ])
    expect(packed.description).toBe('Mossy riverbanks.')
    expect(packed.starting_location_key).toBe('hearth')
    expect(packed.locations).toHaveLength(1)
  })

  it('round-trips the world form through packed fields', () => {
    const draft = worldDraft()
    const restored = unpackWorld(packWorld(draft) as unknown as Record<string, unknown>)
    expect(restored.details).toBe(draft.details)
    expect(restored.terrain).toEqual(draft.terrain)
    expect(restored.climate).toBe(draft.climate)
    expect(restored.architecture).toBe(draft.architecture)
    expect(restored.exclusions).toBe(draft.exclusions)
    expect(restored.places?.[0]).toMatchObject({
      name: 'Hearth',
      type: 'Village inn',
      purpose: 'Warm rest.',
      landmark: 'The fire'
    })
    expect(restored.activePlace).toBe(restored.places?.[0]?.id)
  })

  it('slugs place keys deterministically', () => {
    expect(slugPlaceKey('The Lantern Point', 'place-1')).toBe('the-lantern-point')
    expect(slugPlaceKey('!!!', 'place-2')).toBe('place-2')
  })
})
