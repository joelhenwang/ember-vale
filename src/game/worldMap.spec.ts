import { describe, expect, it } from 'vitest'
import type { PresetDetail } from '../../content/clients/worldsim'
import {
  MAX_BENDS,
  SNAP,
  boardFromPreset,
  describePhases,
  nearestPlace,
  roadProblem,
  stretchMiddles,
  withBend,
  placesFromReading,
  roadLength,
  roadsFromReading,
  saveProblem,
  saveRequest,
  timedRoads,
  toPhases,
  travelPhases,
  type Board
} from './worldMap'

const world = [
  { key: 'hearth', name: 'Hearth' },
  { key: 'market', name: 'Market' }
]

describe('travel time', () => {
  it('scales between the shortest and the longest road, like the server', () => {
    expect(travelPhases([100, 300, 500], 2, 10)).toEqual([2, 6, 10])
    expect(travelPhases([40, 40], 2, 10)).toEqual([2, 2])
    expect(travelPhases([0, 1, 2], 1, 2)).toEqual([1, 2, 2]) // half rounds up
    expect(travelPhases([], 1, 5)).toEqual([])
  })

  it('measures length on the picture, not on the 0..1000 grid', () => {
    const across = roadLength(
      [
        [0, 500],
        [1000, 500]
      ],
      2000,
      1000
    )
    const down = roadLength(
      [
        [500, 0],
        [500, 1000]
      ],
      2000,
      1000
    )
    expect(across).toBeCloseTo(2 * down)
  })

  it('reads and writes times in phases and days', () => {
    expect(describePhases(3)).toBe('3 phases')
    expect(describePhases(10)).toBe('1 day')
    expect(describePhases(24)).toBe('2 days 4 phases')
    expect(describePhases(11)).toBe('1 day 1 phase')
    expect(toPhases(2, 'days')).toBe(20)
    expect(toPhases(0, 'phases')).toBe(1)
  })
})

describe('the board', () => {
  it('matches found places to the world by name and leaves roads and seas off', () => {
    const places = placesFromReading(
      [
        { name: 'hearth', kind: 'inn', point: [100, 100] },
        { name: 'Old Mill', kind: 'mill', point: [900, 2000] },
        { name: 'King’s Road', kind: 'road', point: [500, 500] }
      ],
      world
    )
    expect(places.map((p) => [p.key, p.keep])).toEqual([
      ['hearth', true],
      [null, true],
      [null, false]
    ])
    expect(places[1]!.point).toEqual([900, 1000])
  })

  it('leaves scenery and parts of other places off', () => {
    const places = placesFromReading(
      [
        { name: 'Corvane', kind: 'city', point: [300, 500] },
        { name: 'Corvane harbor', kind: 'port', point: [340, 540] },
        { name: 'Corvane Road', kind: 'town', point: [900, 900] }, // far away: its own place
        { name: 'Witchmire forest', kind: 'forest', point: [700, 100] },
        { name: 'Hollow Isle', kind: 'island', point: [600, 600] }
      ],
      []
    )
    expect(places.map((p) => p.keep)).toEqual([true, false, true, false, true])
  })

  it('times only roads between kept places and builds the save request', () => {
    const places = placesFromReading(
      [
        { name: 'Hearth', kind: 'inn', point: [0, 0] },
        { name: 'River', kind: 'river', point: [500, 0] },
        { name: 'Market', kind: 'market', point: [1000, 0] },
        { name: 'Mill', kind: 'mill', point: [1000, 500] }
      ],
      world
    )
    const kept = places.filter((p) => p.keep)
    const board: Board = {
      assetId: 'a1',
      width: 1000,
      height: 1000,
      places,
      roads: roadsFromReading(
        [
          { a: 0, b: 1, by: 'road', points: [] },
          { a: 1, b: 2, by: 'path', points: [] }
        ],
        kept
      )
    }
    board.roads.push({ a: places[0]!.id, b: places[1]!.id, by: 'river', points: [] })
    const timed = timedRoads(board, 2, 6)
    expect(timed.map((t) => t.phases)).toEqual([6, 2]) // the river road is off
    const request = saveRequest(board, 2, 6, 4)
    expect(request.places.map((p) => p.name)).toEqual(['Hearth', 'Market', 'Mill'])
    expect((request.roads ?? []).map((r) => [r.a, r.b])).toEqual([
      [0, 1],
      [1, 2]
    ])
    expect(request.expected_version).toBe(4)
    expect(saveProblem(board)).toBeNull()
    places[2]!.key = 'hearth'
    expect(saveProblem(board)).toBe('Two pins are the same world place.')
  })

  it('reopens a saved map', () => {
    const detail = {
      id: 'w',
      kind: 'world',
      name: 'Vale',
      builtin: false,
      readonly: false,
      current_revision: 2,
      version: 1,
      revision: {
        locations: world,
        map: {
          asset_id: 'a9',
          width: 1600,
          height: 900,
          pins: [
            { key: 'hearth', kind: 'inn', point: [10, 20] },
            { key: 'market', kind: 'market', point: [30, 40] }
          ],
          roads: [{ a: 'hearth', b: 'market', by: 'sea', points: [[20, 30]], phases: 3 }],
          scale: { shortest_phases: 2, longest_phases: 20 }
        }
      }
    } as unknown as PresetDetail
    const board = boardFromPreset(detail)!
    expect(board.places.map((p) => p.name)).toEqual(['Hearth', 'Market'])
    expect(board.roads).toEqual([
      { a: board.places[0]!.id, b: board.places[1]!.id, by: 'sea', points: [[20, 30]] }
    ])
  })
})

describe('drawing roads by hand', () => {
  const board = (): Board => ({
    assetId: 'm',
    width: 2000,
    height: 1000,
    places: [
      { id: 'h', name: 'Hearth', kind: 'inn', point: [100, 100], key: 'hearth', keep: true },
      { id: 'm', name: 'Market', kind: 'market', point: [900, 100], key: 'market', keep: true },
      { id: 'o', name: 'Rocks', kind: 'rocks', point: [500, 500], key: null, keep: false }
    ],
    roads: []
  })

  it('snaps a click near a kept place onto it, measured on the picture', () => {
    // 20 units across a 2:1 picture is 20 on the long side; 20 down is only 10.
    expect(nearestPlace(board(), [120, 100])?.id).toBe('h')
    expect(nearestPlace(board(), [100, 150])?.id).toBe('h')
    expect(nearestPlace(board(), [160, 100])).toBeNull()
    expect(nearestPlace(board(), [500, 500])).toBeNull() // left off: not a place to go
    expect(nearestPlace(board(), [120, 100], SNAP, 'h')).toBeNull()
  })

  it('refuses a road to itself, a second road, and too many bends', () => {
    const b = board()
    expect(roadProblem(b, 'h', 'h', 0)).toMatch(/two different/)
    expect(roadProblem(b, 'h', 'm', MAX_BENDS)).toBeNull()
    expect(roadProblem(b, 'h', 'm', MAX_BENDS + 1)).toMatch(/at most 16/)
    b.roads.push({ a: 'm', b: 'h', by: 'road', points: [] })
    expect(roadProblem(b, 'h', 'm', 0)).toBe('There is already a road between Hearth and Market.')
  })

  it('pulls a new bend out of the middle of a stretch', () => {
    const line: Array<[number, number]> = [
      [0, 0],
      [100, 0],
      [100, 100]
    ]
    expect(stretchMiddles(line)).toEqual([
      [50, 0],
      [100, 50]
    ])
    expect(withBend([[100, 0]], 0, [50, 0])).toEqual([
      [50, 0],
      [100, 0]
    ])
    expect(withBend([[100, 0]], 1, [100, 50])).toEqual([
      [100, 0],
      [100, 50]
    ])
    const full = Array.from({ length: MAX_BENDS }, (_, i): [number, number] => [i, i])
    expect(withBend(full, 0, [9, 9])).toBe(full)
  })
})
