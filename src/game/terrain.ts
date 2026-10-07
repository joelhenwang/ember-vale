/**
 * Terrain on a world map: a coarse grid, one letter a cell (the domain's
 * TerrainGrid in backend/src/worldsim/domain/geography.py). The map
 * reader drafts it; the player corrects it with a brush; roads through
 * hard country take longer (effortLength mirrors the domain's).
 */

import type { Point } from './worldMap'

export interface Terrain {
  cols: number
  rows: number
  /** rows of letters, top row first, joined */
  cells: string
}

export interface TerrainKind {
  letter: string
  name: string
  colour: string
  /** How much harder than open plains a stretch of road through it is. */
  cost: number
}

/** Same letters, colours and costs as the domain (TERRAIN_KINDS / _COST / _COLOURS). */
export const TERRAIN_KINDS: TerrainKind[] = [
  { letter: 'p', name: 'Plains', colour: '#b6d36b', cost: 1 },
  { letter: 'f', name: 'Forest', colour: '#2f7d3a', cost: 1.4 },
  { letter: 'h', name: 'Hills', colour: '#b8935a', cost: 1.6 },
  { letter: 'm', name: 'Mountains', colour: '#7a6a5a', cost: 2.6 },
  { letter: 's', name: 'Marsh', colour: '#5f8f7a', cost: 2 },
  { letter: 'd', name: 'Desert', colour: '#e3c77a', cost: 1.5 },
  { letter: 'i', name: 'Snow', colour: '#eef3f7', cost: 2 },
  { letter: 'w', name: 'Water', colour: '#3b82c4', cost: 1 },
  { letter: 't', name: 'Town', colour: '#c0392b', cost: 1 }
]
const BY_LETTER = new Map(TERRAIN_KINDS.map((k) => [k.letter, k]))
/** Map points run 0..1000 on each side (domain MAP_SPAN). */
const SPAN = 1000
/** Roads are weighed in steps this long, in map units (domain _TERRAIN_STEP). */
const STEP = SPAN / 100

export function terrainKind(letter: string): TerrainKind {
  return BY_LETTER.get(letter) ?? TERRAIN_KINDS[0]!
}

/** The cell under a point (map units 0..1000). */
export function cellAt(terrain: Terrain, point: Point): number {
  const col = Math.min(terrain.cols - 1, Math.max(0, Math.floor((point[0] / SPAN) * terrain.cols)))
  const row = Math.min(terrain.rows - 1, Math.max(0, Math.floor((point[1] / SPAN) * terrain.rows)))
  return row * terrain.cols + col
}

/**
 * A road's length weighed by what it crosses (plains once, mountains 2.6
 * times). Without terrain, or by sea or river, it is the drawn length.
 */
export function effortLength(
  line: Point[],
  width: number,
  height: number,
  terrain: Terrain | null | undefined,
  by = 'road'
): number {
  const longer = Math.max(width, height)
  const sx = width / longer
  const sy = height / longer
  let total = 0
  for (let i = 1; i < line.length; i += 1) {
    const [x1, y1] = line[i - 1]!
    const [x2, y2] = line[i]!
    const length = Math.hypot((x2 - x1) * sx, (y2 - y1) * sy)
    if (!terrain || by === 'sea' || by === 'river') {
      total += length
      continue
    }
    const steps = Math.max(1, Math.ceil(length / STEP))
    for (let n = 0; n < steps; n += 1) {
      const t = (n + 0.5) / steps
      const at: Point = [x1 + (x2 - x1) * t, y1 + (y2 - y1) * t]
      total += (length / steps) * terrainKind(terrain.cells[cellAt(terrain, at)]!).cost
    }
  }
  return total
}

/** The grid with the cells around a point (radius in cells, 0 = one) set to a kind. */
export function paintTerrain(terrain: Terrain, point: Point, letter: string, radius = 0): Terrain {
  const centre = cellAt(terrain, point)
  const cr = Math.floor(centre / terrain.cols)
  const cc = centre % terrain.cols
  const cells = terrain.cells.split('')
  for (let r = cr - radius; r <= cr + radius; r += 1) {
    for (let c = cc - radius; c <= cc + radius; c += 1) {
      if (r < 0 || c < 0 || r >= terrain.rows || c >= terrain.cols) continue
      cells[r * terrain.cols + c] = letter
    }
  }
  const next = cells.join('')
  return next === terrain.cells ? terrain : { ...terrain, cells: next }
}

/** An even grid of one kind, the shape of a map (about 24 cells across). */
export function blankTerrain(width: number, height: number, letter = 'p'): Terrain {
  const cols = 24
  const rows = Math.max(4, Math.min(48, Math.round((cols * height) / Math.max(1, width))))
  return { cols, rows, cells: letter.repeat(cols * rows) }
}

/** How much of the map each kind covers, largest first. */
export function terrainShares(terrain: Terrain): Array<{ kind: TerrainKind; share: number }> {
  const counts = new Map<string, number>()
  for (const c of terrain.cells) counts.set(c, (counts.get(c) ?? 0) + 1)
  return [...counts.entries()]
    .map(([letter, n]) => ({ kind: terrainKind(letter), share: n / terrain.cells.length }))
    .sort((a, b) => b.share - a.share)
}
