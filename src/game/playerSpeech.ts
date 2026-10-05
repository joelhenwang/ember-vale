/**
 * Player speech modes for the Play composer.
 *
 * The backend treats a communicate topic wrapped in matching quotation
 * marks as identified spoken words: the narrator voices it as the
 * player character's dialogue. An unquoted topic is something the
 * character talks *about*, which the narrator paraphrases.
 */

export type SpeechMode = 'say' | 'about'

/** Backend limit for a communicate topic (schemas: max_length=256). */
export const TOPIC_MAX = 256

const QUOTE_PAIRS: Record<string, string> = { '"': '"', "'": "'", '“': '”', '‘': '’' }

/** Text with one pair of surrounding quotation marks removed, if present. */
export function stripOuterQuotes(text: string): string {
  const t = text.trim()
  const close = QUOTE_PAIRS[t[0] ?? '']
  if (t.length >= 2 && close !== undefined && t.endsWith(close)) return t.slice(1, -1).trim()
  return t
}

/**
 * Topic sent for the chosen mode. Say wraps the words in straight double
 * quotes (the backend's identified-utterance convention); About sends
 * the bare topic, so typed quotes cannot accidentally turn it into speech.
 */
export function topicFor(text: string, mode: SpeechMode): string {
  const words = stripOuterQuotes(text)
  return mode === 'say' ? `"${words}"` : words
}

/** Characters the player may type so the sent topic stays within limits. */
export function inputLimit(mode: SpeechMode): number {
  return mode === 'say' ? TOPIC_MAX - 2 : TOPIC_MAX
}
