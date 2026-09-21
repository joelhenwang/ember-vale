/**
 * Exact pinned preset revisions for the New Story wizard.
 *
 * The shelf loads latest revisions only, but a draft can pin an older
 * world/character revision. This composable fetches the exact pinned
 * revision so displayed places/names are the ones the draft submits.
 * Requests are generation-guarded and results keyed by preset ID *and*
 * revision, so a slow response for a previous selection can never supply
 * another preset's places. Failures surface as explicit errors — latest
 * content is never substituted silently under an old revision.
 */

import { ref } from 'vue'
import { getPreset } from '../api/worldsim'

export interface PinnedWorld {
  id: string
  revision: number
  name: string
  places: { key: string; name: string }[]
}

export interface PinnedCharacter {
  presetId: string
  revision: number
  name: string
}

interface WorldRevisionBody {
  locations?: { key: string; name: string }[]
  description?: string
}

export function usePinnedPresets() {
  const world = ref<PinnedWorld | null>(null)
  const worldError = ref<string | null>(null)
  const worldLoading = ref(false)
  const characters = ref(new Map<string, PinnedCharacter>())
  let worldCycle = 0

  const keyOf = (id: string, revision: number): string => `${id}@${revision}`

  /**
   * Load the exact pinned world revision. Assigns only if the same preset
   * ID and revision are still selected when the response arrives.
   */
  async function loadWorld(id: string, revision: number, isCurrent?: () => boolean): Promise<void> {
    worldCycle += 1
    const seen = worldCycle
    // Frozen request identity: the response is labeled with these values,
    // never with whatever is selected when it arrives.
    const wantId = id
    const wantRev = revision
    worldLoading.value = true
    worldError.value = null
    try {
      const detail = await getPreset(wantId, wantRev)
      if (seen !== worldCycle) return
      if (isCurrent && !isCurrent()) return
      const rev = (detail.revision ?? {}) as unknown as WorldRevisionBody
      const places = (rev.locations ?? []).map((p) => ({ key: p.key, name: p.name }))
      world.value = { id: wantId, revision: wantRev, name: detail.name, places }
    } catch (err) {
      if (seen !== worldCycle) return
      if (isCurrent && !isCurrent()) return
      world.value = null
      worldError.value =
        err instanceof Error
          ? `Could not load the pinned world revision (${wantRev}): ${err.message}`
          : `Could not load the pinned world revision (${wantRev}).`
    } finally {
      if (seen === worldCycle) worldLoading.value = false
    }
  }

  function clearWorld(): void {
    worldCycle += 1
    world.value = null
    worldError.value = null
    worldLoading.value = false
  }

  /**
   * Resolve the exact pinned character revision for display. Latest
   * revisions stay uncached-eligible for browsing; only older pinned
   * revisions are fetched, keyed by preset ID and revision.
   */
  async function loadCharacter(
    presetId: string,
    revision: number,
    latestRevision: number
  ): Promise<void> {
    const key = keyOf(presetId, revision)
    if (characters.value.has(key) || revision === latestRevision) return
    try {
      const detail = await getPreset(presetId, revision)
      characters.value.set(key, { presetId, revision, name: detail.name })
    } catch {
      /* display falls back to the draft-stored name */
    }
  }

  function characterName(presetId: string, revision: number, fallback: string): string {
    return characters.value.get(keyOf(presetId, revision))?.name ?? fallback
  }

  return {
    world,
    worldError,
    worldLoading,
    characters,
    loadWorld,
    clearWorld,
    loadCharacter,
    characterName
  }
}
