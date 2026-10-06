/**
 * Adventure (player seat) display and action logic: pure, Vue-free, unit-tested.
 *
 * The log reads like a story: the scenes you are in, told in full, with
 * spoken lines under the speaker's portrait; what happened elsewhere as
 * one short line. Every action the composer sends is one of the backend's
 * action families, so the server validates it like any other intent.
 */

import type { BeatView, ChronicleEntry, SuggestionView } from '../../content/clients/worldsim'
import { QUIET_TYPES, beatTimeLabel } from './observatory'

/** Placeholder snapshot: the server binds the beat's own snapshot. */
export const NIL_SNAPSHOT = '00000000-0000-0000-0000-000000000000'

export type LogKind = 'time' | 'narration' | 'dialogue' | 'elsewhere' | 'pending'

export interface LogLine {
  key: string
  kind: LogKind
  text: string
  /** The speaker of a spoken line (dialogue), when known. */
  speakerId?: string | null
  /** The line was spoken by the player's own character. */
  mine?: boolean
  /** Elsewhere lines: where it happened. */
  placeId?: string | null
}

export interface LogInput {
  entries: ChronicleEntry[]
  /** Narration beats per scene id, once loaded. */
  beats: Record<string, BeatView[] | undefined>
  /** The player's character. */
  me: string
  /** Where the player's character is now. */
  hereId: string | null
}

/** Whether the player saw this happen (took part, or it happened where they are). */
export function isNear(entry: ChronicleEntry, me: string, hereId: string | null): boolean {
  if (entry.participant_ids?.includes(me)) return true
  return hereId !== null && entry.location_id === hereId
}

function linesFor(entry: ChronicleEntry, beats: BeatView[] | undefined, me: string): LogLine[] {
  if (beats && beats.length > 0) {
    return beats
      .filter((b) => b.kind !== 'system' && b.text.trim())
      .map((b) => {
        const spoken = b.kind === 'dialogue' && !!b.speaker_id
        return {
          key: `${entry.event_id}:${b.id}`,
          kind: spoken ? ('dialogue' as const) : ('narration' as const),
          text: b.text.trim(),
          speakerId: b.speaker_id ?? null,
          mine: spoken && b.speaker_id === me
        }
      })
  }
  if (entry.text) return [{ key: entry.event_id, kind: 'narration', text: entry.text }]
  return [{ key: entry.event_id, kind: 'pending', text: 'The scene is still being written…' }]
}

/**
 * The story so far, oldest first, with a time heading per beat. Scenes the
 * player saw are told in full; others become one "elsewhere" line, and
 * idle moments elsewhere are left out entirely.
 */
export function buildLog({ entries, beats, me, hereId }: LogInput): LogLine[] {
  const shown = [...entries]
    .filter((e) => !QUIET_TYPES.has(e.event_type))
    .sort((a, b) => a.sequence - b.sequence)
  const out: LogLine[] = []
  let lastIndex: number | null = null
  for (const entry of shown) {
    const near = isNear(entry, me, hereId)
    if (!near && entry.idle) continue
    if (entry.absolute_index !== lastIndex) {
      lastIndex = entry.absolute_index
      out.push({
        key: `t:${entry.absolute_index}`,
        kind: 'time',
        text: beatTimeLabel(entry.absolute_index)
      })
    }
    if (near) {
      out.push(...linesFor(entry, entry.scene_id ? beats[entry.scene_id] : undefined, me))
    } else if (entry.text || entry.title) {
      out.push({
        key: entry.event_id,
        kind: 'elsewhere',
        text: firstSentence(entry.text ?? entry.title),
        placeId: entry.location_id ?? null
      })
    }
  }
  return out
}

/** "At the Market, Ash looks around." under a "Meanwhile at Market" label: drop the repeat. */
export function trimPlaceLead(text: string, place: string | null | undefined): string {
  if (!place) return text
  const escaped = place.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const trimmed = text.replace(new RegExp(`^(?:at|in) (?:the )?${escaped},\\s*`, 'i'), '')
  return trimmed === text ? text : trimmed.charAt(0).toUpperCase() + trimmed.slice(1)
}

export interface PrologueInput {
  name: string
  place: string | null
  appearance?: string | null
  others: { name: string; place: string | null }[]
}

/** Who you are, where you stand, and who else is out there: the hook before turn one. */
export function prologue({ name, place, appearance, others }: PrologueInput): string[] {
  const lines = [`You are ${name}${place ? `, at the ${place}` : ''}.`]
  if (appearance?.trim()) lines.push(appearance.trim())
  const near = others.filter((o) => o.place && o.place === place).map((o) => o.name)
  const far = others.filter((o) => o.place && o.place !== place)
  if (near.length) lines.push(`${listNames(near)} ${near.length > 1 ? 'are' : 'is'} here with you.`)
  for (const other of far.slice(0, 3)) lines.push(`${other.name} is at the ${other.place}.`)
  return lines
}

function listNames(names: string[]): string {
  return names.length < 2 ? names.join('') : `${names.slice(0, -1).join(', ')} and ${names.at(-1)}`
}

/** The first sentence, so elsewhere stays a glance rather than a story. */
export function firstSentence(text: string): string {
  const clean = text.trim().replace(/\s+/g, ' ')
  const match = clean.match(/^.+?[.!?…](?=\s|$)/)
  return match ? match[0] : clean
}

/** Scenes whose narration should be fetched: seen up close and not loaded yet. */
export function scenesToLoad(input: LogInput): string[] {
  return input.entries
    .filter(
      (e) => e.scene_id && !QUIET_TYPES.has(e.event_type) && isNear(e, input.me, input.hereId)
    )
    .map((e) => e.scene_id as string)
    .filter((id) => !input.beats[id] || input.beats[id]!.length === 0)
}

/* Actions ----------------------------------------------------------------- */

export type Intent = Record<string, unknown>

const base = (me: string): Intent => ({ character_id: me, snapshot_id: NIL_SNAPSHOT })

/** Words spoken aloud to someone here (the narrator voices them as dialogue). */
export function sayIntent(me: string, targetId: string, words: string): Intent {
  const spoken = words.trim().replace(/^["“]|["”]$/g, '')
  return { ...base(me), family: 'communicate', target_character_id: targetId, topic: `"${spoken}"` }
}

/** A physical attempt in the player's own words; the resolver judges it. */
export function doIntent(me: string, attempt: string, targetId?: string | null): Intent {
  const intent: Intent = { ...base(me), family: 'interact', attempt: attempt.trim() }
  if (targetId) intent.target_character_id = targetId
  return intent
}

export function waitIntent(me: string): Intent {
  return { ...base(me), family: 'wait' }
}

/** The intent for a suggestion chip, or null when it needs words first. */
export function suggestionIntent(me: string, s: SuggestionView, words?: string): Intent | null {
  switch (s.family) {
    case 'rest':
      return { ...base(me), family: 'rest' }
    case 'observe':
      return { ...base(me), family: 'observe', focus: 'surroundings' }
    case 'move':
      return s.destination_location_id
        ? { ...base(me), family: 'move', destination_location_id: s.destination_location_id }
        : null
    case 'take':
      return s.item_instance_id
        ? { ...base(me), family: 'take', item_instance_id: s.item_instance_id }
        : null
    case 'spar':
      return s.target_character_id
        ? { ...base(me), family: 'spar', target_character_id: s.target_character_id }
        : null
    case 'communicate':
      return s.target_character_id && words?.trim()
        ? sayIntent(me, s.target_character_id, words)
        : null
    case 'appeal':
      return words?.trim() ? { ...base(me), family: 'appeal', proposition: words.trim() } : null
    default:
      return null
  }
}

/** Chips shown under the composer: one click acts, no typing needed. */
export function quickChips(suggestions: SuggestionView[]): SuggestionView[] {
  const order: Record<string, number> = { take: 0, move: 1, observe: 2, spar: 3, rest: 4 }
  return suggestions
    .filter((s) => s.family in order)
    .sort((a, b) => order[a.family] - order[b.family])
}

/* Scene framing ------------------------------------------------------------ */

/**
 * CSS for a close-up of the world map centred on a place: the painted map
 * doubles as the scene's backdrop until a place has its own art.
 */
export function sceneFocus(anchor: { x: number; y: number } | null): Record<string, string> {
  if (!anchor) return { backgroundPosition: '50% 50%', backgroundSize: 'cover' }
  const clamp = (v: number): number => Math.min(100, Math.max(0, v * 100))
  return {
    backgroundPosition: `${clamp(anchor.x)}% ${clamp(anchor.y)}%`,
    backgroundSize: '260%'
  }
}

/** Fraction for a stat bar; stats run 0..100. */
export function barFraction(value: unknown): number {
  const n = typeof value === 'number' && Number.isFinite(value) ? value : 0
  return Math.min(1, Math.max(0, n / 100))
}

/** Drive lines a studio card packs into its personality ("Wants: ..."), as on the server. */
export function cardDrives(personality: unknown): string[] {
  if (typeof personality !== 'string') return []
  const prefixes = ['Wants:', 'Avoids:', 'Under pressure:']
  return personality
    .split('\n')
    .map((line) => line.trim())
    .filter((line) => prefixes.some((p) => line.startsWith(p)) && line.length > 'Wants:'.length + 1)
}

/** A rumour is fresh for two beats after it spreads. */
export function isFresh(sinceIndex: number | undefined, nowIndex: number): boolean {
  return typeof sinceIndex === 'number' && nowIndex - sinceIndex <= 2
}

/* Turn feedback ------------------------------------------------------------ */

/** What the player can see of themselves and their surroundings at one moment. */
export interface Glimpse {
  place: string | null
  stamina: number | null
  mana: number | null
  /** Carried item names (one entry per item). */
  items: string[]
  /** Names of others where the player stands. */
  present: string[]
  /** Rumour titles heard. */
  rumours: string[]
  /** Rumour titles settled (closed with an ending). */
  settled?: string[]
}

export type ChangeTone = 'gain' | 'loss' | 'news'

export interface TurnChange {
  text: string
  tone: ChangeTone
}

function counts(names: string[]): Map<string, number> {
  const out = new Map<string, number>()
  for (const n of names) out.set(n, (out.get(n) ?? 0) + 1)
  return out
}

/** The small badges after a turn: what you gained, lost, met and heard. */
export function turnChanges(before: Glimpse, after: Glimpse): TurnChange[] {
  const out: TurnChange[] = []
  if (after.place && after.place !== before.place)
    out.push({ text: `Now at ${after.place}`, tone: 'news' })
  const was = counts(before.items)
  const now = counts(after.items)
  for (const [name, n] of now) {
    const gained = n - (was.get(name) ?? 0)
    if (gained > 0) out.push({ text: `+ ${name}${gained > 1 ? ` ×${gained}` : ''}`, tone: 'gain' })
  }
  for (const [name, n] of was) {
    const lost = n - (now.get(name) ?? 0)
    if (lost > 0) out.push({ text: `− ${name}${lost > 1 ? ` ×${lost}` : ''}`, tone: 'loss' })
  }
  for (const [label, a, b] of [
    ['Stamina', before.stamina, after.stamina],
    ['Mana', before.mana, after.mana]
  ] as const) {
    if (a !== null && b !== null && a !== b) {
      out.push({
        text: `${label} ${b > a ? '+' : '−'}${Math.abs(b - a)}`,
        tone: b > a ? 'gain' : 'loss'
      })
    }
  }
  if (after.place === before.place) {
    for (const name of after.present) {
      if (!before.present.includes(name)) out.push({ text: `${name} arrives`, tone: 'news' })
    }
    for (const name of before.present) {
      if (!after.present.includes(name)) out.push({ text: `${name} leaves`, tone: 'news' })
    }
  }
  for (const title of after.settled ?? []) {
    if (!(before.settled ?? []).includes(title)) {
      out.push({ text: `Settled: ${title}`, tone: 'gain' })
    }
  }
  for (const title of after.rumours) {
    if (!before.rumours.includes(title)) out.push({ text: `New rumour: ${title}`, tone: 'news' })
  }
  return out
}
