import { ref, watch, type Ref } from 'vue'
import { branchPoints } from '../api/worldsim'

/**
 * The turns of a story that can be branched from, refreshed when the story
 * moves on (each new turn is kept as it ends). Empty until loaded or when
 * the read fails, so no "Branch from here" is ever offered on a guess.
 */
export function useBranchPoints(storyId: Ref<string>, nowIndex: Ref<number>) {
  const kept = ref<ReadonlySet<number>>(new Set())
  let asked = 0

  async function load(): Promise<void> {
    const ticket = ++asked
    try {
      const points = await branchPoints(storyId.value)
      if (ticket === asked) kept.value = new Set(points.turns)
    } catch {
      if (ticket === asked) kept.value = new Set()
    }
  }

  watch([storyId, nowIndex], () => void load(), { immediate: true })
  return { kept, reload: load }
}
