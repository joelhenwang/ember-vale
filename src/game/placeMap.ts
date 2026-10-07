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
  MapPlaceView,
  PlaceMapRequest,
  PlaceMapView,
  PlaceSpotView,
  PresetDetail
} from '../../content/clients/worldsim'
import { MAP_SPAN, type Point } from './worldMap'
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

/** Spots the map reader found, onto the board. */
export function spotsFromReading(found: MapPlaceView[]): BoardSpot[] {
  return found.map((p) => ({
    id: localId(),
    name: p.name,
    kind: p.kind ?? '',
    point: asPoint(p.point),
    keep: isSpot(p.kind ?? '')
  }))
}

/** One world place as the preset stores it. */
export interface PresetPlace {
  key: string
  name: string
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
    return { key: String(p['key']), name: String(p['name']), map: board }
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
export function placePrompt(worldName: string, placeName: string): string {
  return (
    `Painted storybook bird's-eye view of ${placeName}, a place in ${worldName}. ` +
    'Its buildings, squares, yards and gates clearly drawn and separated by lanes, ' +
    'each with a short readable label, people-sized details, warm daylight, no border.'
  )
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
const TOKEN_GAP = 0.05

/**
 * Tokens for the living characters in this place, each at their spot.
 * Travellers are on the road, not here. Several at one spot sit in a row.
 */
export function layoutSpotTokens(
  placeMap: PlaceMapView,
  cast: CastEntry[],
  activities: ActivityView[] = []
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
  const bySpot = new Map<string, CastEntry[]>()
  for (const member of here) {
    const spot = spotFor(member.character_id, doing.get(member.character_id) ?? null, spots)
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
        spot: spot.name,
        spotKey: spot.key
      })
    })
  }
  return tokens
}
