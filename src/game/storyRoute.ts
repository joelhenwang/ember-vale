/**
 * Which screen a story opens on: a player plays it (Adventure), a watcher
 * watches the world map, and the director/deity seats use the story room
 * where their controls live.
 */

export type StoryScreen = 'story-adventure' | 'story-watch' | 'story-play'

type ModeLike = string | { kind: string } | null | undefined

export function storyScreen(mode: ModeLike): StoryScreen {
  const kind = (typeof mode === 'string' ? mode : (mode?.kind ?? '')).toLowerCase()
  if (kind === 'player') return 'story-adventure'
  if (kind === 'watcher' || kind === 'observer') return 'story-watch'
  return 'story-play'
}

export function storyLocation(storyId: string, mode: ModeLike) {
  return { name: storyScreen(mode), params: { storyId } }
}
