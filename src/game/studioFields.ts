/**
 * Field bridge between the studio forms and the server preset payloads (E3).
 *
 * The studio forms predate the server schemas, so this mapping is explicit
 * and tested: every packed key names a real payload field, and unpacking
 * restores the form. Keys the editor never exposes (character appearance
 * and tags, world name/travel/cast/style-pack) are never packed, so the
 * server merge preserves them verbatim.
 *
 * Section packing is line-prefix based with continuation lines, so normal
 * prose round-trips exactly. A user line that starts with a known prefix
 * is the one documented edge: it unpacks under that prefix.
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

function packSections(entries: Array<[string, string]>): string {
  return entries
    .filter(([, v]) => v.trim().length > 0)
    .map(([k, v]) => `${k}: ${v.trim()}`)
    .join('\n')
}

function unpackSections(text: string, known: readonly string[]): Record<string, string> {
  const out: Record<string, string> = {}
  let current: string | null = null
  for (const line of text.split('\n')) {
    const hit = known.find((p) => line === p || line.startsWith(`${p}:`))
    if (hit !== null && hit !== undefined) {
      current = hit
      const rest = line.slice(hit.length).replace(/^:\s?/, '')
      out[hit] = rest
    } else if (current !== null) {
      out[current] = out[current] ? `${out[current]}\n${line}` : line
    }
  }
  for (const k of known) {
    if (!(k in out)) out[k] = ''
    else out[k] = out[k].trim()
  }
  return out
}

export interface CharacterServerFields {
  personality?: string
  background?: string
}

/** Pack the character form into valid character-payload keys. */
export function packCharacter(draft: CharacterDraft): CharacterServerFields {
  const personality = packSections([
    ['Wants', draft.want],
    ['Avoids', draft.avoid],
    ['Under pressure', draft.pressure],
    ['Contradiction', draft.contradiction],
    ['With strangers', draft.withStrangers],
    ['When they care', draft.whenTheyCare],
    ['Example line', draft.exampleLine],
    ['Styles', draft.styleTags.join('; ')]
  ])
  const background = packSections([
    ['Boundaries', draft.boundaries],
    ['Secret fear', draft.secretFear]
  ])
  const out: CharacterServerFields = {}
  if (personality) out.personality = personality
  if (background) out.background = background
  return out
}

/** Restore the character form from packed (or server) fields. */
export function unpackCharacter(fields: Record<string, unknown>): Partial<CharacterDraft> {
  const out: Partial<CharacterDraft> = {}
  if (typeof fields['personality'] === 'string') {
    const s = unpackSections(fields['personality'], PERSONALITY_PREFIXES)
    out.want = s['Wants'] ?? ''
    out.avoid = s['Avoids'] ?? ''
    out.pressure = s['Under pressure'] ?? ''
    out.contradiction = s['Contradiction'] ?? ''
    out.withStrangers = s['With strangers'] ?? ''
    out.whenTheyCare = s['When they care'] ?? ''
    out.exampleLine = s['Example line'] ?? ''
    const styles = s['Styles'] ?? ''
    out.styleTags = styles
      ? styles
          .split(';')
          .map((t) => t.trim())
          .filter(Boolean)
      : []
  }
  if (typeof fields['background'] === 'string') {
    const s = unpackSections(fields['background'], BACKGROUND_PREFIXES)
    out.boundaries = s['Boundaries'] ?? ''
    out.secretFear = s['Secret fear'] ?? ''
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

export interface WorldServerFields {
  description?: string
  lore?: string
  locations?: { key: string; name: string; description?: string }[]
  starting_location_key?: string
}

function packPlace(p: PlaceDraft): string {
  return packSections([
    ['Type', p.type],
    ['Purpose', p.purpose],
    ['Appearance', p.appearance],
    ['Landmark', p.landmark],
    ['Connected to', p.connectedTo],
    ['Texture', p.sounds]
  ])
}

const PLACE_PREFIXES = [
  'Type',
  'Purpose',
  'Appearance',
  'Landmark',
  'Connected to',
  'Texture'
] as const

/** Pack the world form into valid world-payload keys. */
export function packWorld(draft: WorldDraft): WorldServerFields {
  const lore = packSections([
    ['Terrain', draft.terrain.join('; ')],
    ['Climate', draft.climate],
    ['Architecture', draft.architecture],
    ['Exclusions', draft.exclusions]
  ])
  const locations = draft.places.map((p, i) => {
    const detail = packPlace(p)
    const entry: { key: string; name: string; description?: string } = {
      key: slugPlaceKey(p.name, `place-${i + 1}`),
      name: p.name
    }
    if (detail) entry.description = detail
    return entry
  })
  const active = draft.places.find((p) => p.id === draft.activePlace) ?? draft.places[0]
  const out: WorldServerFields = {}
  if (draft.details.trim()) out.description = draft.details.trim()
  if (lore) out.lore = lore
  if (locations.length > 0) out.locations = locations
  if (active) out.starting_location_key = slugPlaceKey(active.name, 'place-1')
  return out
}

/** Restore the world form from packed (or server) fields. */
export function unpackWorld(fields: Record<string, unknown>): Partial<WorldDraft> {
  const out: Partial<WorldDraft> = {}
  if (typeof fields['description'] === 'string') out.details = fields['description']
  if (typeof fields['lore'] === 'string') {
    const s = unpackSections(fields['lore'], LORE_PREFIXES)
    const terrain = s['Terrain'] ?? ''
    out.terrain = terrain
      ? terrain
          .split(';')
          .map((t) => t.trim())
          .filter(Boolean)
      : []
    out.climate = s['Climate'] ?? ''
    out.architecture = s['Architecture'] ?? ''
    out.exclusions = s['Exclusions'] ?? ''
  }
  if (Array.isArray(fields['locations'])) {
    const places: PlaceDraft[] = []
    for (const item of fields['locations'] as unknown[]) {
      if (typeof item !== 'object' || item === null) continue
      const rec = item as Record<string, unknown>
      if (typeof rec['name'] !== 'string') continue
      const detail = typeof rec['description'] === 'string' ? rec['description'] : ''
      const s = unpackSections(detail, PLACE_PREFIXES)
      places.push({
        id: `place-${places.length}`,
        name: rec['name'],
        type: s['Type'] || 'Other',
        purpose: s['Purpose'] ?? '',
        appearance: s['Appearance'] ?? '',
        landmark: s['Landmark'] ?? '',
        connectedTo: s['Connected to'] ?? '',
        sounds: s['Texture'] ?? ''
      })
    }
    if (places.length > 0) {
      out.places = places
      const startKey =
        typeof fields['starting_location_key'] === 'string' ? fields['starting_location_key'] : null
      const match = startKey ? places.findIndex((p) => slugPlaceKey(p.name, '') === startKey) : -1
      out.activePlace = match >= 0 ? places[match]!.id : places[0]!.id
    }
  }
  return out
}
