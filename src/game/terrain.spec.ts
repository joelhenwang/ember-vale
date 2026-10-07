import { describe, expect, it } from 'vitest'
import {
  blankTerrain,
  cellAt,
  effortLength,
  paintTerrain,
  terrainShares,
  type Terrain
} from './terrain'
import { timedRoads, type Board } from './worldMap'

// Left half plains, right half mountains, 4 x 2 (as backend tests/test_terrain.py).
const HALVES: Terrain = { cols: 4, rows: 2, cells: 'ppmmppmm' }

describe('terrain', () => {
  it('weighs a road by what it crosses, like the server', () => {
    expect(
      effortLength(
        [
          [100, 500],
          [400, 500]
        ],
        1000,
        1000,
        HALVES
      )
    ).toBeCloseTo(300)
    expect(
      effortLength(
        [
          [600, 500],
          [900, 500]
        ],
        1000,
        1000,
        HALVES
      )
    ).toBeCloseTo(780)
    expect(
      effortLength(
        [
          [600, 500],
          [900, 500]
        ],
        1000,
        1000,
        HALVES,
        'sea'
      )
    ).toBeCloseTo(300)
    expect(
      effortLength(
        [
          [600, 500],
          [900, 500]
        ],
        1000,
        1000,
        null
      )
    ).toBeCloseTo(300)
  })

  it('times the mountain road as the long one', () => {
    const board: Board = {
      assetId: 'a',
      width: 1000,
      height: 1000,
      places: (['a', 'b', 'c', 'd'] as const).map((id, i) => ({
        id,
        name: id,
        kind: 'town',
        point: [
          [100, 500],
          [400, 500],
          [600, 500],
          [900, 500]
        ][i] as [number, number],
        key: id,
        keep: true
      })),
      roads: [
        { a: 'a', b: 'b', by: 'road', points: [] },
        { a: 'c', b: 'd', by: 'road', points: [] }
      ],
      terrain: HALVES
    }
    expect(timedRoads(board, 2, 8).map((r) => r.phases)).toEqual([2, 8])
    expect(timedRoads({ ...board, terrain: null }, 2, 8).map((r) => r.phases)).toEqual([2, 2])
  })

  it('paints cells with a brush and keeps the same grid when nothing changes', () => {
    expect(cellAt(HALVES, [999, 999])).toBe(7)
    const one = paintTerrain(HALVES, [100, 100], 'w')
    expect(one.cells).toBe('wpmmppmm')
    const wide = paintTerrain(HALVES, [300, 300], 'f', 1)
    expect(wide.cells).toBe('fffmfffm')
    expect(paintTerrain(one, [100, 100], 'w')).toBe(one)
    const blank = blankTerrain(1600, 1000)
    expect(blank.cols).toBe(24)
    expect(blank.rows).toBe(15)
    expect(terrainShares(HALVES).map((s) => [s.kind.name, s.share])).toEqual([
      ['Plains', 0.5],
      ['Mountains', 0.5]
    ])
  })
})
