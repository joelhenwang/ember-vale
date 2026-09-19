import { describe, expect, it } from 'vitest'
import { catalog } from './catalog'
import {
  filterCast,
  filterCharactersLibrary,
  filterPacks,
  filterWorlds,
  matchesQuery,
  sortByNameOrRecent
} from './filters'

const byName = (a: { name: string }, b: { name: string }) => a.name.localeCompare(b.name)

describe('sortByNameOrRecent', () => {
  const items = [
    { name: 'Zeta', updatedAt: 5 },
    { name: 'Alpha', updatedAt: 1 },
    { name: 'Mid', updatedAt: 9 }
  ]
  it('sorts by name ascending', () => {
    expect(sortByNameOrRecent(items, 'name').map((i) => i.name)).toEqual(['Alpha', 'Mid', 'Zeta'])
  })
  it('sorts by updatedAt descending for "recent"', () => {
    expect(sortByNameOrRecent(items, 'recent').map((i) => i.name)).toEqual(['Mid', 'Zeta', 'Alpha'])
  })
  it('does not mutate the input', () => {
    sortByNameOrRecent(items, 'name')
    expect(items.map((i) => i.name)).toEqual(['Zeta', 'Alpha', 'Mid'])
  })
})

describe('matchesQuery', () => {
  it('treats blank queries as match-all', () => {
    expect(matchesQuery('   ', 'anything')).toBe(true)
  })
  it('is case-insensitive substring matching', () => {
    expect(matchesQuery('WREN', 'Wren the traveler')).toBe(true)
    expect(matchesQuery('mage', 'Wren the traveler')).toBe(false)
  })
})

describe('filterCast', () => {
  const noFilter = { search: '', category: 'all', sort: 'name' } as const
  it('passes everything through with neutral filters, sorted by name', () => {
    const out = filterCast(catalog.characters, noFilter)
    expect(out.length).toBe(catalog.characters.length)
    expect([...out].sort(byName)).toEqual(out)
  })
  it('restricts to a category', () => {
    const out = filterCast(catalog.characters, { ...noFilter, category: 'companions' })
    expect(out.length).toBeGreaterThan(0)
    expect(out.every((c) => c.categories.includes('companions'))).toBe(true)
  })
  it('searches name, role and blurb', () => {
    const out = filterCast(catalog.characters, { ...noFilter, search: 'traveler' })
    expect(out.some((c) => c.id === 'wren')).toBe(true)
  })
})

describe('library filters', () => {
  const base = { search: '', chip: 'all', sort: 'name' } as const
  it('splits characters by the player/npc chip', () => {
    const players = filterCharactersLibrary(catalog.characters, { ...base, chip: 'player' })
    const npcs = filterCharactersLibrary(catalog.characters, { ...base, chip: 'npc' })
    expect(players.length).toBeGreaterThan(0)
    expect(players.every((c) => c.playerReady)).toBe(true)
    expect(npcs.every((c) => !c.playerReady)).toBe(true)
    expect(players.length + npcs.length).toBe(catalog.characters.length)
  })
  it('filters worlds by status chip', () => {
    const ready = filterWorlds(catalog.worlds, { ...base, chip: 'ready' })
    expect(ready.every((w) => w.status === 'ready')).toBe(true)
  })
  it('packs ignore the chip (no statuses) but honor search', () => {
    const all = filterPacks(catalog.stylePacks, base)
    const q = filterPacks(catalog.stylePacks, { ...base, search: 'zzz-no-match' })
    expect(all.length).toBe(catalog.stylePacks.length)
    expect(q).toHaveLength(0)
  })
})
