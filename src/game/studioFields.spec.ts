import { describe, expect, it } from 'vitest'
import {
  normalizePlaceKey,
  packCharacter,
  packWorld,
  removeWorldPlace,
  renamePlaceReferences,
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
  appearanceSaved: false,
  personalityExtra: '',
  backgroundExtra: ''
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
        key: 'hearth',
        name: 'Hearth',
        type: 'Village inn',
        purpose: 'Warm rest.',
        appearance: 'Low beams.',
        landmark: 'The fire',
        connectedTo: 'Market',
        sounds: 'Kettles.',
        detailExtra: ''
      },
      {
        id: 'market',
        key: 'market_east',
        name: 'Market',
        type: 'Open-air market',
        purpose: 'Trade.',
        appearance: 'Stalls.',
        landmark: 'Well',
        connectedTo: 'Hearth',
        sounds: 'Haggling.',
        detailExtra: ''
      }
    ],
    activePlace: 'market',
    startPlace: 'hearth',
    loreExtra: ''
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
      secretFear: charDraft.secretFear,
      personalityExtra: '',
      backgroundExtra: ''
    })
  })

  it('round-trips multi-line prose via continuation lines', () => {
    const draft = { ...charDraft, want: 'Line one.\nLine two.' }
    const restored = unpackCharacter(packCharacter(draft) as Record<string, unknown>)
    expect(restored.want).toBe('Line one.\nLine two.')
  })

  it('preserves ordinary server prose the parser never authored', () => {
    const restored = unpackCharacter({
      personality: 'A wandering sword-for-hire with a past.',
      background: 'Owes money in three towns.'
    })
    expect(restored.want).toBe('')
    expect(restored.personalityExtra).toBe('A wandering sword-for-hire with a past.')
    expect(restored.backgroundExtra).toBe('Owes money in three towns.')
    // Packing it back is byte-identical: nothing is lost or rewritten.
    const packed = packCharacter({ ...charDraft, ...restored })
    expect(packed.personality).toBe('A wandering sword-for-hire with a past.')
    expect(packed.background).toBe('Owes money in three towns.')
  })

  it('keeps unrelated prose when one section is edited', () => {
    const restored = unpackCharacter({
      personality: 'A wandering sword-for-hire with a past.'
    })
    const edited = { ...charDraft, ...restored, want: 'Find their brother.' }
    const packed = packCharacter(edited, {
      personality: 'A wandering sword-for-hire with a past.'
    })
    expect(packed.personality).toContain('A wandering sword-for-hire with a past.')
    expect(packed.personality).toContain('Wants: Find their brother.')
  })

  it('omits unchanged keys and emits an explicit clear', () => {
    const prev = packCharacter(charDraft) as Record<string, unknown>
    // Nothing changed: the merge must not rewrite anything.
    expect(packCharacter(charDraft, prev)).toEqual({})
    // Cleared down to nothing: an explicit empty string, not an omission
    // (an omission would resurrect the old value through the merge).
    const cleared = { ...charDraft, want: '', avoid: '', pressure: '' }
    const repacked = packCharacter(cleared, prev)
    expect(repacked.personality).toBeDefined()
    expect(repacked.personality).not.toContain('Wants:')
    // Reloading the cleared value keeps it cleared.
    const reloaded = unpackCharacter({ personality: repacked.personality ?? '' })
    expect(reloaded.want).toBe('')
    expect(reloaded.avoid).toBe('')
  })

  it('packs the world form into valid payload keys only', () => {
    const packed = packWorld(worldDraft())
    expect(Object.keys(packed).sort()).toEqual([
      'description',
      'locations',
      'lore',
      'starting_location_key',
      'travel'
    ])
    expect(packed.description).toBe('Mossy riverbanks.')
    expect(packed.starting_location_key).toBe('hearth')
    expect(packed.locations).toHaveLength(2)
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
      key: 'hearth',
      name: 'Hearth',
      type: 'Village inn',
      purpose: 'Warm rest.',
      landmark: 'The fire'
    })
    expect(restored.places?.[1]).toMatchObject({ key: 'market_east', name: 'Market' })
  })

  it('repairs name references when a place is renamed', () => {
    const draft = worldDraft()
    expect(renamePlaceReferences(draft.places, 'market', 'Market', 'Grand Market')).toBe(1)
    expect(draft.places[0]!.connectedTo).toBe('Grand Market')
    expect(renamePlaceReferences(draft.places, 'market', 'Grand Market', 'Grand Market')).toBe(0)
    expect(renamePlaceReferences(draft.places, 'missing', 'Grand Market', 'X')).toBe(0)
  })

  it('keeps stable location keys across renames so routes survive', () => {
    const draft = worldDraft()
    const first = packWorld(draft) as unknown as Record<string, unknown>
    // Rename Market (references follow explicitly); the key must not follow the name.
    draft.places[1]!.name = 'Grand Market'
    renamePlaceReferences(draft.places, 'market', 'Market', 'Grand Market')
    const second = packWorld(draft, first)
    const locations = second.locations as { key: string; name: string }[]
    expect(locations.find((l) => l.name === 'Grand Market')?.key).toBe('market_east')
    // Reloading the packed map keeps the key.
    const reloaded = unpackWorld(second as unknown as Record<string, unknown>)
    expect(reloaded.places?.[1]?.key).toBe('market_east')
    // The routes did not change, so no travel rewrite ships at all.
    expect(second.travel).toBeUndefined()
  })

  it('separates the inspected tab from the configured starting place', () => {
    const draft = worldDraft()
    // Inspecting the Market tab leaves the Hearth starting pin alone.
    expect(draft.activePlace).toBe('market')
    const packed = packWorld(draft)
    expect(packed.starting_location_key).toBe('hearth')
    // Configuring the start on Market moves only the pin, not the tab.
    draft.startPlace = 'market'
    const prev = packWorld(worldDraft()) as unknown as Record<string, unknown>
    expect(packWorld(draft, prev).starting_location_key).toBe('market_east')
  })

  it('derives travel from connections and drops cleared legs', () => {
    const draft = worldDraft()
    const packed = packWorld(draft)
    expect(packed.travel).toEqual([
      ['hearth', 'market_east'],
      ['market_east', 'hearth']
    ])
    // Clearing both connections clears the routes instead of preserving them.
    draft.places[0]!.connectedTo = ''
    draft.places[1]!.connectedTo = ''
    const cleared = packWorld(draft, packed as unknown as Record<string, unknown>)
    expect(cleared.travel).toEqual([])
  })

  it('preserves lore residue and clears explicitly emptied lore', () => {
    const restored = unpackWorld({ lore: 'Old songs mention this valley.' })
    expect(restored.loreExtra).toBe('Old songs mention this valley.')
    expect(restored.terrain).toEqual([])
    const draft = { ...worldDraft(), ...restored, climate: 'Arid' }
    const packed = packWorld(draft, { lore: 'Old songs mention this valley.' })
    expect(packed.lore).toContain('Old songs mention this valley.')
    expect(packed.lore).toContain('Climate: Arid')
  })

  it('removes a place explicitly and repairs dependent references', () => {
    const draft = worldDraft()
    expect(removeWorldPlace(draft, 'missing')).toBe(false)
    expect(removeWorldPlace(draft, 'market')).toBe(true)
    expect(draft.places.map((p) => p.id)).toEqual(['hearth'])
    // Hearth pointed at Market by name: disconnected, not dangling.
    expect(draft.places[0]!.connectedTo).toBe('')
    // The inspected tab fell back; the starting pin was elsewhere and stays.
    expect(draft.activePlace).toBe('hearth')
    expect(draft.startPlace).toBe('hearth')
    // The last place cannot go: an empty map is not publishable.
    expect(removeWorldPlace(draft, 'hearth')).toBe(false)
  })

  it('moves the starting pin when its place is removed', () => {
    const draft = worldDraft()
    draft.startPlace = 'market'
    draft.activePlace = 'hearth'
    expect(removeWorldPlace(draft, 'market')).toBe(true)
    expect(draft.startPlace).toBe('hearth')
    expect(draft.activePlace).toBe('hearth')
  })

  it('slugs place keys deterministically', () => {
    expect(slugPlaceKey('The Lantern Point', 'place-1')).toBe('the-lantern-point')
    expect(slugPlaceKey('!!!', 'place-2')).toBe('place-2')
    expect(normalizePlaceKey('Hearth', 'market_east', 'place-9')).toBe('market_east')
    expect(normalizePlaceKey('Hearth', undefined, 'place-9')).toBe('hearth')
    expect(normalizePlaceKey('Hearth', '  ', 'place-9')).toBe('hearth')
  })
})
