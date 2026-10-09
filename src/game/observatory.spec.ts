import { describe, expect, it } from 'vitest'
import type {
  ActivityView,
  AutoplayView,
  CastEntry,
  ChronicleEntry
} from '../../content/clients/worldsim'
import {
  alongLine,
  autoplayStatus,
  beatTimeLabel,
  groupFeed,
  rollsByScene,
  rollsFor,
  rollsInTurn,
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
    const status = autoplayStatus(view, null, now)
    expect(status).toMatch(/^Playing/)
    expect(status).toContain('12 s')
    expect(status).toContain('3 beats left')
  })

  it('names the stage the server reports, with time since the page saw the beat', () => {
    const beat = { state: 'director_complete', seenAtMs: now - 23_000 }
    const deciding = autoplayStatus(autoplay({ status: 'playing', beats_left: 2 }), beat, now)
    expect(deciding).toContain('deciding')
    expect(deciding).toContain('23 s')
    expect(
      autoplayStatus(autoplay({ status: 'playing' }), { state: 'mystery', seenAtMs: now }, now)
    ).toContain('unfolding')
  })

  it('explains why autoplay stopped', () => {
    expect(
      autoplayStatus(autoplay({ stop_reason: 'beat_limit', beats_run: 10 }), null, now)
    ).toContain('10 beats')
    expect(autoplayStatus(autoplay({ stop_reason: 'no_observers' }), null, now)).toContain(
      'nobody was watching'
    )
    expect(
      autoplayStatus(autoplay({ stop_reason: 'error', stop_detail: 'beat 4: boom' }), null, now)
    ).toContain('beat 4: boom')
    expect(
      autoplayStatus(
        autoplay({ stop_reason: 'user' }),
        { state: 'scenes_assembled', seenAtMs: now },
        now
      )
    ).toMatch(/^Pausing after this beat/)
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

  const trip = (progress: number): ActivityView => ({
    id: 't1',
    world_id: 'w',
    character_id: 'w',
    kind: 'travel',
    status: 'active',
    start_absolute: 0,
    duration_phases: 4,
    progress_phases: progress,
    from_location_id: 'market',
    to_location_id: 'hearth',
    version: 1
  })

  it('walks a traveller along the road as drawn, from where they set out', () => {
    // Drawn hearth -> bend -> market; the trip runs market -> hearth.
    const roads = [
      {
        from_location_id: 'hearth',
        to_location_id: 'market',
        by: 'road',
        points: [
          [0.2, 0.3],
          [0.2, 0.9],
          [0.8, 0.9],
          [0.8, 0.4]
        ]
      }
    ]
    const cast = [member('w', 'Wren', 'market'), member('a', 'Ash', 'market')]
    const tokens = layoutTokens(anchors, cast, roads, [trip(2)])
    const wren = tokens.find((t) => t.id === 'w')!
    expect(wren.travelling).toBe(true)
    expect(wren.x).toBeCloseTo(0.45) // 0.85 of 1.7: 0.35 into the bottom leg
    expect(wren.y).toBeCloseTo(0.9)
    expect(tokens.find((t) => t.id === 'a')).toMatchObject({ x: 0.8, y: 0.4 }) // alone now
  })

  it('takes the straight line when no road is drawn', () => {
    const [wren] = layoutTokens(anchors, [member('w', 'Wren', 'market')], [], [trip(1)])
    expect(wren).toMatchObject({ travelling: true })
    expect(wren!.x).toBeCloseTo(0.65)
    expect(alongLine([], 0.5)).toBeNull()
    const [setOut] = layoutTokens(anchors, [member('w', 'Wren', 'market')], [], [trip(0)])
    expect(setOut!.x).toBeLessThan(0.8) // already a little way along, not on the place
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

  it('folds consecutive idle beats into one quiet stretch', () => {
    const idle = (seq: number, index: number): ChronicleEntry => ({
      ...entry(seq, index),
      idle: true
    })
    const beats = groupFeed([
      entry(1, 3),
      idle(2, 4),
      idle(3, 5),
      idle(4, 6),
      entry(5, 7),
      idle(6, 8)
    ])
    expect(beats.map((b) => [b.index, b.quiet?.beats ?? 0])).toEqual([
      [8, 1],
      [7, 0],
      [6, 3],
      [3, 0]
    ])
    expect(beats[2].label).toBe('Day 1 · Afternoon – Day 1 · Dusk')
    expect(beats[2].entries).toEqual([])
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

describe('the dice in Watch', () => {
  const scene = entry(1, 4)
  const fight: ChronicleEntry = {
    ...entry(2, 4),
    combat: {
      scene_event_id: 'e1',
      rolls: [{ kind: 'attack', text: 'Wren hits Goblin 2', actor: 'Wren', target: 'Goblin 2' }]
    }
  }
  const lone: ChronicleEntry = {
    ...entry(3, 5),
    combat: { scene_event_id: 'gone', rolls: [{ kind: 'note', text: 'Old fight' }] }
  }

  it('shows a fight with its scene and keeps a lone fight on its own', () => {
    const beats = groupFeed([scene, fight, lone])
    expect(beats.flatMap((b) => b.entries.map((e) => e.event_id))).toEqual(['e3', 'e1'])
  })

  it('never folds a turn with dice into a quiet stretch', () => {
    const waited = { ...scene, idle: true }
    const beats = groupFeed([waited, fight, { ...entry(4, 3), idle: true }])
    expect(beats.map((b) => [b.index, !!b.quiet])).toEqual([
      [4, false],
      [3, true]
    ])
  })

  it('gives each scene its rolls', () => {
    const byScene = rollsByScene([scene, fight, lone])
    expect(rollsFor(byScene, scene).map((r) => r.target)).toEqual(['Goblin 2'])
    expect(rollsFor(byScene, lone).map((r) => r.text)).toEqual(['Old fight'])
    expect(rollsFor(byScene, entry(9, 6))).toEqual([])
  })

  it('keeps the dice of a turn under its scene in the story room, once', () => {
    const turn = rollsInTurn([scene, fight])
    expect([...turn.keys()]).toEqual(['e1'])
    expect(turn.get('e1')?.map((r) => r.target)).toEqual(['Goblin 2'])
    // The scene is not in this turn: the fight's own event carries its dice.
    expect([...rollsInTurn([lone]).keys()]).toEqual(['e3'])
    expect(rollsInTurn([scene]).size).toBe(0)
  })
})
