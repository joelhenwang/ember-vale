import { reactive } from 'vue'
import type { SortMode } from './filters'
import type { ImageSlot } from './model'

/**
 * The Stories shelf — every saved tale the player can return to.
 *
 * `storyShelf` stands in for the save directory (in production: one record
 * per story, written by the story engine after every beat). The UI filters
 * and sorting are `storiesUi` + `filters.filterStories`, mirroring how the
 * Library page is wired, so this module stays view-agnostic and testable.
 */

export type StoryStatus = 'in-progress' | 'archived'
export type StoryTimeOfDay = 'Morning' | 'Afternoon' | 'Evening' | 'Night'

export interface StoryRecord {
  id: string
  title: string
  world: string
  /** Banner slot — the scene art shown on the card. */
  sceneSlot: ImageSlot
  status: StoryStatus
  /** Watcher stories have no player avatar; player stories name one. */
  mode: { kind: 'watcher' } | { kind: 'player'; characterId: string }
  day: number
  timeOfDay: StoryTimeOfDay
  blurb: string
  /** Character ids, resolved to portraits through the catalog. */
  cast: string[]
  /** Backend metadata version — required for archive/restore calls. */
  version?: number
  /** Relative epoch — display strings are pre-composed (mockup parity). */
  lastPlayedAt: number
  lastPlayedLabel: string
}

export const storyShelf = reactive<StoryRecord[]>([
  {
    id: 'whispers-of-ember-vale',
    title: 'Whispers of Ember Vale',
    world: 'Ember Vale',
    sceneSlot: 'world.emberVale',
    status: 'in-progress',
    mode: { kind: 'watcher' },
    day: 8,
    timeOfDay: 'Afternoon',
    blurb: 'Ash reached the Market while Wren remained at Hearth.',
    cast: ['wren', 'ash'],
    lastPlayedAt: 20,
    lastPlayedLabel: 'Played 20 minutes ago'
  },
  {
    id: 'the-lantern-road',
    title: 'The Lantern Road',
    world: 'Ember Vale',
    sceneSlot: 'scene.hearth',
    status: 'in-progress',
    mode: { kind: 'player', characterId: 'wren' },
    day: 3,
    timeOfDay: 'Evening',
    blurb: 'A stranger at Hearth offered a map with one place missing.',
    cast: ['wren', 'ash'],
    lastPlayedAt: 40,
    lastPlayedLabel: 'Played yesterday'
  },
  {
    id: 'tides-of-silverleaf',
    title: 'Tides of Silverleaf',
    world: 'Silverleaf Coast',
    sceneSlot: 'world.silverleaf',
    status: 'in-progress',
    mode: { kind: 'watcher' },
    day: 12,
    timeOfDay: 'Morning',
    blurb: 'The harbor wakes as a ship returns without its captain.',
    cast: ['wren', 'ash', 'lyria'],
    lastPlayedAt: 3 * 1440,
    lastPlayedLabel: 'Played 3 days ago'
  },
  {
    id: 'the-quiet-cartographer',
    title: 'The Quiet Cartographer',
    world: 'Ember Vale',
    sceneSlot: 'scene.market',
    status: 'archived',
    mode: { kind: 'player', characterId: 'nessa' },
    day: 21,
    timeOfDay: 'Night',
    blurb: 'A mapmaker drew a road that only appears on rainy nights.',
    cast: ['nessa', 'thomas'],
    lastPlayedAt: 30 * 1440,
    lastPlayedLabel: 'Archived last month'
  }
])

/** Toolbar state for the Stories page (kept out of the component on purpose). */
export const storiesUi = reactive({
  search: '',
  chip: 'all' as 'all' | 'in-progress' | 'archived',
  sort: 'recent' as SortMode,
  view: 'grid' as 'grid' | 'list'
})

export function setStoryArchived(id: string, archived: boolean): void {
  const s = storyShelf.find((x) => x.id === id)
  if (s) s.status = archived ? 'archived' : 'in-progress'
}
