import { describe, expect, it } from 'vitest'
import { filterCharactersLibrary, filterWorlds } from '../game/filters'
import {
  toLibraryCharacter,
  toLibraryWorld,
  type PresetCharacter,
  type PresetWorld
} from './usePresets'

const wren: PresetCharacter = {
  id: 'w1',
  revision: 2,
  name: 'Wren',
  role: 'Traveler',
  blurb: 'Quick eyes.',
  tags: ['Human', 'Explorer', 'Player-ready'],
  startKey: 'hearth',
  playerReady: true,
  imageSlot: 'character.wren'
}

const nessa: PresetCharacter = {
  id: 'n1',
  revision: 1,
  name: 'Nessa',
  role: 'Ferrywoman',
  blurb: 'Knows the river.',
  tags: ['Human', 'Local', 'NPC'],
  startKey: null,
  playerReady: false,
  imageSlot: 'story.lantern'
}

const vale: PresetWorld = {
  id: 'v1',
  revision: 2,
  name: 'Ember Vale',
  description: 'A welcoming valley.',
  places: [
    { key: 'hearth', name: 'Hearth' },
    { key: 'market', name: 'Market' }
  ]
}

describe('server preset library mapping', () => {
  it('maps a character preset to a card record with revision recency', () => {
    const record = toLibraryCharacter(wren)
    expect(record).toMatchObject({
      id: 'w1',
      name: 'Wren',
      role: 'Traveler',
      playerReady: true,
      categories: ['companions'],
      usedInStories: null,
      revision: 2,
      imageSlot: 'character.wren'
    })
    expect(record.tags).toContainEqual({ label: 'Player-ready', tone: 'green' })
    expect(record.tags).toContainEqual({ label: 'Explorer' })
  })

  it('marks non-player presets as locals without curated faces', () => {
    const record = toLibraryCharacter(nessa)
    expect(record.categories).toEqual(['locals'])
    expect(record.playerReady).toBe(false)
    expect(record.imageSlot).toBe('story.lantern')
  })

  it('maps a world preset with place count and ready status', () => {
    const record = toLibraryWorld(vale)
    expect(record).toMatchObject({
      id: 'v1',
      name: 'Ember Vale',
      blurb: 'A welcoming valley.',
      places: 2,
      usedInStories: null,
      status: 'ready',
      revision: 2,
      imageSlot: 'world.emberVale'
    })
  })

  it('falls back to the neutral map slot for unknown worlds', () => {
    const record = toLibraryWorld({ ...vale, id: 'v9', name: 'Elsewhere' })
    expect(record.imageSlot).toBe('world.map')
  })

  it('mapped records flow through the existing library filters', () => {
    const characters = [toLibraryCharacter(wren), toLibraryCharacter(nessa)]
    expect(
      filterCharactersLibrary(characters, { search: '', chip: 'player', sort: 'name' }).map(
        (c) => c.name
      )
    ).toEqual(['Wren'])
    expect(
      filterCharactersLibrary(characters, { search: 'river', chip: 'all', sort: 'name' }).map(
        (c) => c.name
      )
    ).toEqual(['Nessa'])
    const worlds = [toLibraryWorld(vale)]
    expect(
      filterWorlds(worlds, { search: '', chip: 'ready', sort: 'name' }).map((w) => w.name)
    ).toEqual(['Ember Vale'])
    expect(filterWorlds(worlds, { search: '', chip: 'draft', sort: 'name' })).toEqual([])
  })
})
