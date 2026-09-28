/**
 * Pure reading helpers for the room's beat cards (no Vue, no fetches).
 *
 * The established quotation and commitment rules live here so they are
 * covered by deterministic fixtures:
 *
 * - Persisted DIALOGUE beats are speech. Nothing else speaks on its own.
 * - A `communicate` topic is a topic, not an utterance: unquoted topics
 *   render as summaries, never as speaker-labelled dialogue.
 * - A quoted topic counts as quoted speech only when the beat's
 *   resolution committed it (`outcome === 'success'`). Quoted but
 *   uncommitted utterance is an attempt, rendered with the technical
 *   detail — never in the dialogue flow.
 * - Intent/reaction `detail` may be redacted for the viewer (null): then
 *   there is no topic to render at all.
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
  /** Voiced line: persisted DIALOGUE beat, or quoted topic on a committed beat. */
  | { type: 'say'; speakerId: string | null; text: string; quoted: boolean }
  /** Communication summary: an unquoted topic. Never presented as speech. */
  | { type: 'topic'; speakerId: string; targetId: string | null; topic: string }
  /** Narration prose, in stored order. */
  | { type: 'prose'; text: string }

export interface AttemptedSpeech {
  speakerId: string
  text: string
}

export interface SceneReading {
  /** Dialogue and prose in the stored narration order (never grouped). */
  blocks: ReadingBlock[]
  /** Quoted topics on beats that did not commit: attempts, not speech. */
  attempted: AttemptedSpeech[]
}

/**
 * Blocks for one scene. Dialogue beats speak; supplementary topics fill in
 * only when nothing was voiced, and then only under the quotation and
 * commitment rules above.
 */
export function readScene(detail: SceneDetail, narration: BeatView[]): SceneReading {
  const blocks: ReadingBlock[] = []
  for (const beat of narration) {
    if (beat.kind === 'dialogue') {
      blocks.push({
        type: 'say',
        speakerId: beat.speaker_id ?? null,
        text: beat.text,
        quoted: false
      })
    } else if (!isAttemptRecord(beat.text ?? '')) {
      blocks.push({ type: 'prose', text: beat.text })
    }
  }
  const attempted: AttemptedSpeech[] = []
  if (!blocks.some((b) => b.type === 'say')) {
    const committed = detail.resolution?.outcome === 'success'
    for (const topic of communicateTopics(detail)) {
      if (topic.quoted && committed) {
        blocks.push({ type: 'say', speakerId: topic.speakerId, text: topic.topic, quoted: true })
      } else if (topic.quoted) {
        attempted.push({ speakerId: topic.speakerId, text: topic.topic })
      } else {
        blocks.push({
          type: 'topic',
          speakerId: topic.speakerId,
          targetId: topic.targetId,
          topic: topic.topic
        })
      }
    }
  }
  return { blocks, attempted }
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
