import { describe, expect, it } from 'vitest'
import type { AutoplayView, CastEntry, ChronicleEntry } from '../../content/clients/worldsim'
import {
  autoplayStatus,
  beatTimeLabel,
  groupFeed,
  layoutTokens,
  mergeChronicle,
  speedFor
} from './observatory'

const autoplay = (over: Partial<AutoplayView> = {}): AutoplayView => ({
  world_id: 'w',
  status: 'paused',
  delay_seconds: 0,
  beats_left: 0,
  beats_run: 0,
  runner_enabled: true,
  version: 1,
  ...over
})

const member = (id: string, name: string, place: string, alive = true): CastEntry => ({
  character_id: id,
  name,
  location_id: place,
  life_status: alive ? 'alive' : 'dead'
})

const entry = (seq: number, index: number, type = 'action_resolved'): ChronicleEntry => ({
  sequence: seq,
  absolute_index: index,
  event_id: `e${seq}`,
  event_type: type,
  title: `t${seq}`
})

describe('beatTimeLabel', () => {
  it('maps absolute indices onto days of ten phases', () => {
    expect(beatTimeLabel(0)).toBe('Day 1 · Dawn')
    expect(beatTimeLabel(3)).toBe('Day 1 · Noon')
    expect(beatTimeLabel(10)).toBe('Day 2 · Dawn')
    expect(beatTimeLabel(19)).toBe('Day 2 · Midnight')
  })
})

describe('autoplayStatus', () => {
  const now = Date.parse('2026-10-05T12:00:00Z')

  it('counts down to the next beat while playing', () => {
    const view = autoplay({
      status: 'playing',
      beats_left: 3,
      next_due_at: '2026-10-05T12:00:12Z'
    })
    expect(autoplayStatus(view, null, now)).toBe('Playing · next beat in 12 s · 3 beats left')
  })

  it('names the stage the server reports, with time since the page saw the beat', () => {
    const beat = { state: 'director_complete', seenAtMs: now - 23_000 }
    expect(autoplayStatus(autoplay({ status: 'playing', beats_left: 2 }), beat, now)).toBe(
      'Playing · Characters are deciding… 23 s'
    )
    expect(
      autoplayStatus(autoplay({ status: 'playing' }), { state: 'mystery', seenAtMs: now }, now)
    ).toBe('Playing · A beat is unfolding… 0 s')
  })

  it('explains why autoplay stopped', () => {
    expect(autoplayStatus(autoplay({ stop_reason: 'beat_limit', beats_run: 10 }), null, now)).toBe(
      'Paused after 10 beats'
    )
    expect(autoplayStatus(autoplay({ stop_reason: 'no_observers' }), null, now)).toBe(
      'Paused · nobody was watching'
    )
    expect(
      autoplayStatus(autoplay({ stop_reason: 'error', stop_detail: 'beat 4: boom' }), null, now)
    ).toBe('Paused · a beat failed: beat 4: boom')
    expect(
      autoplayStatus(
        autoplay({ stop_reason: 'user' }),
        { state: 'scenes_assembled', seenAtMs: now },
        now
      )
    ).toBe('Pausing after this beat · Scenes are playing out… 0 s')
  })

  it('is honest when the server runs no autoplay runner', () => {
    expect(
      autoplayStatus(autoplay({ status: 'playing', runner_enabled: false }), null, now)
    ).toMatch(/switched off/)
  })
})

describe('layoutTokens', () => {
  const anchors = [
    { location_id: 'hearth', x: 0.2, y: 0.3 },
    { location_id: 'market', x: 0.8, y: 0.4 }
  ]

  it('places a lone character on its anchor', () => {
    const [token] = layoutTokens(anchors, [member('w', 'Wren', 'market')])
    expect(token).toMatchObject({ id: 'w', x: 0.8, y: 0.4, locationId: 'market' })
  })

  it('spreads co-located characters symmetrically without overlap', () => {
    const tokens = layoutTokens(anchors, [
      member('w', 'Wren', 'hearth'),
      member('a', 'Ash', 'hearth')
    ])
    expect(tokens.map((t) => t.name)).toEqual(['Ash', 'Wren'])
    expect(tokens[0].x).toBeLessThan(0.2)
    expect(tokens[1].x).toBeGreaterThan(0.2)
    expect(tokens[0].x + tokens[1].x).toBeCloseTo(0.4)
  })

  it('wraps a crowd onto a second row', () => {
    const crowd = ['a', 'b', 'c', 'd', 'e'].map((id) => member(id, id.toUpperCase(), 'hearth'))
    const tokens = layoutTokens(anchors, crowd)
    expect(new Set(tokens.map((t) => `${t.x.toFixed(3)},${t.y.toFixed(3)}`)).size).toBe(5)
    expect(tokens[4].y).toBeGreaterThan(tokens[0].y)
  })

  it('leaves out the dead and characters at unmapped places', () => {
    const tokens = layoutTokens(anchors, [
      member('g', 'Ghost', 'hearth', false),
      member('t', 'Traveller', 'road')
    ])
    expect(tokens).toEqual([])
  })
})

describe('feed', () => {
  it('groups readable events per beat, newest first, dropping bookkeeping', () => {
    const beats = groupFeed([
      entry(1, 0, 'world_seeded'),
      entry(2, 1, 'world_ticked'),
      entry(3, 1),
      entry(5, 2),
      entry(4, 1)
    ])
    expect(beats.map((b) => b.index)).toEqual([2, 1])
    expect(beats[1].entries.map((e) => e.sequence)).toEqual([3, 4])
    expect(beats[1].label).toBe('Day 1 · Sunrise')
  })

  it('merges pages by event id in source order', () => {
    const merged = mergeChronicle([entry(1, 1), entry(2, 1)], [entry(2, 1), entry(3, 2)])
    expect(merged.map((e) => e.sequence)).toEqual([1, 2, 3])
  })
})

describe('speedFor', () => {
  it('falls back to back-to-back for unknown delays', () => {
    expect(speedFor(15).key).toBe('short')
    expect(speedFor(7).key).toBe('back-to-back')
  })
})
