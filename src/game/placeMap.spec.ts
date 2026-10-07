import { describe, expect, it } from 'vitest'
import type {
  ActivityView,
  CastEntry,
  PlaceMapView,
  PresetDetail
} from '../../content/clients/worldsim'
import {
  layoutSpotTokens,
  placeMapRequest,
  presetPlaces,
  spotFor,
  spotProblem,
  spotsFromReading,
  type SpotBoard
} from './placeMap'

const spots = [
  { key: 'the-hearth', name: 'the Hearth', kind: 'inn', x: 0.4, y: 0.4 },
  { key: 'market-square', name: 'Market square', kind: 'square', x: 0.45, y: 0.52 },
  { key: 'smithy', name: 'Smithy', kind: 'smithy', x: 0.7, y: 0.45 },
  { key: 'mill', name: 'Mill', kind: 'mill', x: 0.16, y: 0.6 },
  { key: 'mill-road', name: 'Mill Road', kind: 'road', x: 0.55, y: 0.8 }
]
const village: PlaceMapView = { location_id: 'vale', asset_id: 'art', spots }

function member(id: string, name: string, where = 'vale', alive = true): CastEntry {
  return {
    character_id: id,
    name,
    life_status: alive ? 'alive' : 'dead',
    location_id: where
  } as CastEntry
}

function doing(characterId: string, kind: string): ActivityView {
  return {
    id: `a-${characterId}`,
    world_id: 'w',
    character_id: characterId,
    kind,
    status: 'active',
    start_absolute: 0,
    duration_phases: 3,
    progress_phases: 1,
    version: 1
  }
}

describe('the board', () => {
  it('keeps spots and leaves the ways through off', () => {
    const board = spotsFromReading([
      { name: 'the Hearth', kind: 'inn', point: [400, 400] },
      { name: 'Mill Road', kind: 'road', point: [550, 2000] },
      { name: 'River', kind: 'River', point: [430, 870] }
    ])
    expect(board.map((s) => [s.name, s.keep])).toEqual([
      ['the Hearth', true],
      ['Mill Road', false],
      ['River', false]
    ])
    expect(board[1]!.point).toEqual([550, 1000])
  })

  it('builds the save request from the kept spots', () => {
    const board: SpotBoard = {
      assetId: 'pic',
      width: 1672,
      height: 941,
      spots: spotsFromReading([
        { name: ' Smithy ', kind: 'smithy', point: [690, 450] },
        { name: 'River', kind: 'river', point: [430, 870] }
      ])
    }
    expect(placeMapRequest(board, 5)).toEqual({
      asset_id: 'pic',
      spots: [{ name: 'Smithy', kind: 'smithy', point: [690, 450] }],
      expected_version: 5
    })
    expect(placeMapRequest(null, 6)).toEqual({ asset_id: null, spots: [], expected_version: 6 })
    expect(spotProblem(board)).toBeNull()
    board.spots[0]!.keep = false
    expect(spotProblem(board)).toBe('Keep at least one spot.')
  })

  it('reopens the places and their saved maps', () => {
    const detail = {
      revision: {
        locations: [
          { key: 'vale', name: 'Vale', map: { asset_id: 'art', width: 10, height: 5, spots: [] } },
          { key: 'pass', name: 'Pass' }
        ]
      }
    } as unknown as PresetDetail
    const places = presetPlaces(detail)
    expect(places.map((p) => [p.key, p.map?.assetId ?? null])).toEqual([
      ['vale', 'art'],
      ['pass', null]
    ])
  })
})

describe('who is where inside a place', () => {
  it('puts people where what they do is done', () => {
    expect(spotFor('wren', 'rest', spots)?.name).toBe('the Hearth')
    expect(['Smithy', 'Mill']).toContain(spotFor('wren', 'work', spots)?.name)
    // Nothing suits patrolling but the road; a spot is still found.
    expect(spotFor('ash', 'patrol', spots)?.name).toBe('Mill Road')
    expect(spotFor('ash', null, [])).toBeNull()
  })

  it('keeps a character at the same spot between refreshes', () => {
    const first = spotFor('wren', 'work', spots)
    for (let i = 0; i < 5; i += 1) expect(spotFor('wren', 'work', spots)).toBe(first)
  })

  it('shows the living people here, not travellers or others', () => {
    const cast = [
      member('wren', 'Wren'),
      member('ash', 'Ash'),
      member('kip', 'Kip'),
      member('old', 'Old Tom', 'vale', false),
      member('far', 'Far', 'elsewhere')
    ]
    const tokens = layoutSpotTokens(village, cast, [
      doing('wren', 'rest'),
      doing('ash', 'rest'),
      doing('kip', 'travel')
    ])
    expect(tokens.map((t) => [t.name, t.spot])).toEqual([
      ['Ash', 'the Hearth'],
      ['Wren', 'the Hearth']
    ])
    // Two at one spot sit side by side around it.
    expect(tokens[0]!.x).toBeLessThan(0.4)
    expect(tokens[1]!.x).toBeGreaterThan(0.4)
    expect(tokens[0]!.y).toBe(0.4)
  })
})
