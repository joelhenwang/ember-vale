import { describe, expect, it } from 'vitest'
import type { StoryDetail } from '../../content/clients/worldsim'
import { minutesSince, sortStoriesNewest, toStoryRecord } from './records'

const DETAIL: StoryDetail = {
  absolute_index: 1,
  archived_at: null,
  day: 1,
  last_played_at: '2026-09-20T11:30:00Z',
  metadata_version: 3,
  mode: 'watcher',
  phase: 'morning',
  status: 'in_progress',
  story_id: 's1',
  title: 'A Morning in Ember Vale',
  world_id: 'w1',
  world_name: 'Ember Vale'
}

describe('record mapping', () => {
  it('maps a detail to an honest shelf record', () => {
    const record = toStoryRecord(DETAIL, {
      name: 'Ember Vale',
      description: 'A sheltered vale.'
    })
    expect(record.id).toBe('w1')
    expect(record.world).toBe('Ember Vale')
    expect(record.blurb).toBe('A sheltered vale.')
    expect(record.mode).toEqual({ kind: 'watcher' })
    expect(record.cast).toEqual([])
    expect(record.version).toBe(3)
    expect(record.lastPlayedLabel).toMatch(/^Played /)
  })

  it('falls back to derived text without inventing prose', () => {
    const record = toStoryRecord({ ...DETAIL, mode: 'player' }, { name: '', description: '' })
    expect(record.world).toBe('')
    expect(record.blurb).toBe('Day 1 · Morning')
    expect(record.mode).toEqual({ kind: 'player', characterId: '' })
  })

  it('sorts newest first with untouched stories last', () => {
    const items = [
      { ...DETAIL, world_id: 'a', title: 'B', last_played_at: null },
      { ...DETAIL, world_id: 'b', title: 'A', last_played_at: '2026-09-20T10:00:00Z' },
      { ...DETAIL, world_id: 'c', title: 'C', last_played_at: '2026-09-20T11:00:00Z' }
    ]
    expect(sortStoriesNewest(items).map((s) => s.world_id)).toEqual(['c', 'b', 'a'])
  })

  it('computes shelf epochs with -1 for never-opened', () => {
    const now = Date.parse('2026-09-20T12:00:00Z')
    expect(minutesSince('2026-09-20T11:30:00Z', now)).toBe(30)
    expect(minutesSince(null, now)).toBe(-1)
    expect(minutesSince('nope', now)).toBe(-1)
  })
})
