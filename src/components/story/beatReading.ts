/**
 * Pure reading helpers for the room's beat cards (no Vue, no fetches).
 *
 * The attribution rule lives here so it is covered by deterministic
 * fixtures: spoken lines come from persisted DIALOGUE beats only. Scene
 * resolution outcome never proves an individual utterance committed —
 * the backend's commitment check reads the reaction's own status, which
 * the scene API does not expose — so no speech (and no "not committed")
 * is ever inferred from the outcome. Supplementary intent/reaction
 * topics stay verbatim records in Beat details, quoted or not.
 * Intent/reaction `detail` may be redacted for the viewer (null): then
 * there is no topic to render at all.
 */
import type { BeatView, SceneDetail } from '../../../content/clients/worldsim'

/** Backend attempt summaries arrive prefixed (`attempt:wait: …`): records, not prose. */
export function isAttemptRecord(text: string): boolean {
  return /^attempt:[a-z_]+:/.test(text.trim())
}

/** An explicitly quoted utterance (`"…"`) as opposed to a bare topic. */
export function isQuotedSpeech(text: string): boolean {
  const trimmed = text.trim()
  return trimmed.length > 1 && trimmed.startsWith('"') && trimmed.endsWith('"')
}

export interface CommunicateTopic {
  speakerId: string
  targetId: string | null
  topic: string
  quoted: boolean
}

function topicOf(detail: Record<string, unknown> | null | undefined): string | null {
  if (!detail || typeof detail['topic'] !== 'string') return null
  const topic = (detail['topic'] as string).trim()
  return topic ? topic : null
}

function targetOf(detail: Record<string, unknown> | null | undefined): string | null {
  if (!detail || typeof detail['target_character_id'] !== 'string') return null
  return detail['target_character_id'] as string
}

/** Communicate intents then reactions with a visible (unredacted) topic. */
export function communicateTopics(detail: SceneDetail): CommunicateTopic[] {
  const out: CommunicateTopic[] = []
  for (const intent of detail.intents ?? []) {
    if (intent.family !== 'communicate') continue
    const topic = topicOf(intent.detail)
    if (topic) {
      out.push({
        speakerId: intent.author_character_id,
        targetId: targetOf(intent.detail),
        topic,
        quoted: isQuotedSpeech(topic)
      })
    }
  }
  for (const reaction of detail.reactions ?? []) {
    if (reaction.family !== 'communicate') continue
    const topic = topicOf(reaction.detail)
    if (topic) {
      out.push({
        speakerId: reaction.reactor_character_id,
        targetId: targetOf(reaction.detail),
        topic,
        quoted: isQuotedSpeech(topic)
      })
    }
  }
  return out
}

export type ReadingBlock =
  /** Voiced line from a persisted DIALOGUE beat — the only speech source. */
  | { type: 'say'; speakerId: string | null; text: string }
  /** Narration prose, in stored order. */
  | { type: 'prose'; text: string }

export interface TopicRecord {
  speakerId: string
  targetId: string | null
  topic: string
  quoted: boolean
}

export interface SceneReading {
  /** Dialogue and prose in the stored narration order (never grouped). */
  blocks: ReadingBlock[]
  /**
   * Verbatim communicate topics for Beat details. Quotation marks are
   * preserved as written, but no speech — and no commitment claim in
   * either direction — is inferred: the resolution outcome does not prove
   * an individual utterance committed.
   */
  records: TopicRecord[]
}

/**
 * Blocks for one scene. Only persisted DIALOGUE beats speak; topics are
 * records regardless of quotation or outcome.
 */
export function readScene(detail: SceneDetail, narration: BeatView[]): SceneReading {
  const blocks: ReadingBlock[] = []
  for (const beat of narration) {
    if (beat.kind === 'dialogue') {
      blocks.push({ type: 'say', speakerId: beat.speaker_id ?? null, text: beat.text })
    } else if (!isAttemptRecord(beat.text ?? '')) {
      blocks.push({ type: 'prose', text: beat.text })
    }
  }
  const records: TopicRecord[] = communicateTopics(detail).map((topic) => ({
    speakerId: topic.speakerId,
    targetId: topic.targetId,
    topic: topic.topic,
    quoted: topic.quoted
  }))
  return { blocks, records }
}

export interface ScenePointer {
  eventId: string
  sceneIds: string[]
  fallback: boolean
}

/**
 * Every distinct scene pointer in a beat, in timeline order. A beat with
 * two resolved scenes yields two pointers — the card must not stop at the
 * first.
 */
export function collectScenePointers(
  entries: Array<{ event_id: string }>,
  refs: Record<string, { sceneIds: string[]; fallback: boolean }>
): ScenePointer[] {
  const out: ScenePointer[] = []
  const seen = new Set<string>()
  for (const entry of entries) {
    if (seen.has(entry.event_id)) continue
    seen.add(entry.event_id)
    const ref = refs[entry.event_id]
    if (ref && ref.sceneIds.length > 0) {
      out.push({ eventId: entry.event_id, sceneIds: ref.sceneIds, fallback: ref.fallback })
    }
  }
  return out
}

/** Distinct cited fact keys across a scene's narration beats, in order. */
export function sceneCitations(narration: BeatView[]): string[] {
  const out: string[] = []
  for (const beat of narration) {
    for (const key of beat.cited_fact_keys ?? []) {
      if (!out.includes(key)) out.push(key)
    }
  }
  return out
}

const EVENT_LABELS: Record<string, string> = {
  world_seeded: 'The story begins',
  world_ticked: 'Time passes',
  macro_ticked: 'Meanwhile, far off',
  action_resolved: 'What happened',
  deity_override: 'A hand from above',
  schedule_fired: 'As planned',
  world_ended: 'The end',
  condition_tick: 'How they fare'
}

/** A story event's kind in plain words ("action_resolved" → "What happened"). */
export function eventLabel(type: string): string {
  return EVENT_LABELS[type] ?? type.replace(/_/g, ' ')
}
