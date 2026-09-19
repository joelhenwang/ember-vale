/**
 * Pure list-filtering helpers shared by the wizard cast picker and the
 * Library. Deliberately free of Vue reactivity so they can be unit-tested
 * in isolation (see src/game/filters.spec.ts).
 */
import type { CharacterDef, PackDef, WorldDef } from './model'

export type SortMode = 'name' | 'recent'

interface Sortable {
  name: string
  updatedAt: number
}

export function sortByNameOrRecent<T extends Sortable>(items: readonly T[], sort: SortMode): T[] {
  return [...items].sort((a, b) =>
    sort === 'name' ? a.name.localeCompare(b.name) : b.updatedAt - a.updatedAt
  )
}

export function matchesQuery(query: string, haystack: string): boolean {
  const q = query.trim().toLowerCase()
  return !q || haystack.toLowerCase().includes(q)
}

/* ------------------------------------------------------------------ *
 * New Story — cast picker
 * ------------------------------------------------------------------ */

/** 'all' or one of the categories present on CharacterDef. */
export type CastCategory = 'all' | CharacterDef['categories'][number]

export interface CastFilter {
  search: string
  category: CastCategory
  sort: SortMode
}

export function filterCast(characters: readonly CharacterDef[], f: CastFilter): CharacterDef[] {
  const filtered = characters.filter((c) => {
    if (f.category !== 'all' && !c.categories.includes(f.category)) return false
    return matchesQuery(f.search, `${c.name} ${c.role} ${c.blurb}`)
  })
  return sortByNameOrRecent(filtered, f.sort)
}

/* ------------------------------------------------------------------ *
 * Library tabs — chip vocabulary lives here so card badges, filter
 * options and logic can't drift apart silently.
 * ------------------------------------------------------------------ */

export interface LibraryFilter {
  search: string
  /** Tab-specific chip value; see the filter functions for the vocabulary. */
  chip: string
  sort: SortMode
}

export function filterCharactersLibrary(
  characters: readonly CharacterDef[],
  f: LibraryFilter
): CharacterDef[] {
  const filtered = characters.filter((c) => {
    if (f.chip === 'player' && !c.playerReady) return false
    if (f.chip === 'npc' && c.playerReady) return false
    return matchesQuery(f.search, `${c.name} ${c.role} ${c.bio}`)
  })
  return sortByNameOrRecent(filtered, f.sort)
}

export function filterWorlds(worlds: readonly WorldDef[], f: LibraryFilter): WorldDef[] {
  const filtered = worlds.filter((w) => {
    if (f.chip !== 'all' && w.status !== f.chip) return false
    return matchesQuery(f.search, `${w.name} ${w.blurb}`)
  })
  return sortByNameOrRecent(filtered, f.sort)
}

export function filterPacks(packs: readonly PackDef[], f: LibraryFilter): PackDef[] {
  return sortByNameOrRecent(
    packs.filter((p) => matchesQuery(f.search, `${p.name} ${p.blurb}`)),
    f.sort
  )
}

/* ------------------------------------------------------------------ *
 * Stories shelf
 * ------------------------------------------------------------------ */

interface StoryLike {
  title: string
  world: string
  blurb: string
  status: 'in-progress' | 'archived'
  lastPlayedAt: number
}

export interface StoryFilter {
  search: string
  chip: 'all' | 'in-progress' | 'archived'
  sort: SortMode
}

export function filterStories<T extends StoryLike>(stories: readonly T[], f: StoryFilter): T[] {
  const filtered = stories.filter((s) => {
    if (f.chip !== 'all' && s.status !== f.chip) return false
    return matchesQuery(f.search, `${s.title} ${s.world} ${s.blurb}`)
  })
  return [...filtered].sort((a, b) =>
    f.sort === 'name' ? a.title.localeCompare(b.title) : b.lastPlayedAt - a.lastPlayedAt
  )
}
