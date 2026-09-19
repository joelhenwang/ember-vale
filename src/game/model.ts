/**
 * Domain model for the menus and the creation wizard.
 *
 * In production every field here would be produced by the story engine
 * (LLM narrator + state tracker). The UI only ever reads these shapes, so
 * wiring the real backend later means filling the stores with real data
 * and nothing else has to change.
 */

/** Image slots the UI can request. See src/game/images.ts. */
export type ImageSlot =
  | 'hero.currentStory'
  | 'story.ashes'
  | 'story.lantern'
  | 'player.avatar'
  | 'scene.hearth'
  | 'scene.market'
  | 'character.wren'
  | 'character.ash'
  | 'character.lyria'
  | 'character.miri'
  | 'character.thomas'
  | 'character.nessa'
  | 'world.emberVale'
  | 'world.silverleaf'
  | 'world.map'
  | 'character.wren.fullbody'
  | 'library.banner'

export interface StoryBeat {
  /** In-world day counter. */
  day: number
  /** e.g. "Morning" */
  timeOfDay: string
  /** e.g. "The Market Forge" */
  location: string
}

export interface StorySummary {
  id: string
  title: string
  beat: StoryBeat
  /** Two-ish lines of the latest scene state, written by the narrator. */
  logline: string
  imageSlot: ImageSlot
  mark: 'spark' | 'leaf'
  /** "Watcher" (observer run) or "Player" (protagonist run). */
  pov: 'Watcher' | 'Player'
}

export interface CurrentStory extends StorySummary {
  /** Whimsical epigraph under the Continue button. */
  epigraph: string
}

export interface GameMenuState {
  player: {
    name: string
    avatarSlot: ImageSlot
  }
  current: CurrentStory | null
  recent: StorySummary[]
  quickStartWorld: string
  motto: string
}

/* ------------------------------------------------------------------ *
 * Library / wizard entities
 * ------------------------------------------------------------------ */

export type TagTone = 'tan' | 'green' | 'blue' | 'purple' | 'rose'

export interface Tag {
  label: string
  tone?: TagTone
}

export interface CharacterDef {
  id: string
  name: string
  role: string
  /** One-liner for the cast-picker card. */
  blurb: string
  /** Slightly longer line for the library card. */
  bio: string
  tags: Tag[]
  imageSlot: ImageSlot
  categories: Array<'companions' | 'travelers' | 'scholars' | 'locals'>
  playerReady: boolean
  usedInStories: number
  /** Monotonic recency key for "Recently updated" sorting. */
  updatedAt: number
}

export interface WorldDef {
  id: string
  name: string
  blurb: string
  tags: Tag[]
  imageSlot: ImageSlot
  places: number
  usedInStories: number
  status: 'ready' | 'draft'
  updatedAt: number
}

export interface PackDef {
  id: string
  name: string
  blurb: string
  tags: Tag[]
  usedInStories: number
  updatedAt: number
}
