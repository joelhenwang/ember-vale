/**
 * A place's own map: a closer picture of one world place and the spots
 * inside it (the inn, the market, the smithy). Vue-free: the board the
 * library page edits, its save request, and where each character in the
 * place stands on it while a story plays.
 *
 * Board points run 0..1000 across the picture, like the world map; a
 * story's spots arrive as fractions (0..1).
 */
import type {
  ActivityView,
  CastEntry,
  ChronicleEntry,
  MapPlaceView,
  PlaceMapRequest,
  PlaceMapView,
  PlaceSpotView,
  PresetDetail
} from '../../content/clients/worldsim'
import { MAP_SPAN, type Point } from './worldMap'
import { frameFromList } from './framing'
import type { Token } from './observatory'

export const MAX_SPOTS = 32

export interface BoardSpot {
  /** Local id, stable while the page is open. */
  id: string
  name: string
  kind: string
  point: Point
  /** Left off the place when false. */
  keep: boolean
}

export interface SpotBoard {
  assetId: string
  width: number
  height: number
  spots: BoardSpot[]
}

/** Ways through a place rather than spots in it: off by default when found. */
const WAYS = new Set(['road', 'path', 'track', 'trail', 'river', 'stream', 'lake', 'sea'])

export function isSpot(kind: string): boolean {
  return !WAYS.has(kind.trim().toLowerCase())
}

let counter = 0
function localId(): string {
  counter += 1
  return `spot-${counter}`
}

function asPoint(raw: unknown): Point {
  const pair = Array.isArray(raw) ? raw : []
  const clamp = (v: unknown) => Math.max(0, Math.min(MAP_SPAN, Math.round(Number(v) || 0)))
  return [clamp(pair[0]), clamp(pair[1])]
}

/** Spots the map reader found, onto the board; past MAX_SPOTS they come unticked. */
export function spotsFromReading(found: MapPlaceView[]): BoardSpot[] {
  let kept = 0
  return found.map((p) => {
    const keep = isSpot(p.kind ?? '') && kept < MAX_SPOTS
    if (keep) kept += 1
    return { id: localId(), name: p.name, kind: p.kind ?? '', point: asPoint(p.point), keep }
  })
}

/** One world place as the preset stores it. */
export interface PresetPlace {
  key: string
  name: string
  /** The world's own words for it, when it has any. */
  description: string
  map: SpotBoard | null
}

/** The world's places, each with its own map when it has one. */
export function presetPlaces(detail: PresetDetail): PresetPlace[] {
  const raw = (detail.revision as Record<string, unknown>)['locations']
  if (!Array.isArray(raw)) return []
  return (raw as Array<Record<string, unknown>>).map((p) => {
    const map = p['map'] as Record<string, unknown> | null | undefined
    const board: SpotBoard | null =
      map && typeof map['asset_id'] === 'string'
        ? {
            assetId: map['asset_id'],
            width: Number(map['width']) || 1,
            height: Number(map['height']) || 1,
            spots: ((map['spots'] as Array<Record<string, unknown>>) ?? []).map((s) => ({
              id: localId(),
              name: String(s['name'] ?? ''),
              kind: String(s['kind'] ?? ''),
              point: asPoint(s['point']),
              keep: true
            }))
          }
        : null
    const description = typeof p['description'] === 'string' ? p['description'] : ''
    return { key: String(p['key']), name: String(p['name']), description, map: board }
  })
}

export function keptSpots(board: SpotBoard): BoardSpot[] {
  return board.spots.filter((s) => s.keep)
}

export function placeMapRequest(board: SpotBoard | null, expectedVersion: number): PlaceMapRequest {
  return {
    asset_id: board?.assetId ?? null,
    spots: board
      ? keptSpots(board).map((s) => ({ name: s.name.trim(), kind: s.kind, point: s.point }))
      : [],
    expected_version: expectedVersion
  }
}

/** Why the board cannot be saved yet, or null. */
export function spotProblem(board: SpotBoard): string | null {
  const kept = keptSpots(board)
  if (kept.length === 0) return 'Keep at least one spot.'
  if (kept.length > MAX_SPOTS) return `A place holds at most ${MAX_SPOTS} spots.`
  if (kept.some((s) => !s.name.trim())) return 'Every kept spot needs a name.'
  return null
}

/** A painting prompt for a closer picture of one place. */
export function placePrompt(
  worldName: string,
  placeName: string,
  kind = '',
  description = ''
): string {
  const an = /^[aeiou]/i.test(kind) ? 'an' : 'a'
  const what = kind ? `${an} ${kind} in ${worldName}` : `a place in ${worldName}`
  // The first sentence of the world's own description, if any, steers the picture.
  const first =
    description
      .trim()
      .split(/(?<=[.!?])\s/)[0]
      ?.slice(0, 240) ?? ''
  return (
    `Painted storybook bird's-eye view of ${placeName}, ${what}. ` +
    (first ? `${first} ` : '') +
    'Its buildings, squares, yards and gates clearly drawn and separated by lanes, ' +
    'each with a short readable label, people-sized details, warm daylight, no border.'
  )
}

/** Kinds of world place with an inside worth drawing: settlements and sites. */
const HAS_INSIDE = new Set([
  'city',
  'town',
  'village',
  'port',
  'harbor',
  'harbour',
  'camp',
  'tribe',
  'castle',
  'fort',
  'keep',
  'checkpoint',
  'gate',
  'tower',
  'lighthouse',
  'temple',
  'monastery',
  'chapel',
  'inn',
  'market',
  'smithy',
  'mill',
  'farm',
  'ruin',
  'ruins',
  'dungeon',
  'cave',
  'mine'
])

export interface InsideCandidate {
  key: string
  name: string
  description: string
  /** Kind from the world map pin, when the world has one. */
  kind: string
  /** Ticked by default: a settlement or site, or a place of unknown kind. */
  suggested: boolean
}

/** The world's places that have no map of their own yet. */
export function insideCandidates(detail: PresetDetail): InsideCandidate[] {
  const map = (detail.revision as Record<string, unknown>)['map'] as
    { pins?: Array<{ key?: string; kind?: string }> } | null | undefined
  const kinds = new Map((map?.pins ?? []).map((p) => [String(p.key), String(p.kind ?? '')]))
  return presetPlaces(detail)
    .filter((p) => p.map === null)
    .map((p) => {
      const kind = (kinds.get(p.key) ?? '').trim().toLowerCase()
      return {
        key: p.key,
        name: p.name,
        description: p.description,
        kind,
        suggested: !kind || HAS_INSIDE.has(kind)
      }
    })
}

// --- where people stand inside a place -------------------------------------

/** Spot kinds that suit what a character is doing, best first. */
const SUITS: Record<string, string[]> = {
  rest: ['inn', 'tavern', 'house', 'hall', 'manor', 'home', 'camp', 'barn', 'keep'],
  work: [
    'market',
    'shop',
    'smithy',
    'workshop',
    'mill',
    'farm',
    'dock',
    'pier',
    'warehouse',
    'stable',
    'field',
    'garden',
    'mine'
  ],
  train: ['yard', 'barracks', 'field', 'square', 'arena', 'keep'],
  patrol: ['gate', 'wall', 'tower', 'bridge', 'road', 'path', 'keep'],
  idle: [
    'square',
    'market',
    'inn',
    'tavern',
    'well',
    'chapel',
    'temple',
    'shrine',
    'garden',
    'house'
  ]
}

/** A small stable number from a string, so a spot does not change between refreshes. */
function hash(text: string): number {
  let h = 2166136261
  for (let i = 0; i < text.length; i += 1) {
    h ^= text.charCodeAt(i)
    h = Math.imul(h, 16777619)
  }
  return h >>> 0
}

/**
 * The spot a character is at: one that suits what they are doing (resting
 * at the inn, working at the market or the smithy), chosen by their id among
 * the suitable ones so a crowd spreads out; any spot when none suits.
 */
export function spotFor(
  characterId: string,
  doing: string | null,
  spots: PlaceSpotView[]
): PlaceSpotView | null {
  if (spots.length === 0) return null
  const wanted = new Set(SUITS[doing ?? 'idle'] ?? SUITS['idle'])
  const suitable = spots.filter((s) => wanted.has((s.kind ?? '').toLowerCase()))
  const pool = suitable.length ? suitable : spots.filter((s) => isSpot(s.kind ?? ''))
  const from = pool.length ? pool : spots
  return from[hash(`${characterId}|${doing ?? 'idle'}`) % from.length]!
}

/** A character inside a place, at a named spot. */
export interface SpotToken extends Token {
  spot: string
  spotKey: string
}

/** Spacing between tokens at one spot, as a fraction of the picture width. */
const TOKEN_GAP = 0.065

/**
 * Where each character's scenes say they are: the spot named by their
 * newest scene in this place that named one, while they stayed here.
 */
export function spotsFromScenes(
  placeMap: PlaceMapView,
  scenes: ChronicleEntry[]
): Map<string, string> {
  const keys = new Set((placeMap.spots ?? []).map((s) => s.key))
  const newestFirst = [...scenes].sort((a, b) => b.sequence - a.sequence)
  const out = new Map<string, string>()
  const settled = new Set<string>()
  for (const entry of newestFirst) {
    for (const id of entry.participant_ids ?? []) {
      if (settled.has(id)) continue
      // Scenes elsewhere end the search: they came from there.
      if (entry.location_id !== placeMap.location_id) settled.add(id)
      else if (entry.spot_key && keys.has(entry.spot_key)) {
        out.set(id, entry.spot_key)
        settled.add(id)
      }
      // A scene here that named no spot leaves them where they were.
    }
  }
  return out
}

/**
 * Tokens for the living characters in this place, each at their spot:
 * where their latest scene was set, else one that suits what they are
 * doing. Travellers are on the road, not here. Several at one spot sit
 * in a row.
 */
export function layoutSpotTokens(
  placeMap: PlaceMapView,
  cast: CastEntry[],
  activities: ActivityView[] = [],
  scenes: ChronicleEntry[] = []
): SpotToken[] {
  const doing = new Map<string, string>()
  for (const a of activities) if (a.status === 'active') doing.set(a.character_id, a.kind)
  const here = cast
    .filter(
      (c) =>
        c.life_status === 'alive' &&
        c.location_id === placeMap.location_id &&
        doing.get(c.character_id) !== 'travel'
    )
    .sort((a, b) => a.name.localeCompare(b.name) || a.character_id.localeCompare(b.character_id))
  const spots = placeMap.spots ?? []
  const told = spotsFromScenes(placeMap, scenes)
  const bySpot = new Map<string, CastEntry[]>()
  for (const member of here) {
    const named = told.get(member.character_id)
    const spot =
      spots.find((s) => s.key === named) ??
      spotFor(member.character_id, doing.get(member.character_id) ?? null, spots)
    if (!spot) continue
    bySpot.set(spot.key, [...(bySpot.get(spot.key) ?? []), member])
  }
  const tokens: SpotToken[] = []
  for (const spot of spots) {
    const members = bySpot.get(spot.key) ?? []
    members.forEach((member, i) => {
      tokens.push({
        id: member.character_id,
        name: member.name,
        locationId: placeMap.location_id,
        x: Number(spot.x) + (i - (members.length - 1) / 2) * TOKEN_GAP,
        y: Number(spot.y),
        portraitAssetId: member.portrait_asset_id ?? null,
        faceFrame: frameFromList(member.face_frame),
        spot: spot.name,
        spotKey: spot.key
      })
    })
  }
  return tokens
}
