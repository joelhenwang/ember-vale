/**
 * The world studio's steps and fields, described once, like
 * characterForm.ts: the writing helper fills from these descriptions and
 * the painters build their words from the same draft.
 */

import { CLIMATES, PLACE_TYPES, type PlaceDraft, type WorldDraft } from './studio'

export const WORLD_STEPS = [
  { title: 'Overview', sub: 'What is this world? A few lines or key points are enough.' },
  { title: 'The world', sub: 'Its land, its people and its past, in a little more detail.' },
  { title: 'Places', sub: 'Where stories can happen. Add each place and say what it is like.' },
  { title: 'Review', sub: 'Where stories start, then make it real.' }
] as const

/** Text fields of the world itself the writing helper may fill. */
export type WorldKey =
  'terrain' | 'climate' | 'architecture' | 'peoples' | 'history' | 'distinct' | 'exclusions'

export interface WorldFieldSpec {
  key: WorldKey
  label: string
  hint: string
  max: number
}

export const WORLD_FIELDS: WorldFieldSpec[] = [
  {
    key: 'terrain',
    label: 'Terrain',
    hint: 'a few kinds of land, comma separated, e.g. river valley, woodland, salt marsh',
    max: 200
  },
  {
    key: 'climate',
    label: 'Climate',
    hint: `one of: ${CLIMATES.join(', ')} (or a short phrase)`,
    max: 60
  },
  {
    key: 'architecture',
    label: 'Architecture',
    hint: 'what buildings are made of and look like',
    max: 400
  },
  {
    key: 'peoples',
    label: 'Peoples',
    hint: 'who lives here: folk, races, guilds, factions',
    max: 500
  },
  {
    key: 'history',
    label: 'History',
    hint: 'what happened here before, and what people still argue about',
    max: 800
  },
  {
    key: 'distinct',
    label: 'Distinctive details',
    hint: 'the three glances that say “you are here”',
    max: 400
  },
  {
    key: 'exclusions',
    label: 'Never in this world',
    hint: 'what this world will never contain, e.g. guns, steam engines',
    max: 200
  }
]

function fieldText(draft: WorldDraft, key: WorldKey): string {
  return key === 'terrain' ? draft.terrain.join(', ') : draft[key]
}

/** Put a written value into the draft, in the shape its field keeps. */
export function setWorldField(draft: WorldDraft, key: WorldKey, value: string): void {
  if (key === 'terrain') {
    draft.terrain = value
      .split(/[,;]/)
      .map((t) => t.trim())
      .filter(Boolean)
      .slice(0, 8)
  } else {
    draft[key] = value
  }
}

export function isWorldFieldEmpty(draft: WorldDraft, key: WorldKey): boolean {
  return !fieldText(draft, key).trim()
}

export function worldWritingFields(draft: WorldDraft) {
  return WORLD_FIELDS.map((f) => ({
    key: f.key,
    label: f.label,
    hint: f.hint,
    value: fieldText(draft, f.key),
    max_length: f.max
  }))
}

/** A place in the writing helper's words: its kind and what is written about it. */
export function placeForWriting(p: PlaceDraft): { name: string; description: string } {
  const parts = [p.purpose, p.appearance, p.landmark && `Landmark: ${p.landmark}`]
    .map((s) => s.trim())
    .filter(Boolean)
  return { name: p.name, description: parts.join(' ') }
}

/** How many world fields, and places without a word about them, are still empty. */
export function worldEmptyCount(draft: WorldDraft): number {
  return (
    WORLD_FIELDS.filter((f) => isWorldFieldEmpty(draft, f.key)).length +
    draft.places.filter((p) => !placeForWriting(p).description).length
  )
}

/** Words for painting the world as a map. */
export function worldMapPrompt(draft: WorldDraft, name: string): string {
  const places = draft.places
    .map((p) => p.name.trim())
    .filter((n) => n && n !== 'New place')
    .slice(0, 12)
  const parts = [
    `an illustrated fantasy map of ${name.trim() || 'a small realm'}, seen from above, hand-drawn on parchment`,
    draft.terrain.length ? `with ${draft.terrain.join(', ').toLowerCase()}` : '',
    draft.climate && draft.climate !== 'Temperate' ? `${draft.climate.toLowerCase()} lands` : '',
    places.length ? `labelled places: ${places.join(', ')}` : '',
    draft.details.trim().slice(0, 300)
  ].filter(Boolean)
  return parts.join('; ').slice(0, 1500)
}

/** Words for painting one place, seen from above or at an angle. */
export function placePrompt(p: PlaceDraft, draft: WorldDraft): string {
  const parts = [
    `${p.type && p.type !== 'Other' ? p.type.toLowerCase() : 'a place'} called ${p.name}`,
    p.appearance.trim(),
    p.landmark.trim() && `its landmark: ${p.landmark.trim()}`,
    draft.architecture.trim() && `buildings: ${draft.architecture.trim()}`,
    draft.climate && `${draft.climate.toLowerCase()} climate`,
    'seen from above at an angle, a detailed fantasy illustration'
  ].filter(Boolean)
  return parts.join('; ').slice(0, 1500)
}

/** The place types the writing helper may choose from. */
export const WRITABLE_PLACE_TYPES = PLACE_TYPES.filter((t) => t !== 'Other')
