/**
 * Backend records into the home/shelf display models (C5).
 *
 * Prose on cards comes only from real preset content (world descriptions),
 * never invented per-story text. Missing data renders as explicitly
 * unknown. Image slots are neutral covers until story covers land (E7).
 */

import type { StoryDetail, StorySummary as ApiStorySummary } from '../../content/clients/worldsim'
import { lastPlayedLabel, phaseLabel, phaseToTimeOfDay } from './format'
import type { CurrentStory, StorySummary } from './model'
import type { StoryRecord } from './stories'

export interface ResolvedWorld {
  name: string
  description: string
}

export function toStoryRecord(detail: StoryDetail, world: ResolvedWorld): StoryRecord {
  return {
    id: detail.world_id,
    title: detail.title,
    world: world.name,
    sceneSlot: 'hero.currentStory',
    status: detail.archived_at ? 'archived' : 'in-progress',
    mode: detail.mode === 'player' ? { kind: 'player', characterId: '' } : { kind: 'watcher' },
    day: detail.day,
    timeOfDay: phaseToTimeOfDay(detail.phase),
    blurb: world.description || `Day ${detail.day} · ${phaseLabel(detail.phase)}`,
    cast: [],
    lastPlayedAt: minutesSince(detail.last_played_at),
    lastPlayedLabel: lastPlayedLabel(detail.last_played_at),
    version: detail.metadata_version
  }
}

/**
 * Minutes since the ISO timestamp; -1 when never opened so shelf sorts put
 * untouched stories last. Mirrors the shelf's relative-epoch convention.
 */
export function minutesSince(iso: string | null | undefined, nowMs?: number): number {
  if (!iso) return -1
  const then = Date.parse(iso)
  if (Number.isNaN(then)) return -1
  return Math.max(0, Math.round(((nowMs ?? Date.now()) - then) / 60000))
}

export function toMenuCurrent(detail: StoryDetail, world: ResolvedWorld): CurrentStory {
  return {
    id: detail.world_id,
    title: detail.title,
    beat: { day: detail.day, timeOfDay: phaseToTimeOfDay(detail.phase), location: world.name },
    logline: world.description || `Day ${detail.day} · ${phaseLabel(detail.phase)}`,
    imageSlot: 'hero.currentStory',
    mark: 'spark',
    pov: detail.mode === 'player' ? 'Player' : 'Watcher',
    epigraph: ''
  }
}

export function toMenuRecent(detail: StoryDetail, world: ResolvedWorld): StorySummary {
  return {
    id: detail.world_id,
    title: detail.title,
    beat: { day: detail.day, timeOfDay: phaseToTimeOfDay(detail.phase), location: world.name },
    logline: world.description || `Day ${detail.day} · ${phaseLabel(detail.phase)}`,
    imageSlot: 'hero.currentStory',
    mark: 'spark',
    pov: detail.mode === 'player' ? 'Player' : 'Watcher'
  }
}

/** Newest played first; never-opened stories sort last, stable by title. */
export function sortStoriesNewest(items: readonly ApiStorySummary[]): ApiStorySummary[] {
  return [...items].sort((a, b) => {
    if (a.last_played_at === b.last_played_at) return a.title.localeCompare(b.title)
    if (!a.last_played_at) return 1
    if (!b.last_played_at) return -1
    return (b.last_played_at as string).localeCompare(a.last_played_at as string)
  })
}
