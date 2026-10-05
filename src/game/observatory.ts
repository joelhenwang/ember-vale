/**
 * Observatory display logic (E5): pure, Vue-free, unit-tested.
 *
 * Positions come from the world's map manifest (place anchors) and the
 * cast's current locations, never from model output. Status lines say
 * what the server reports; nothing here invents progress.
 */

import type {
  AutoplayView,
  CastEntry,
  ChronicleEntry,
  MapAnchorView
} from '../../content/clients/worldsim'

/** World clock order (backend PhaseName); ten phases per day. */
export const PHASES = [
  'dawn',
  'sunrise',
  'morning',
  'noon',
  'afternoon',
  'sunset',
  'dusk',
  'evening',
  'night',
  'midnight'
] as const

/** "Day 2 · Noon" for an absolute phase index (0 = day 1, dawn). */
export function beatTimeLabel(index: number): string {
  const day = Math.floor(index / PHASES.length) + 1
  const phase = PHASES[((index % PHASES.length) + PHASES.length) % PHASES.length]
  return `Day ${day} · ${phase.charAt(0).toUpperCase()}${phase.slice(1)}`
}

/** Pause between one committed beat and the next; beats themselves take time. */
export interface SpeedOption {
  key: 'back-to-back' | 'short' | 'long'
  label: string
  delaySeconds: number
}

export const SPEEDS: readonly SpeedOption[] = [
  { key: 'back-to-back', label: 'Back to back', delaySeconds: 0 },
  { key: 'short', label: 'Short pause', delaySeconds: 15 },
  { key: 'long', label: 'Long pause', delaySeconds: 60 }
]

/** Beats one Play press may run before autoplay stops on its own. */
export const BEAT_LIMITS: readonly number[] = [3, 10, 25]

export function speedFor(delaySeconds: number): SpeedOption {
  return SPEEDS.find((s) => s.delaySeconds === delaySeconds) ?? SPEEDS[0]
}

/** One honest sentence for the toolbar. */
export function autoplayStatus(
  autoplay: AutoplayView | null,
  beatOpen: boolean,
  nowMs: number
): string {
  if (!autoplay) return 'Loading…'
  if (autoplay.status === 'playing') {
    if (!autoplay.runner_enabled) return 'Playing, but autoplay is switched off on this server'
    if (beatOpen) return 'Playing · a beat is unfolding'
    const due = autoplay.next_due_at ? Date.parse(autoplay.next_due_at) : NaN
    const left = Number.isNaN(due) ? 0 : Math.ceil((due - nowMs) / 1000)
    const beats = `${autoplay.beats_left} beat${autoplay.beats_left === 1 ? '' : 's'} left`
    return left > 1 ? `Playing · next beat in ${left} s · ${beats}` : `Playing · ${beats}`
  }
  if (beatOpen) return 'Paused · finishing the current beat'
  switch (autoplay.stop_reason) {
    case 'beat_limit':
      return `Paused after ${autoplay.beats_run} beat${autoplay.beats_run === 1 ? '' : 's'}`
    case 'no_observers':
      return 'Paused · nobody was watching'
    case 'error':
      return `Paused · a beat failed${autoplay.stop_detail ? `: ${autoplay.stop_detail}` : ''}`
    case 'archived':
      return 'Paused · the story is archived'
    default:
      return 'Paused'
  }
}

export interface Token {
  id: string
  name: string
  locationId: string
  /** Fractions of the map width/height (0..1). */
  x: number
  y: number
  portraitAssetId: string | null
}

/** Spacing between clustered tokens, as a fraction of the map width. */
const TOKEN_GAP = 0.045
const PER_ROW = 4

/**
 * Character tokens at their place's anchor. Several characters at one
 * place sit in a centered row (wrapping every four) so none overlap;
 * order is by name, then id, so tokens do not jump between refreshes.
 * Characters at a place without an anchor, and the dead, are left out.
 */
export function layoutTokens(anchors: MapAnchorView[], cast: CastEntry[]): Token[] {
  const at = new Map(anchors.map((a) => [a.location_id, { x: Number(a.x), y: Number(a.y) }]))
  const byPlace = new Map<string, CastEntry[]>()
  for (const member of cast) {
    if (member.life_status !== 'alive' || !at.has(member.location_id)) continue
    const list = byPlace.get(member.location_id) ?? []
    list.push(member)
    byPlace.set(member.location_id, list)
  }
  const tokens: Token[] = []
  for (const [placeId, members] of byPlace) {
    const anchor = at.get(placeId)!
    const sorted = [...members].sort(
      (a, b) => a.name.localeCompare(b.name) || a.character_id.localeCompare(b.character_id)
    )
    sorted.forEach((member, i) => {
      const row = Math.floor(i / PER_ROW)
      const inRow = Math.min(PER_ROW, sorted.length - row * PER_ROW)
      const col = i % PER_ROW
      tokens.push({
        id: member.character_id,
        name: member.name,
        locationId: placeId,
        x: anchor.x + (col - (inRow - 1) / 2) * TOKEN_GAP,
        y: anchor.y + row * TOKEN_GAP * 1.6,
        portraitAssetId: member.portrait_asset_id ?? null
      })
    })
  }
  return tokens
}

/** Bookkeeping events that say nothing to a reader. */
const QUIET_TYPES = new Set(['world_seeded', 'world_ticked', 'macro_ticked', 'condition_tick'])

export interface FeedBeat {
  index: number
  label: string
  entries: ChronicleEntry[]
}

/** Readable events grouped per beat, newest beat first, in-beat order kept. */
export function groupFeed(entries: ChronicleEntry[]): FeedBeat[] {
  const groups = new Map<number, ChronicleEntry[]>()
  for (const entry of entries) {
    if (QUIET_TYPES.has(entry.event_type)) continue
    const list = groups.get(entry.absolute_index) ?? []
    list.push(entry)
    groups.set(entry.absolute_index, list)
  }
  return [...groups.entries()]
    .map(([index, list]) => ({
      index,
      label: beatTimeLabel(index),
      entries: [...list].sort((a, b) => a.sequence - b.sequence)
    }))
    .sort((a, b) => b.index - a.index)
}

/** Merge a new chronicle page into what is shown, by event id. */
export function mergeChronicle(shown: ChronicleEntry[], page: ChronicleEntry[]): ChronicleEntry[] {
  const byId = new Map(shown.map((e) => [e.event_id, e]))
  for (const entry of page) byId.set(entry.event_id, entry)
  return [...byId.values()].sort((a, b) => a.sequence - b.sequence)
}
