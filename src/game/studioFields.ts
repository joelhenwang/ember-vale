/**
 * Field bridge between the studio forms and the server preset payloads (E3).
 *
 * The studio forms predate the server schemas, so this mapping is explicit
 * and tested: every packed key names a real payload field, and unpacking
 * restores the form. Keys the editor never exposes (character appearance
 * and tags, world name/cast/style-pack) are never packed, so the server
 * merge preserves them verbatim.
 *
 * Location identity is key-based, never name-based: each form place
 * carries a stable `key` that survives renames, travel pairs reference
 * those keys, and the configured starting place (`startPlace`) is a
 * separate field from the inspected tab (`activePlace`) — clicking
 * through tabs can never move the world's starting location.
 *
 * Section packing is line-prefix based with continuation lines. Leading
 * free prose the parser does not attribute to a known prefix is kept as
 * residue (`*Extra` fields, invisible in the form) and packed back
 * verbatim ahead of the regenerated sections, so ordinary server prose
 * survives section edits. A user line that starts with a known prefix is
 * the one documented edge: it unpacks under that prefix.
 *
 * Packing compares against the previously acknowledged server fields
 * (`prev`): unchanged keys are omitted, while a recomputed empty string
 * that differs from `prev` is emitted explicitly — clearing a field
 * clears it server-side instead of resurrecting the old value through
 * the merge.
 */

import type { CharacterDraft, PlaceDraft, WorldDraft } from './studio'

const PERSONALITY_PREFIXES = [
  'Wants',
  'Avoids',
  'Under pressure',
  'Contradiction',
  'With strangers',
  'When they care',
  'Example line',
  'Styles'
] as const

const BACKGROUND_PREFIXES = ['Boundaries', 'Secret fear'] as const

const LORE_PREFIXES = ['Terrain', 'Climate', 'Architecture', 'Exclusions'] as const

const PLACE_PREFIXES = [
  'Type',
  'Purpose',
  'Appearance',
  'Landmark',
  'Connected to',
  'Texture'
] as const

interface SplitSections {
  /** Values attributed to known prefixes (every known key present, possibly ''). */
  values: Record<string, string>
  /** Leading free prose before the first recognized prefix, trimmed. */
  rest: string
}

function splitSections(text: string, known: readonly string[]): SplitSections {
  const values: Record<string, string> = {}
  const restLines: string[] = []
  let current: string | null = null
  for (const line of text.split('\n')) {
    const hit = known.find((p) => line === p || line.startsWith(`${p}:`))
    if (hit !== undefined) {
      current = hit
      const rest = line.slice(hit.length).replace(/^:\s?/, '')
      values[hit] = rest
    } else if (current !== null) {
      values[current] = values[current] ? `${values[current]}\n${line}` : line
    } else {
      restLines.push(line)
    }
  }
  for (const k of known) {
    if (!(k in values)) values[k] = ''
    else values[k] = values[k].trim()
  }
  return { values, rest: restLines.join('\n').trim() }
}

/** Residue first, then regenerated sections — unpack attributes leading lines to residue. */
function combineSections(extra: string, entries: Array<[string, string]>): string {
  const sections = entries
    .filter(([, v]) => v.trim().length > 0)
    .map(([k, v]) => `${k}: ${v.trim()}`)
    .join('\n')
  return [extra.trim(), sections].filter((part) => part.length > 0).join('\n')
}

function prevString(prev: Record<string, unknown>, key: string): string {
  const raw = prev[key]
  return typeof raw === 'string' ? raw : ''
}

export interface CharacterServerFields {
  personality?: string
  background?: string
}

/** Pack the character form, emitting only keys that differ from `prev`. */
export function packCharacter(
  draft: CharacterDraft,
  prev: Record<string, unknown> = {}
): CharacterServerFields {
  const personality = combineSections(draft.personalityExtra, [
    ['Wants', draft.want],
    ['Avoids', draft.avoid],
    ['Under pressure', draft.pressure],
    ['Contradiction', draft.contradiction],
    ['With strangers', draft.withStrangers],
    ['When they care', draft.whenTheyCare],
    ['Example line', draft.exampleLine],
    ['Styles', draft.styleTags.join('; ')]
  ])
  const background = combineSections(draft.backgroundExtra, [
    ['Boundaries', draft.boundaries],
    ['Secret fear', draft.secretFear]
  ])
  const out: CharacterServerFields = {}
  if (personality !== prevString(prev, 'personality')) out.personality = personality
  if (background !== prevString(prev, 'background')) out.background = background
  return out
}

/** Restore the character form from packed (or server) fields. */
export function unpackCharacter(fields: Record<string, unknown>): Partial<CharacterDraft> {
  const out: Partial<CharacterDraft> = {}
  if (typeof fields['personality'] === 'string') {
    const s = splitSections(fields['personality'], PERSONALITY_PREFIXES)
    out.want = s.values['Wants'] ?? ''
    out.avoid = s.values['Avoids'] ?? ''
    out.pressure = s.values['Under pressure'] ?? ''
    out.contradiction = s.values['Contradiction'] ?? ''
    out.withStrangers = s.values['With strangers'] ?? ''
    out.whenTheyCare = s.values['When they care'] ?? ''
    out.exampleLine = s.values['Example line'] ?? ''
    const styles = s.values['Styles'] ?? ''
    out.styleTags = styles
      ? styles
          .split(';')
          .map((t) => t.trim())
          .filter(Boolean)
      : []
    out.personalityExtra = s.rest
  }
  if (typeof fields['background'] === 'string') {
    const s = splitSections(fields['background'], BACKGROUND_PREFIXES)
    out.boundaries = s.values['Boundaries'] ?? ''
    out.secretFear = s.values['Secret fear'] ?? ''
    out.backgroundExtra = s.rest
  }
  return out
}

export function slugPlaceKey(name: string, fallback: string): string {
  const slug = name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '')
  return slug || fallback
}

/** Stable server key for a form place: kept across renames, never re-slugged. */
export function normalizePlaceKey(name: string, key: unknown, fallback: string): string {
  return typeof key === 'string' && key.trim() ? key.trim() : slugPlaceKey(name, fallback)
}

export interface WorldServerLocation {
  key: string
  name: string
  description?: string
}

export interface WorldServerFields {
  description?: string
  lore?: string
  locations?: WorldServerLocation[]
  starting_location_key?: string
  travel?: string[][]
}

function packPlaceEntries(p: PlaceDraft): Array<[string, string]> {
  return [
    ['Type', p.type],
    ['Purpose', p.purpose],
    ['Appearance', p.appearance],
    ['Landmark', p.landmark],
    ['Connected to', p.connectedTo],
    ['Texture', p.sounds]
  ]
}

/** Pack the world form, emitting only keys that differ from `prev`. */
export function packWorld(
  draft: WorldDraft,
  prev: Record<string, unknown> = {}
): WorldServerFields {
  const lore = combineSections(draft.loreExtra, [
    ['Terrain', draft.terrain.join('; ')],
    ['Climate', draft.climate],
    ['Architecture', draft.architecture],
    ['Exclusions', draft.exclusions]
  ])
  const prevLocations = Array.isArray(prev['locations']) ? (prev['locations'] as unknown[]) : []
  const prevDescByKey = new Map<string, string>()
  for (const item of prevLocations) {
    if (typeof item !== 'object' || item === null) continue
    const rec = item as Record<string, unknown>
    if (typeof rec['key'] !== 'string') continue
    prevDescByKey.set(rec['key'], typeof rec['description'] === 'string' ? rec['description'] : '')
  }
  // Normalize keys once: names resolve through this table everywhere below.
  const keyed = draft.places.map((p, i) => ({
    place: p,
    key: normalizePlaceKey(p.name, p.key, `place-${i + 1}`)
  }))
  const locations: WorldServerLocation[] = keyed.map(({ place: p, key }) => {
    const detail = combineSections(p.detailExtra, packPlaceEntries(p))
    const entry: WorldServerLocation = { key, name: p.name }
    const prevDesc = prevDescByKey.get(key) ?? ''
    if (detail !== prevDesc) entry.description = detail
    return entry
  })
  const byName = new Map<string, string>()
  for (const { place: p, key } of keyed) {
    if (!byName.has(p.name)) byName.set(p.name, key)
  }
  // Travel is derived from the form's connections: each place's
  // "connected to" names exactly one directed leg. Renames are safe
  // because pairs reference stable keys.
  const pairs: string[][] = []
  const seenPairs = new Set<string>()
  for (const { place: p, key: src } of keyed) {
    const target = p.connectedTo.trim()
    if (!target) continue
    const dst = byName.get(target)
    if (dst === undefined || src === dst) continue
    const id = `${src}→${dst}`
    if (seenPairs.has(id)) continue
    seenPairs.add(id)
    pairs.push([src, dst])
  }
  const prevTravel = Array.isArray(prev['travel']) ? prev['travel'] : []
  const start = keyed.find(({ place: p }) => p.id === draft.startPlace) ?? keyed[0] ?? null
  const out: WorldServerFields = {}
  if (draft.details !== prevString(prev, 'description')) out.description = draft.details
  if (lore !== prevString(prev, 'lore')) out.lore = lore
  // Locations always ship when places exist: renames and detail edits
  // must land even when the key set is unchanged.
  if (keyed.length > 0) {
    out.locations = locations
    const startKey = start ? start.key : ''
    if (startKey !== prevString(prev, 'starting_location_key')) {
      out.starting_location_key = startKey
    }
    if (
      JSON.stringify(pairs) !== JSON.stringify(prevTravel) &&
      (pairs.length > 0 || prevTravel.length > 0)
    ) {
      out.travel = pairs
    }
  } else {
    // No places left is not publishable server-side (min 1 location):
    // say so explicitly instead of silently keeping the old map.
    out.locations = []
  }
  return out
}

/** Restore the world form from packed (or server) fields. */
export function unpackWorld(fields: Record<string, unknown>): Partial<WorldDraft> {
  const out: Partial<WorldDraft> = {}
  if (typeof fields['description'] === 'string') out.details = fields['description']
  if (typeof fields['lore'] === 'string') {
    const s = splitSections(fields['lore'], LORE_PREFIXES)
    const terrain = s.values['Terrain'] ?? ''
    out.terrain = terrain
      ? terrain
          .split(';')
          .map((t) => t.trim())
          .filter(Boolean)
      : []
    out.climate = s.values['Climate'] ?? ''
    out.architecture = s.values['Architecture'] ?? ''
    out.exclusions = s.values['Exclusions'] ?? ''
    out.loreExtra = s.rest
  }
  if (Array.isArray(fields['locations'])) {
    const places: PlaceDraft[] = []
    for (const item of fields['locations'] as unknown[]) {
      if (typeof item !== 'object' || item === null) continue
      const rec = item as Record<string, unknown>
      if (typeof rec['name'] !== 'string') continue
      const detail = typeof rec['description'] === 'string' ? rec['description'] : ''
      const s = splitSections(detail, PLACE_PREFIXES)
      places.push({
        id: `place-${places.length}`,
        key: normalizePlaceKey(rec['name'], rec['key'], `place-${places.length + 1}`),
        name: rec['name'],
        type: s.values['Type'] || 'Other',
        purpose: s.values['Purpose'] ?? '',
        appearance: s.values['Appearance'] ?? '',
        landmark: s.values['Landmark'] ?? '',
        connectedTo: s.values['Connected to'] ?? '',
        sounds: s.values['Texture'] ?? '',
        detailExtra: s.rest
      })
    }
    if (places.length > 0) {
      out.places = places
      const startKey =
        typeof fields['starting_location_key'] === 'string' ? fields['starting_location_key'] : null
      const start = (startKey ? places.find((p) => p.key === startKey) : undefined) ?? places[0]!
      // The inspected tab opens on the starting place, but the two stay
      // independent afterwards: tab clicks never move the starting pin.
      out.startPlace = start.id
      out.activePlace = start.id
    }
  }
  return out
}

/**
 * Follow a place rename across dependent references: every other place
 * whose connection names the old name is repointed at the new one.
 * Connections are name-based in the form (keys stay stable underneath),
 * so without this a rename would silently drop the route. Returns the
 * number of references repointed.
 */
export function renamePlaceReferences(
  places: PlaceDraft[],
  placeId: string,
  from: string,
  to: string
): number {
  if (from === to) return 0
  if (!places.some((p) => p.id === placeId)) return 0
  let repaired = 0
  for (const p of places) {
    if (p.id !== placeId && p.connectedTo === from) {
      p.connectedTo = to
      repaired += 1
    }
  }
  return repaired
}

/**
 * Remove a form place explicitly, repairing dependent references: other
 * places connected to it by name are disconnected, and the starting and
 * inspected tabs fall back to the first remaining place. The last place
 * cannot be removed (an empty map is not publishable). Returns false
 * when nothing was removed.
 */
export function removeWorldPlace(draft: WorldDraft, id: string): boolean {
  if (draft.places.length <= 1) return false
  const idx = draft.places.findIndex((p) => p.id === id)
  if (idx < 0) return false
  const removed = draft.places[idx]
  if (removed === undefined) return false
  draft.places.splice(idx, 1)
  for (const p of draft.places) {
    if (p.connectedTo === removed.name) p.connectedTo = ''
  }
  const fallback = draft.places[0]!.id
  if (draft.startPlace === id) draft.startPlace = fallback
  if (draft.activePlace === id) draft.activePlace = fallback
  return true
}
