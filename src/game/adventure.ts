/**
 * Adventure (player seat) display and action logic: pure, Vue-free, unit-tested.
 *
 * The log reads like a story: the scenes you are in, told in full, with
 * spoken lines under the speaker's portrait; what happened elsewhere as
 * one short line. Every action the composer sends is one of the backend's
 * action families, so the server validates it like any other intent.
 */

import type {
  BeatView,
  ChronicleEntry,
  SceneArtView,
  SuggestionView
} from '../../content/clients/worldsim'
import { QUIET_TYPES, beatTimeLabel } from './observatory'

/** Placeholder snapshot: the server binds the beat's own snapshot. */
export const NIL_SNAPSHOT = '00000000-0000-0000-0000-000000000000'

export type LogKind =
  'time' | 'narration' | 'dialogue' | 'elsewhere' | 'pending' | 'picture' | 'paint'

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
  /** Paint lines: the scene (one the player took part in) that can be painted. */
  paintScene?: string | null
  /** Picture lines: the painted moment (or the one being painted). */
  picture?: SceneArtView
}

export interface LogInput {
  entries: ChronicleEntry[]
  /** Narration beats per scene id, once loaded. */
  beats: Record<string, BeatView[] | undefined>
  /** The player's character. */
  me: string
  /** Where the player's character is now. */
  hereId: string | null
  /** Painted moments, shown under their scene. */
  pictures?: SceneArtView[]
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
export function buildLog({ entries, beats, me, hereId, pictures = [] }: LogInput): LogLine[] {
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
      const lines = linesFor(entry, entry.scene_id ? beats[entry.scene_id] : undefined, me)
      const sceneId = entry.scene_id ?? null
      out.push(...lines)
      const told = lines.every((l) => l.kind !== 'pending')
      if (sceneId && told && entry.participant_ids?.includes(me)) {
        out.push({ key: `paint:${sceneId}`, kind: 'paint', text: '', paintScene: sceneId })
      }
      for (const picture of pictures) {
        if (sceneId && picture.scene_id === sceneId && picture.status !== 'failed') {
          out.push({
            key: `pic:${picture.picture_id}`,
            kind: 'picture',
            text: picture.caption,
            picture
          })
        }
      }
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

const LOOK_KEYS = [
  'Age',
  'Race',
  'Sex',
  'Hair',
  'Eyes',
  'Height',
  'Build',
  'Marks',
  'Wears',
  'Carries',
  'Condition'
] as const

/**
 * How a character looks, as prose. The studio keeps appearance as
 * "Age: 17", "Hair: …" lines (the narrator reads them as they are); a
 * reader gets sentences: who, then hair, eyes and build, then what they
 * wear. Prose without those lines comes back unchanged; what they carry
 * is left to the satchel.
 */
export function appearancePlain(text: string | null | undefined): string {
  const raw = (text ?? '').trim()
  if (!raw) return ''
  const found: Partial<Record<(typeof LOOK_KEYS)[number], string>> = {}
  const rest: string[] = []
  let current: (typeof LOOK_KEYS)[number] | null = null
  for (const line of raw.split('\n')) {
    const key = LOOK_KEYS.find((k) => line.startsWith(`${k}:`))
    if (key) {
      current = key
      found[key] = line.slice(key.length + 1).trim()
    } else if (current) {
      found[current] = `${found[current]} ${line.trim()}`.trim()
    } else if (line.trim()) {
      rest.push(line.trim())
    }
  }
  if (!Object.keys(found).length) return raw
  const soft = (t: string) => t.replace(/^[A-Z](?=[a-z ])/, (c) => c.toLowerCase())
  const end = (t: string) => (/[.!?…]$/.test(t) ? t : `${t}.`)
  const cap = (t: string) => t.charAt(0).toUpperCase() + t.slice(1)
  const age = found.Age ?? ''
  const who = [
    age ? (/^\d+$/.test(age) ? `${age} years old` : soft(age)) : '',
    found.Race ?? '',
    found.Sex ? found.Sex.toLowerCase() : '',
    found.Height && found.Height.toLowerCase() !== 'average' ? found.Height.toLowerCase() : ''
  ].filter(Boolean)
  const looks = [
    found.Hair && `${soft(found.Hair)}${/hair/i.test(found.Hair) ? '' : ' hair'}`,
    found.Eyes && `${soft(found.Eyes)}${/eye/i.test(found.Eyes) ? '' : ' eyes'}`,
    found.Build && soft(found.Build.replace(/[.]$/, '')),
    found.Marks && soft(found.Marks.replace(/[.]$/, ''))
  ].filter(Boolean) as string[]
  const out = [...rest]
  if (who.length) out.push(end(cap(who.join(', '))))
  if (looks.length) out.push(end(cap(looks.join('; '))))
  if (found.Wears) out.push(end(`Wearing ${soft(found.Wears.replace(/[.]$/, ''))}`))
  if (found.Condition) out.push(end(cap(found.Condition.replace(/[.]$/, ''))))
  return out.join(' ')
}

/** Who you are, where you stand, and who else is out there: the hook before turn one. */
export function prologue({ name, place, appearance, others }: PrologueInput): string[] {
  const lines = [`You are ${name}${place ? `, at the ${place}` : ''}.`]
  const looks = appearancePlain(appearance)
  if (looks) lines.push(looks)
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

/**
 * Scenes whose narration should be fetched: ones the player took part in
 * and not loaded yet. Players may read narration only for their own
 * scenes; what happened around them comes from the chronicle's text.
 */
export function scenesToLoad(input: LogInput): string[] {
  return input.entries
    .filter(
      (e) => e.scene_id && !QUIET_TYPES.has(e.event_type) && e.participant_ids?.includes(input.me)
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
    case 'transfer':
      return s.item_instance_id && s.target_character_id
        ? {
            ...base(me),
            family: 'transfer',
            item_instance_id: s.item_instance_id,
            target_character_id: s.target_character_id
          }
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
  const order: Record<string, number> = {
    take: 0,
    transfer: 1,
    move: 2,
    observe: 3,
    spar: 4,
    rest: 5
  }
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

/** How far through the current level, 0..1. */
export function levelProgress(renown: number, floor: number, next: number): number {
  return next > floor ? Math.min(1, Math.max(0, (renown - floor) / (next - floor))) : 1
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
  /** Renown and its level title. */
  renown?: number
  level?: number
  title?: string
}

export type ChangeTone = 'gain' | 'loss' | 'news' | 'level'

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
  if (before.renown !== undefined && after.renown !== undefined && after.renown > before.renown) {
    out.push({ text: `+${after.renown - before.renown} renown`, tone: 'gain' })
  }
  if ((after.level ?? 0) > (before.level ?? after.level ?? 0)) {
    out.push({ text: `Now known as: ${after.title ?? `level ${after.level}`}`, tone: 'level' })
  }
  return out
}

/** A "What do you do?" prompt grounded in the moment: a lead to follow or someone near. */
export function doPrompt(rumour: string | null, nearby: string[]): string {
  if (rumour) return `What do you do? — look into “${rumour}”, or anything else…`
  if (nearby.length) return `What do you do? — help ${nearby[0]}, look around, set out…`
  return 'What do you do? — search the stalls, mend the cart, follow the stranger…'
}

/** A title mid-sentence: "A stray dog" -> "a stray dog" (names keep their capitals). */
export function inSentence(title: string): string {
  return /^(A|An|The) /.test(title) ? title.charAt(0).toLowerCase() + title.slice(1) : title
}

/** A ready-made next move grounded in a rumour the player has heard. */
export interface LeadChip {
  key: string
  label: string
  intent: Intent
}

/**
 * Leads from rumours: ask someone here about the newest one, and look into
 * it yourself. Deterministic, so they cost nothing and never invent facts.
 */
export function leadChips(
  me: string,
  rumours: { title: string; purpose?: string }[],
  present: { character_id: string; name: string }[],
  places: { id: string; name: string }[] = [],
  hereId: string | null = null
): LeadChip[] {
  const lead = rumours[0]
  if (!lead) return []
  const chips: LeadChip[] = []
  // A rumour that names somewhere else is followed by going there.
  const told = `${lead.title} ${lead.purpose ?? ''}`.toLowerCase()
  const there = places.find(
    (p) => p.id !== hereId && new RegExp(`\\b${escapeRegex(p.name.toLowerCase())}\\b`).test(told)
  )
  const someone = present[0]
  if (someone) {
    chips.push({
      key: `ask:${someone.character_id}:${lead.title}`,
      label: `Ask ${someone.name} about “${lead.title}”`,
      intent: sayIntent(
        me,
        someone.character_id,
        `What do you know about ${inSentence(lead.title)}?`
      )
    })
  }
  if (there) {
    chips.push({
      key: `go:${there.id}:${lead.title}`,
      label: `Head to the ${there.name} — “${lead.title}”`,
      intent: { ...base(me), family: 'move', destination_location_id: there.id }
    })
    return chips
  }
  chips.push({
    key: `lead:${lead.title}`,
    label: `Look into “${lead.title}”`,
    intent: doIntent(me, `look into ${inSentence(lead.title)}`)
  })
  return chips
}

function escapeRegex(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

/** The light over a scene at each part of the day (CSS colour for an overlay, or none). */
export function phaseLight(phase: string | null | undefined): string | null {
  switch ((phase ?? '').toLowerCase()) {
    case 'dawn':
      return 'rgba(214, 140, 160, 0.30)'
    case 'sunrise':
      return 'rgba(240, 170, 110, 0.22)'
    case 'sunset':
      return 'rgba(230, 120, 60, 0.30)'
    case 'dusk':
      return 'rgba(150, 80, 110, 0.38)'
    case 'evening':
      return 'rgba(70, 55, 120, 0.45)'
    case 'night':
    case 'midnight':
      return 'rgba(20, 30, 70, 0.62)'
    default:
      return null
  }
}
