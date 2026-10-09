import { ref, watch, type Ref } from 'vue'
import { branchPoints } from '../api/worldsim'

/**
 * The turns of a story that can be branched from (or gone back to), refreshed
 * when the story moves on (each new turn is kept as it ends; older days keep
 * only their last turn). Empty until loaded or when the read fails, so no
 * "Branch from here" or "Go back to this turn" is ever offered on a guess.
 */
export function useBranchPoints(storyId: Ref<string>, nowIndex: Ref<number>) {
  const kept = ref<ReadonlySet<number>>(new Set())
  /** The newest finished turn: branched from, never gone back to. */
  const latest = ref<number | null>(null)
  let asked = 0

  async function load(): Promise<void> {
    const ticket = ++asked
    try {
      const points = await branchPoints(storyId.value)
      if (ticket === asked) {
        kept.value = new Set(points.turns)
        latest.value = points.latest_turn ?? null
      }
    } catch {
      if (ticket === asked) {
        kept.value = new Set()
        latest.value = null
      }
    }
  }

  watch([storyId, nowIndex], () => void load(), { immediate: true })
  return { kept, latest, reload: load }
}
