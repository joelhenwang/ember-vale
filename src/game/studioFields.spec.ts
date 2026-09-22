import { describe, expect, it } from 'vitest'
import {
  connectionLabel,
  connectionOptions,
  normalizePlaceKey,
  packCharacter,
  packWorld,
  placeForConnectionLabel,
  removeWorldPlace,
  renamePlaceReferences,
  resolveConnectionKeys,
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
        connectedKey: 'market_east',
        sounds: 'Kettles.',
        detailExtra: '',
        detailBase: '',
        detailBaseCanonical: ''
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
        connectedKey: 'hearth',
        sounds: 'Haggling.',
        detailExtra: '',
        detailBase: '',
        detailBaseCanonical: ''
      }
    ],
    activePlace: 'market',
    startPlace: 'hearth',
    loreExtra: '',
    travelExtra: []
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
    // (The picker clears the stored key and the display name together.)
    draft.places[0]!.connectedTo = ''
    draft.places[0]!.connectedKey = ''
    draft.places[1]!.connectedTo = ''
    draft.places[1]!.connectedKey = ''
    const cleared = packWorld(draft, packed as unknown as Record<string, unknown>)
    expect(cleared.travel).toEqual([])
  })

  it('keeps server-authored routes through an unrelated save', () => {
    // The map arrived with routes but no "Connected to" prose: editing
    // the description must not touch a single route.
    const server = {
      description: 'Mossy riverbanks.',
      lore: '',
      locations: [
        { key: 'hearth', name: 'Hearth', description: '' },
        { key: 'market_east', name: 'Market', description: '' }
      ],
      starting_location_key: 'hearth',
      travel: [
        ['hearth', 'market_east'],
        ['market_east', 'hearth']
      ]
    }
    const restored = unpackWorld(server)
    expect(restored.places?.[0]?.connectedTo).toBe('Market')
    const draft = { ...worldDraft(), ...restored, details: 'Mossy riverbanks, at dawn.' }
    const packed = packWorld(draft, server)
    expect(packed.description).toBe('Mossy riverbanks, at dawn.')
    // The graph is untouched, so no travel rewrite ships at all.
    expect(packed.travel).toBeUndefined()
    // The empty descriptions never gained generated sections either.
    expect(packed.locations).toBeUndefined()
  })

  it('preserves legs the form cannot represent', () => {
    const server = {
      description: '',
      lore: '',
      locations: [
        { key: 'hearth', name: 'Hearth', description: '' },
        { key: 'market_east', name: 'Market', description: '' },
        { key: 'mill', name: 'Mill', description: '' }
      ],
      starting_location_key: 'hearth',
      travel: [
        ['hearth', 'market_east'],
        ['hearth', 'mill'],
        ['mill', 'market_east']
      ]
    }
    const restored = unpackWorld(server)
    // The first leg per source hydrates the field; the rest go opaque.
    // (Mill's own leg hydrates Mill's field, so only Hearth's second
    // leg is unrepresentable.)
    expect(restored.places?.[0]?.connectedTo).toBe('Market')
    expect(restored.places?.[2]?.connectedTo).toBe('Market')
    expect(restored.travelExtra).toEqual([['hearth', 'mill']])
    // An unrelated save re-emits the full graph, order-stable.
    const draft = { ...worldDraft(), ...restored }
    draft.places = restored.places!
    draft.activePlace = restored.activePlace!
    draft.startPlace = restored.startPlace!
    draft.travelExtra = restored.travelExtra!
    const packed = packWorld(draft, server)
    expect(packed.travel).toBeUndefined()
  })

  it('removes only the cleared leg, keeping unrepresentable ones', () => {
    const server = {
      description: '',
      lore: '',
      locations: [
        { key: 'hearth', name: 'Hearth', description: '' },
        { key: 'market_east', name: 'Market', description: '' },
        { key: 'mill', name: 'Mill', description: '' }
      ],
      starting_location_key: 'hearth',
      travel: [
        ['hearth', 'market_east'],
        ['hearth', 'mill']
      ]
    }
    const draft = { ...worldDraft(), ...unpackWorld(server) }
    draft.places = unpackWorld(server).places!
    draft.travelExtra = unpackWorld(server).travelExtra!
    // Hearth's visible connection is cleared: its hydrated leg goes,
    // the opaque second leg stays. (Market never had an outgoing leg
    // in this map, so nothing else ships.)
    draft.places[0]!.connectedTo = ''
    draft.places[0]!.connectedKey = ''
    const packed = packWorld(draft, server)
    expect(packed.travel).toEqual([['hearth', 'mill']])
  })

  it('prunes routes of a deleted place explicitly', () => {
    const draft = worldDraft()
    draft.travelExtra = [['market_east', 'hearth']]
    expect(removeWorldPlace(draft, 'market')).toBe(true)
    expect(draft.travelExtra).toEqual([])
    const packed = packWorld(draft)
    // Nothing to rewrite against an empty previous graph: omit, not [].
    expect(packed.travel).toBeUndefined()
    expect(packed.locations).toHaveLength(1)
  })

  it('sends complete location records on change and nothing when unchanged', () => {
    const draft = worldDraft()
    const first = packWorld(draft) as unknown as Record<string, unknown>
    // A second identical save ships no locations at all.
    expect(packWorld(draft, first).locations).toBeUndefined()
    // Renaming one place ships every record complete with descriptions.
    draft.places[1]!.name = 'Grand Market'
    renamePlaceReferences(draft.places, 'market', 'Market', 'Grand Market')
    const second = packWorld(draft, first)
    expect(second.locations).toHaveLength(2)
    for (const entry of second.locations as { key: string; description?: string }[]) {
      expect(typeof entry.description).toBe('string')
    }
    // Reloading the published map keeps every unchanged description.
    const reloaded = unpackWorld({
      ...(first as Record<string, unknown>),
      ...(second as Record<string, unknown>)
    })
    expect(reloaded.places?.[0]?.purpose).toBe('Warm rest.')
    expect(reloaded.places?.[1]?.name).toBe('Grand Market')
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

  it('keeps a route on the second of two same-named places', () => {
    const server = {
      description: '',
      lore: '',
      locations: [
        { key: 'market_east', name: 'Market', description: '' },
        { key: 'market_west', name: 'Market', description: '' },
        { key: 'hearth', name: 'Hearth', description: '' }
      ],
      starting_location_key: 'hearth',
      travel: [['hearth', 'market_west']]
    }
    const restored = unpackWorld(server)
    // The link is stored by key even though both names read "Market".
    expect(restored.places?.[2]?.connectedKey).toBe('market_west')
    expect(restored.places?.[2]?.connectedTo).toBe('Market')
    // An unrelated edit re-saves without redirecting the route east.
    const draft: WorldDraft = {
      terrain: [],
      climate: '',
      architecture: '',
      details: 'Mossy riverbanks, at dawn.',
      exclusions: '',
      places: restored.places!,
      activePlace: restored.activePlace!,
      startPlace: restored.startPlace!,
      loreExtra: '',
      travelExtra: restored.travelExtra ?? []
    }
    const packed = packWorld(draft, server)
    expect(packed.description).toBe('Mossy riverbanks, at dawn.')
    expect(packed.travel).toBeUndefined()
    expect(packed.locations).toBeUndefined()
  })

  it('labels duplicate connections by key and resolves picks by label', () => {
    const server = {
      description: '',
      lore: '',
      locations: [
        { key: 'market_east', name: 'Market', description: '' },
        { key: 'market_west', name: 'Market', description: '' },
        { key: 'hearth', name: 'Hearth', description: '' }
      ],
      starting_location_key: 'hearth',
      travel: []
    }
    const places = unpackWorld(server).places!
    const hearth = places.find((p) => p.key === 'hearth')!
    expect(connectionOptions(places, hearth.id)).toEqual([
      'Market (market_east)',
      'Market (market_west)'
    ])
    expect(connectionLabel(places, 'market_west')).toBe('Market (market_west)')
    expect(placeForConnectionLabel(places, 'Market (market_west)')?.key).toBe('market_west')
    expect(placeForConnectionLabel(places, 'Market (market_east)')?.key).toBe('market_east')
    expect(placeForConnectionLabel(places, '')).toBeUndefined()
    // Unique names stay plain labels.
    const solo = worldDraft().places
    expect(connectionOptions(solo, 'hearth')).toEqual(['Market'])
    expect(connectionLabel(solo, 'market_east')).toBe('Market')
    expect(placeForConnectionLabel(solo, 'Market')?.key).toBe('market_east')
  })

  it('repoints only the linked place when duplicate names rename', () => {
    const server = {
      description: '',
      lore: '',
      locations: [
        { key: 'market_east', name: 'Market', description: '' },
        { key: 'market_west', name: 'Market', description: '' },
        { key: 'hearth', name: 'Hearth', description: '' }
      ],
      starting_location_key: 'hearth',
      travel: [['hearth', 'market_west']]
    }
    const places = unpackWorld(server).places!
    const west = places.find((p) => p.key === 'market_west')!
    expect(renamePlaceReferences(places, west.id, 'Market', 'Grand Market')).toBe(1)
    // Hearth links west by key, so its display name follows the rename.
    expect(places.find((p) => p.key === 'hearth')?.connectedTo).toBe('Grand Market')
    // Nothing else named "Market" moved.
    expect(places.find((p) => p.key === 'market_east')?.connectedTo).toBe('')
    // The route still targets the western key, so the rename ships
    // location records but no travel rewrite at all.
    const draft: WorldDraft = {
      terrain: [],
      climate: '',
      architecture: '',
      details: '',
      exclusions: '',
      places,
      activePlace: places[0]!.id,
      startPlace: places[2]!.id,
      loreExtra: '',
      travelExtra: []
    }
    const packed = packWorld(draft, server)
    expect(packed.travel).toBeUndefined()
    expect(packed.locations).toHaveLength(3)
  })

  it('leaves plain and empty server descriptions byte-identical on a no-op save', () => {
    const plain = 'A quiet room above the shop.'
    const server = {
      description: '',
      lore: '',
      locations: [
        { key: 'hearth', name: 'Hearth', description: '' },
        { key: 'loft', name: 'Loft', description: plain }
      ],
      starting_location_key: 'hearth',
      travel: [['hearth', 'loft']]
    }
    const restored = unpackWorld(server)
    // Hydration filled in defaults the prose never had...
    expect(restored.places?.[0]?.type).toBe('Other')
    expect(restored.places?.[0]?.connectedTo).toBe('Loft')
    expect(restored.places?.[1]?.detailExtra).toBe(plain)
    // ...but an unrelated world-description edit leaves every location
    // byte-identical: no generated Type / Connected-to sections appear.
    const draft: WorldDraft = {
      terrain: [],
      climate: '',
      architecture: '',
      details: 'Mossy riverbanks.',
      exclusions: '',
      places: restored.places!,
      activePlace: restored.activePlace!,
      startPlace: restored.startPlace!,
      loreExtra: '',
      travelExtra: restored.travelExtra ?? []
    }
    const packed = packWorld(draft, server)
    expect(packed.description).toBe('Mossy riverbanks.')
    expect(packed.locations).toBeUndefined()
    expect(packed.travel).toBeUndefined()
  })

  it('regenerates a location description only after a relevant edit', () => {
    const plain = 'A quiet room above the shop.'
    const server = {
      description: '',
      lore: '',
      locations: [
        { key: 'hearth', name: 'Hearth', description: '' },
        { key: 'loft', name: 'Loft', description: plain }
      ],
      starting_location_key: 'hearth',
      travel: [['hearth', 'loft']]
    }
    const restored = unpackWorld(server)
    const draft: WorldDraft = {
      terrain: [],
      climate: '',
      architecture: '',
      details: '',
      exclusions: '',
      places: restored.places!,
      activePlace: restored.activePlace!,
      startPlace: restored.startPlace!,
      loreExtra: '',
      travelExtra: restored.travelExtra ?? []
    }
    // Editing the loft's purpose regenerates only the loft's record.
    draft.places[1]!.purpose = 'Storage.'
    const packed = packWorld(draft, server)
    const entries = packed.locations as { key: string; description?: string }[]
    expect(entries).toHaveLength(2)
    const loft = entries.find((e) => e.key === 'loft')!
    expect(loft.description).toContain(plain)
    expect(loft.description).toContain('Purpose: Storage.')
    // The untouched hearth ships its original bytes, not a rewrite.
    expect(entries.find((e) => e.key === 'hearth')?.description).toBe('')
  })

  it('backfills stored keys from legacy display names', () => {
    const draft = worldDraft()
    for (const p of draft.places) p.connectedKey = ''
    resolveConnectionKeys(draft.places)
    expect(draft.places[0]!.connectedKey).toBe('market_east')
    expect(draft.places[1]!.connectedKey).toBe('hearth')
    // Unresolvable names stay unlinked rather than guessing.
    draft.places[0]!.connectedTo = 'Nowhere'
    draft.places[0]!.connectedKey = ''
    resolveConnectionKeys(draft.places)
    expect(draft.places[0]!.connectedKey).toBe('')
  })

  it('derives travel from display names only for keyless legacy drafts', () => {
    const draft = worldDraft()
    draft.places[0]!.connectedKey = ''
    draft.places[1]!.connectedKey = ''
    const packed = packWorld(draft)
    expect(packed.travel).toEqual([
      ['hearth', 'market_east'],
      ['market_east', 'hearth']
    ])
  })

  it('drops a stored key that no longer names a live place', () => {
    const draft = worldDraft()
    // The display name still resolves, but the stale key must not fall
    // back to it — that guess could redirect at a same-named stranger.
    draft.places[0]!.connectedKey = 'gone'
    const packed = packWorld(draft)
    expect(packed.travel).toEqual([['market_east', 'hearth']])
  })

  it('clears the stored key when its place is removed', () => {
    const draft = worldDraft()
    expect(removeWorldPlace(draft, 'market')).toBe(true)
    expect(draft.places[0]!.connectedTo).toBe('')
    expect(draft.places[0]!.connectedKey).toBe('')
  })
})
