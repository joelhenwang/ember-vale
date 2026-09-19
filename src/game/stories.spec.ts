import { describe, expect, it } from 'vitest'
import { filterStories } from './filters'
import { setStoryArchived, storyShelf } from './stories'

const sample = [
  {
    id: 'a',
    title: 'Ashes of the Gate',
    world: 'Ember Vale',
    blurb: 'A gate, some ashes.',
    status: 'in-progress' as const,
    lastPlayedAt: 10
  },
  {
    id: 'b',
    title: 'Bell at Dusk',
    world: 'Silverleaf Coast',
    blurb: 'Bells.',
    status: 'archived' as const,
    lastPlayedAt: 40
  },
  {
    id: 'c',
    title: 'Cinders',
    world: 'Ember Vale',
    blurb: 'More fire.',
    status: 'in-progress' as const,
    lastPlayedAt: 25
  }
]

describe('filterStories', () => {
  const base = { search: '', chip: 'all', sort: 'recent' } as const
  it('sorts by recency (last played first)', () => {
    expect(filterStories(sample, base).map((s) => s.id)).toEqual(['b', 'c', 'a'])
  })
  it('sorts by title when asked', () => {
    expect(filterStories(sample, { ...base, sort: 'name' }).map((s) => s.id)).toEqual([
      'a',
      'b',
      'c'
    ])
  })
  it('splits by the status chip', () => {
    expect(filterStories(sample, { ...base, chip: 'archived' }).map((s) => s.id)).toEqual(['b'])
    expect(filterStories(sample, { ...base, chip: 'in-progress' }).length).toBe(2)
  })
  it('searches title, world and blurb', () => {
    expect(filterStories(sample, { ...base, search: 'silverleaf' }).map((s) => s.id)).toEqual(['b'])
    expect(filterStories(sample, { ...base, search: 'fire' }).length).toBe(1)
  })
})

describe('storyShelf archive toggle', () => {
  it('flips status and back (drives the ⋮ menu)', () => {
    const target = storyShelf.find((s) => s.status === 'in-progress')!
    setStoryArchived(target.id, true)
    expect(storyShelf.find((s) => s.id === target.id)!.status).toBe('archived')
    setStoryArchived(target.id, false)
    expect(storyShelf.find((s) => s.id === target.id)!.status).toBe('in-progress')
  })
  it('ignores unknown ids', () => {
    setStoryArchived('no-such-story', true)
    expect(storyShelf.every((s) => s.id !== 'no-such-story')).toBe(true)
  })
})
