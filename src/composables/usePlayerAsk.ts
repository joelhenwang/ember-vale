import type { Ref } from 'vue'

export type PlayerIntents = Record<string, Record<string, unknown>>

/**
 * One spoken attempt with submitter-side confirmation.
 *
 * The live text is snapshotted at submit; the composer clears only when
 * the beat confirms the submission AND the live text still matches the
 * snapshot. A conflict, an unresolved duplicate, or newer edits typed
 * mid-flight all keep the text: none of them proves this question
 * committed.
 */
export function usePlayerAsk(
  advance: (intents: PlayerIntents) => Promise<boolean>,
  text: Ref<string>
) {
  return async function submit(build: (topic: string) => PlayerIntents): Promise<boolean> {
    const snapshot = text.value.trim()
    if (!snapshot) return false
    const confirmed = await advance(build(snapshot))
    if (confirmed && text.value.trim() === snapshot) text.value = ''
    return confirmed
  }
}
