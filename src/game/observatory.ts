/**
 * Observatory display logic (E5): pure, Vue-free, unit-tested.
 *
 * Positions come from the world's map manifest (place anchors) and the
 * cast's current locations, never from model output. Status lines say
 * what the server reports; nothing here invents progress.
 */

import { frameFromList, type Frame } from './framing'
import type {
  ActivityView,
  AutoplayView,
  CastEntry,
  ChronicleEntry,
  CombatRollView,
  MapAnchorView,
  MapRoadLineView
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

/** A beat the server reports as open, and when this page first saw it. */
export interface OpenBeat {
  /** Server run state (created, snapshot_sealed, director_complete, ...). */
  state: string | null
  seenAtMs: number
}

/**
 * What the open beat is doing, from the server's run state. Stages follow
 * the beat pipeline: director, decisions, scenes (react, resolve, narrate),
 * then the commit bookkeeping.
 */
export function beatStageLabel(state: string | null): string {
  switch (state) {
    case 'created':
    case 'world_ticked':
      return 'Time moves on'
    case 'snapshot_sealed':
      return 'The director looks for openings'
    case 'director_complete':
      return 'Characters are deciding'
    case 'intents_complete':
    case 'scenes_assembled':
      return 'Scenes are playing out'
    case 'scenes_committed':
    case 'perception_complete':
    case 'post_commit_queued':
    case 'completed':
      return 'Writing it into the chronicle'
    case 'paused':
      return 'The beat is paused'
    case 'retryable_failed':
      return 'The beat hit a problem'
    default:
      return 'A beat is unfolding'
  }
}

function beatLine(beat: OpenBeat, nowMs: number): string {
  const seconds = Math.max(0, Math.round((nowMs - beat.seenAtMs) / 1000))
  return `${beatStageLabel(beat.state)}… ${seconds} s`
}

/** One honest sentence for the toolbar. */
export function autoplayStatus(
  autoplay: AutoplayView | null,
  beat: OpenBeat | null,
  nowMs: number
): string {
  if (!autoplay) return 'Loading…'
  if (autoplay.status === 'playing') {
    if (!autoplay.runner_enabled) return 'Playing, but autoplay is switched off on this server'
    if (beat) return `Playing · ${beatLine(beat, nowMs)}`
    const due = autoplay.next_due_at ? Date.parse(autoplay.next_due_at) : NaN
    const left = Number.isNaN(due) ? 0 : Math.ceil((due - nowMs) / 1000)
    const beats = `${autoplay.beats_left} beat${autoplay.beats_left === 1 ? '' : 's'} left`
    return left > 1 ? `Playing · next beat in ${left} s · ${beats}` : `Playing · ${beats}`
  }
  if (beat) return `Pausing after this beat · ${beatLine(beat, nowMs)}`
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
  /** Where the face is on an imported portrait; round tokens show it. */
  faceFrame?: Frame | null
  /** On the road between two places. */
  travelling?: boolean
}

type Xy = { x: number; y: number }

/** How far along their road a traveller shows at the very least (share). */
const ON_THE_WAY = 0.12

/** The point a share (0..1) of the way along a line of points. */
export function alongLine(line: Xy[], share: number): Xy | null {
  if (line.length === 0) return null
  const legs = line.slice(1).map((p, i) => Math.hypot(p.x - line[i]!.x, p.y - line[i]!.y))
  const total = legs.reduce((a, b) => a + b, 0)
  let left = Math.max(0, Math.min(1, share)) * total
  for (let i = 0; i < legs.length; i += 1) {
    const leg = legs[i]!
    if (left <= leg || i === legs.length - 1) {
      const t = leg > 0 ? Math.min(1, left / leg) : 0
      const a = line[i]!
      const b = line[i + 1]!
      return { x: a.x + (b.x - a.x) * t, y: a.y + (b.y - a.y) * t }
    }
    left -= leg
  }
  return line[0]!
}

/** The drawn road from one place to another (reversed if drawn the other way). */
export function roadBetween(roads: MapRoadLineView[], from: string, to: string): Xy[] | null {
  for (const road of roads) {
    const line = (road.points ?? []).map((p) => ({ x: Number(p[0]), y: Number(p[1]) }))
    if (road.from_location_id === from && road.to_location_id === to) return line
    if (road.from_location_id === to && road.to_location_id === from) return line.reverse()
  }
  return null
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
export function layoutTokens(
  anchors: MapAnchorView[],
  cast: CastEntry[],
  roads: MapRoadLineView[] = [],
  activities: ActivityView[] = []
): Token[] {
  const at = new Map(anchors.map((a) => [a.location_id, { x: Number(a.x), y: Number(a.y) }]))
  const byPlace = new Map<string, CastEntry[]>()
  const tokens: Token[] = []
  // Travellers walk their road: as far along it as their journey has gone.
  const journeys = new Map(
    activities
      .filter((a) => a.kind === 'travel' && a.status === 'active')
      .map((a) => [a.character_id, a])
  )
  for (const member of cast) {
    const trip = journeys.get(member.character_id)
    if (member.life_status !== 'alive' || !trip?.from_location_id || !trip.to_location_id) continue
    const from = at.get(trip.from_location_id)
    const to = at.get(trip.to_location_id)
    if (!from || !to) continue
    const line = roadBetween(roads, trip.from_location_id, trip.to_location_id) ?? [from, to]
    const done = trip.effective_progress_phases ?? trip.progress_phases
    // Never quite at either end, so a traveller reads as on the way.
    const share = trip.duration_phases > 0 ? done / trip.duration_phases : 0
    const spot = alongLine(line, Math.max(ON_THE_WAY, Math.min(1 - ON_THE_WAY, share)))
    if (!spot) continue
    tokens.push({
      id: member.character_id,
      name: member.name,
      locationId: member.location_id,
      x: spot.x,
      y: spot.y,
      portraitAssetId: member.portrait_asset_id ?? null,
      faceFrame: frameFromList(member.face_frame),
      travelling: true
    })
  }
  const onRoad = new Set(tokens.map((t) => t.id))
  for (const member of cast) {
    if (onRoad.has(member.character_id)) continue
    if (member.life_status !== 'alive' || !at.has(member.location_id)) continue
    const list = byPlace.get(member.location_id) ?? []
    list.push(member)
    byPlace.set(member.location_id, list)
  }
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
        portraitAssetId: member.portrait_asset_id ?? null,
        faceFrame: frameFromList(member.face_frame)
      })
    })
  }
  return tokens
}

/** Bookkeeping events that say nothing to a reader. */
export const QUIET_TYPES = new Set([
  'world_seeded',
  'world_ticked',
  'macro_ticked',
  'condition_tick'
])

export interface FeedBeat {
  index: number
  label: string
  entries: ChronicleEntry[]
  /** Set when this item folds beats where everyone only waited or rested. */
  quiet?: { from: number; to: number; beats: number }
}

/** A beat in which every scene was idle (waiting or resting only). */
function isIdle(beat: FeedBeat): boolean {
  return beat.entries.length > 0 && beat.entries.every((e) => e.idle === true)
}

/**
 * Readable events grouped per beat, newest beat first, in-beat order kept.
 * Consecutive beats where everyone only waited fold into one quiet item,
 * so a night of waiting reads as one line instead of five.
 */
export function groupFeed(entries: ChronicleEntry[]): FeedBeat[] {
  const groups = new Map<number, ChronicleEntry[]>()
  // A fight's rolls are their own event; they show with their scene.
  const scenes = new Set(entries.map((e) => e.event_id))
  for (const entry of entries) {
    if (QUIET_TYPES.has(entry.event_type)) continue
    const of = entry.combat?.scene_event_id
    if (of && scenes.has(of)) continue
    const list = groups.get(entry.absolute_index) ?? []
    list.push(entry)
    groups.set(entry.absolute_index, list)
  }
  const beats = [...groups.entries()]
    .map(([index, list]) => ({
      index,
      label: beatTimeLabel(index),
      entries: [...list].sort((a, b) => a.sequence - b.sequence)
    }))
    .sort((a, b) => b.index - a.index)
  const folded: FeedBeat[] = []
  for (const beat of beats) {
    const last = folded[folded.length - 1]
    if (isIdle(beat) && last?.quiet && last.quiet.from === beat.index + 1) {
      last.quiet = { from: beat.index, to: last.quiet.to, beats: last.quiet.beats + 1 }
      last.label = `${beatTimeLabel(beat.index)} – ${beatTimeLabel(last.quiet.to)}`
      continue
    }
    if (isIdle(beat)) {
      folded.push({ ...beat, entries: [], quiet: { from: beat.index, to: beat.index, beats: 1 } })
      continue
    }
    folded.push(beat)
  }
  return folded
}

/**
 * The dice of each scene, by the scene's event id (a combat story rolls them
 * in an event of their own that names its scene). A fight whose scene is not
 * loaded keeps its rolls under its own id.
 */
export function rollsByScene(entries: ChronicleEntry[]): Map<string, CombatRollView[]> {
  const out = new Map<string, CombatRollView[]>()
  for (const e of entries) {
    const rolls = e.combat?.rolls
    if (!rolls?.length) continue
    const key = e.combat?.scene_event_id ?? e.event_id
    out.set(key, [...(out.get(key) ?? []), ...rolls])
  }
  return out
}

/** The rolls an opened entry shows: its scene's, or its own (a lone fight). */
export function rollsFor(
  byScene: Map<string, CombatRollView[]>,
  entry: ChronicleEntry
): CombatRollView[] {
  return byScene.get(entry.event_id) ?? entry.combat?.rolls ?? []
}

/** Merge a new chronicle page into what is shown, by event id. */
export function mergeChronicle(shown: ChronicleEntry[], page: ChronicleEntry[]): ChronicleEntry[] {
  const byId = new Map(shown.map((e) => [e.event_id, e]))
  for (const entry of page) byId.set(entry.event_id, entry)
  return [...byId.values()].sort((a, b) => a.sequence - b.sequence)
}
