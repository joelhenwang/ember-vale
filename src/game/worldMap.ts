/**
 * A world drawn on a map: its pins, its roads and how long they take.
 * Vue-free: the board state, travel times and the save request.
 *
 * Points run 0..1000 across the picture's width and height. Travel time
 * follows drawn length: the shortest road takes what the player says the
 * shortest takes, the longest likewise, and the rest scale in between.
 * The server repeats this sum when it saves (domain/geography.py).
 */
import type {
  MapPlaceView,
  MapRoadView,
  PresetDetail,
  WorldMapRequest
} from '../../content/clients/worldsim'

export const MAP_SPAN = 1000
export const PHASES_PER_DAY = 10
export const MAX_PLACES = 64

export type Point = [number, number]

export interface BoardPlace {
  /** Local id, stable while the page is open. */
  id: string
  name: string
  kind: string
  point: Point
  /** The world place this pin is; null adds a new place. */
  key: string | null
  /** Left off the world when false. */
  keep: boolean
}

export interface BoardRoad {
  a: string
  b: string
  by: string
  points: Point[]
}

export interface Board {
  assetId: string
  width: number
  height: number
  places: BoardPlace[]
  roads: BoardRoad[]
}

export interface WorldPlace {
  key: string
  name: string
}

/** Things a traveller goes along, not to: off by default when found. */
const THOROUGHFARES = new Set([
  'road',
  'path',
  'track',
  'trail',
  'river',
  'stream',
  'sea',
  'ocean',
  'coast'
])

/** Scenery around the places: off by default, the player can keep any. */
const SCENERY = new Set([
  'forest',
  'wood',
  'woods',
  'jungle',
  'mountains',
  'mountain',
  'range',
  'hills',
  'hill',
  'swamp',
  'marsh',
  'bog',
  'wetland',
  'lake',
  'field',
  'fields',
  'farmland',
  'plains',
  'desert',
  'islets',
  'rocks'
])

export function isThoroughfare(kind: string): boolean {
  return THOROUGHFARES.has(kind.trim().toLowerCase())
}

/** Whether a found place is a place to go by default. */
export function isDestination(kind: string): boolean {
  const k = kind.trim().toLowerCase()
  return !THOROUGHFARES.has(k) && !SCENERY.has(k)
}

/** Pins this close (map units) whose names nest are one place. */
const NEAR = 90

/** "Corvane harbor" next to Corvane is part of Corvane, not a stop of its own. */
function partOfAnother(place: BoardPlace, all: BoardPlace[]): boolean {
  const name = place.name.trim().toLowerCase()
  return all.some((other) => {
    if (other.id === place.id || !other.keep) return false
    const host = other.name.trim().toLowerCase()
    if (host.length < 3 || host === name || !name.includes(host)) return false
    const [x1, y1] = place.point
    const [x2, y2] = other.point
    return Math.hypot(x2 - x1, y2 - y1) <= NEAR
  })
}

let counter = 0
function localId(): string {
  counter += 1
  return `pin-${counter}`
}

function asPoint(raw: unknown): Point {
  const pair = Array.isArray(raw) ? raw : []
  const clamp = (v: unknown) => Math.max(0, Math.min(MAP_SPAN, Math.round(Number(v) || 0)))
  return [clamp(pair[0]), clamp(pair[1])]
}

/** Found places onto the board, matched to the world's places by name. */
export function placesFromReading(found: MapPlaceView[], world: WorldPlace[]): BoardPlace[] {
  const byName = new Map(world.map((p) => [p.name.trim().toLowerCase(), p.key]))
  const claimed = new Set<string>()
  const places = found.map((p): BoardPlace => {
    const match = byName.get(p.name.trim().toLowerCase()) ?? null
    const key = match && !claimed.has(match) ? match : null
    if (key) claimed.add(key)
    return {
      id: localId(),
      name: p.name,
      kind: p.kind ?? '',
      point: asPoint(p.point),
      key,
      keep: key !== null || isDestination(p.kind ?? '')
    }
  })
  for (const place of places) {
    if (place.keep && place.key === null && partOfAnother(place, places)) place.keep = false
  }
  return places
}

/** Traced roads onto the board; indexes are into the places sent. */
export function roadsFromReading(found: MapRoadView[], sent: BoardPlace[]): BoardRoad[] {
  const roads: BoardRoad[] = []
  for (const r of found) {
    const a = sent[r.a]
    const b = sent[r.b]
    if (!a || !b || a.id === b.id) continue
    roads.push({ a: a.id, b: b.id, by: r.by ?? 'road', points: (r.points ?? []).map(asPoint) })
  }
  return roads
}

/** A world's saved map back onto the board. */
export function boardFromPreset(detail: PresetDetail): Board | null {
  const revision = detail.revision as Record<string, unknown>
  const map = revision['map'] as Record<string, unknown> | null | undefined
  if (!map || typeof map['asset_id'] !== 'string') return null
  const names = new Map(worldPlaces(detail).map((p) => [p.key, p.name]))
  const idByKey = new Map<string, string>()
  const places: BoardPlace[] = []
  for (const raw of (map['pins'] as Array<Record<string, unknown>>) ?? []) {
    const key = String(raw['key'])
    const id = localId()
    idByKey.set(key, id)
    places.push({
      id,
      name: names.get(key) ?? key,
      kind: String(raw['kind'] ?? ''),
      point: asPoint(raw['point']),
      key,
      keep: true
    })
  }
  const roads: BoardRoad[] = []
  for (const raw of (map['roads'] as Array<Record<string, unknown>>) ?? []) {
    const a = idByKey.get(String(raw['a']))
    const b = idByKey.get(String(raw['b']))
    if (!a || !b) continue
    const points = Array.isArray(raw['points']) ? (raw['points'] as unknown[]).map(asPoint) : []
    roads.push({ a, b, by: String(raw['by'] ?? 'road'), points })
  }
  return {
    assetId: map['asset_id'],
    width: Number(map['width']) || 1,
    height: Number(map['height']) || 1,
    places,
    roads
  }
}

export function savedScale(detail: PresetDetail): { shortest: number; longest: number } | null {
  const map = (detail.revision as Record<string, unknown>)['map'] as
    { scale?: { shortest_phases?: number; longest_phases?: number } } | null | undefined
  const scale = map?.scale
  if (!scale?.shortest_phases || !scale.longest_phases) return null
  return { shortest: scale.shortest_phases, longest: scale.longest_phases }
}

export function worldPlaces(detail: PresetDetail): WorldPlace[] {
  const raw = (detail.revision as Record<string, unknown>)['locations']
  return Array.isArray(raw)
    ? (raw as Array<Record<string, unknown>>).map((p) => ({
        key: String(p['key']),
        name: String(p['name'])
      }))
    : []
}

/** Roads whose both ends stay on the world. */
export function liveRoads(board: Board): BoardRoad[] {
  const kept = new Set(board.places.filter((p) => p.keep).map((p) => p.id))
  return board.roads.filter((r) => kept.has(r.a) && kept.has(r.b))
}

export function roadLine(board: Board, road: BoardRoad): Point[] {
  const at = new Map(board.places.map((p) => [p.id, p.point]))
  const a = at.get(road.a)
  const b = at.get(road.b)
  return a && b ? [a, ...road.points, b] : []
}

/** Drawn length in units of the picture's longer side (domain road_length). */
export function roadLength(line: Point[], width: number, height: number): number {
  const longer = Math.max(width, height)
  const sx = width / longer
  const sy = height / longer
  let total = 0
  for (let i = 1; i < line.length; i += 1) {
    const [x1, y1] = line[i - 1]!
    const [x2, y2] = line[i]!
    total += Math.hypot((x2 - x1) * sx, (y2 - y1) * sy)
  }
  return total
}

/** Phases per road, linear between the two anchors (domain travel_phases). */
export function travelPhases(lengths: number[], shortest: number, longest: number): number[] {
  if (lengths.length === 0) return []
  const low = Math.min(...lengths)
  const high = Math.max(...lengths)
  const span = high - low
  return lengths.map((length) => {
    const share = span > 0 ? (length - low) / span : 0
    return Math.max(1, Math.floor(shortest + share * (longest - shortest) + 0.5))
  })
}

export function timedRoads(
  board: Board,
  shortest: number,
  longest: number
): Array<{ road: BoardRoad; phases: number; length: number }> {
  const roads = liveRoads(board)
  const lengths = roads.map((r) => roadLength(roadLine(board, r), board.width, board.height))
  const phases = travelPhases(lengths, shortest, longest)
  return roads.map((road, i) => ({ road, phases: phases[i]!, length: lengths[i]! }))
}

/** "3 phases", "1 day", "2 days 4 phases". */
export function describePhases(phases: number): string {
  const days = Math.floor(phases / PHASES_PER_DAY)
  const rest = phases % PHASES_PER_DAY
  const dayText = days === 1 ? '1 day' : `${days} days`
  const restText = rest === 1 ? '1 phase' : `${rest} phases`
  if (days === 0) return restText
  return rest === 0 ? dayText : `${dayText} ${restText}`
}

export type TimeUnit = 'phases' | 'days'

export function toPhases(amount: number, unit: TimeUnit): number {
  const raw = unit === 'days' ? amount * PHASES_PER_DAY : amount
  return Math.max(1, Math.min(999, Math.round(raw)))
}

/** Places sent to trace roads: the kept ones, in board order. */
export function keptPlaces(board: Board): BoardPlace[] {
  return board.places.filter((p) => p.keep)
}

export function saveRequest(
  board: Board,
  shortest: number,
  longest: number,
  expectedVersion: number
): WorldMapRequest {
  const kept = keptPlaces(board)
  const index = new Map(kept.map((p, i) => [p.id, i]))
  return {
    asset_id: board.assetId,
    places: kept.map((p) => ({
      name: p.name.trim(),
      kind: p.kind,
      point: p.point,
      key: p.key
    })),
    roads: liveRoads(board).map((r) => ({
      a: index.get(r.a)!,
      b: index.get(r.b)!,
      by: r.by,
      points: r.points
    })),
    shortest_phases: shortest,
    longest_phases: longest,
    expected_version: expectedVersion
  }
}

/** Why the board cannot be saved yet, or null. */
export function saveProblem(board: Board): string | null {
  const kept = keptPlaces(board)
  if (kept.length === 0) return 'Keep at least one place.'
  if (kept.length > MAX_PLACES) return `A world holds at most ${MAX_PLACES} places.`
  if (kept.some((p) => !p.name.trim())) return 'Every kept place needs a name.'
  const keys = kept.map((p) => p.key).filter((k): k is string => k !== null)
  if (new Set(keys).size !== keys.length) return 'Two pins are the same world place.'
  return null
}

/** A painting prompt for a map of this world. */
export function mapPrompt(worldName: string, places: WorldPlace[]): string {
  const names = places.map((p) => p.name).slice(0, 12)
  const listed = names.length ? `, with ${names.join(', ')} labelled` : ''
  return (
    `Painted fantasy world map of ${worldName}${listed}. Top-down, clear roads and paths ` +
    'between the places, sea lanes drawn as dotted lines, forests, hills and rivers, ' +
    'readable labels, parchment border.'
  )
}

/* drawing roads by hand ---------------------------------------------------- */

/** Bends a road may have between its two places (domain MapRoad). */
export const MAX_BENDS = 16
/** A click this close to a place (in units of the picture's longer side) is on it. */
export const SNAP = 28

/** Distance between two map points, measured on the picture (see roadLength). */
export function mapDistance(a: Point, b: Point, width: number, height: number): number {
  return roadLength([a, b], width, height)
}

/** The kept place nearest a point, if it is within `within`; `except` is skipped. */
export function nearestPlace(
  board: Board,
  point: Point,
  within = SNAP,
  except: string | null = null
): BoardPlace | null {
  let best: BoardPlace | null = null
  let bestDistance = within
  for (const place of keptPlaces(board)) {
    if (place.id === except) continue
    const d = mapDistance(place.point, point, board.width, board.height)
    if (d <= bestDistance) {
      best = place
      bestDistance = d
    }
  }
  return best
}

/** Why a road from a to b with these bends cannot be added, or null. */
export function roadProblem(board: Board, a: string, b: string, bends: number): string | null {
  if (a === b) return 'A road joins two different places.'
  const exists = board.roads.some((r) => (r.a === a && r.b === b) || (r.a === b && r.b === a))
  if (exists) {
    const name = (id: string) => board.places.find((p) => p.id === id)?.name ?? '?'
    return `There is already a road between ${name(a)} and ${name(b)}.`
  }
  if (bends > MAX_BENDS) return `A road has at most ${MAX_BENDS} bends.`
  return null
}

/** The middle of each stretch of a drawn line (where a new bend can be pulled out). */
export function stretchMiddles(line: Point[]): Point[] {
  const out: Point[] = []
  for (let i = 1; i < line.length; i += 1) {
    const [x1, y1] = line[i - 1]!
    const [x2, y2] = line[i]!
    out.push([Math.round((x1 + x2) / 2), Math.round((y1 + y2) / 2)])
  }
  return out
}

/**
 * A road's bends with one added in stretch `stretch` (0: between the first
 * place and the first bend); unchanged when it already has the most.
 */
export function withBend(bends: Point[], stretch: number, point: Point): Point[] {
  if (bends.length >= MAX_BENDS) return bends
  const at = Math.max(0, Math.min(bends.length, stretch))
  return [...bends.slice(0, at), point, ...bends.slice(at)]
}
