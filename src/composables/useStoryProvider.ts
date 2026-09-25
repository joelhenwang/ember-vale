import { computed, ref, unref, type Ref } from 'vue'
import { getStoryProvider } from '../api/worldsim'
import type { StoryProviderView } from '../../content/clients/worldsim'

export type ProviderBannerTone = 'info' | 'error'

export interface ProviderBanner {
  tone: ProviderBannerTone
  text: string
}

/**
 * Room banner wording for the story-effective provider.
 *
 * Names exactly what beats run: the resolved pin (model plus revision) or
 * the environment default stated as such. "Deterministic stand-ins" is
 * reserved for an actually fake effective adapter — a live-provider
 * failure never re-labels the whole story. A null view means the status
 * is still loading (no banner); a failed load is an honest unknown.
 */
export function describeStoryProvider(
  view: StoryProviderView | null,
  loadFailed: boolean
): ProviderBanner | null {
  if (view === null) {
    return loadFailed
      ? { tone: 'info', text: 'Storyteller status unknown — beats will say what they used.' }
      : null
  }
  if (view.pin_state === 'broken') {
    const why = view.pin_error ?? 'the pinned profile could not be resolved'
    return {
      tone: 'error',
      text: `Storyteller unavailable — ${why}. Beats cannot run until the pin is fixed.`
    }
  }
  const fake = view.effective_adapter === 'fake'
  const model = view.effective_model_id ?? 'development model'
  const tail = fake ? 'deterministic stand-ins, not live provider prose.' : 'live provider prose.'
  if (view.effective_source === 'pin' && view.pin) {
    const rev = view.effective_revision ?? view.pin.revision
    return { tone: 'info', text: `Storyteller ${model} · rev ${rev} (pinned) — ${tail}` }
  }
  return { tone: 'info', text: `Storyteller environment default (${model}) — ${tail}` }
}

/**
 * Environment wording for surfaces without a story (story creation).
 * Only an actually fake profile claims deterministic stand-ins; null keeps
 * the caller's unknown fallback.
 */
export function describeEnvironment(modelProfile: string | null): { text: string } | null {
  if (!modelProfile) return null
  if (modelProfile === 'active:fake') {
    return {
      text: `Development model active (${modelProfile}) — beats are deterministic stand-ins, not live provider prose.`
    }
  }
  return {
    text: `Live model active (${modelProfile}) — beats are live provider prose.`
  }
}

/**
 * Beat-scoped fallback note. Narration fallback belongs to the beat whose
 * scenes report it — never to the story-level provider banner.
 */
export function beatFallbackNotice(
  index: number,
  scenes: Array<{ narration?: unknown }> | undefined
): string | null {
  if (!scenes?.some((scene) => scene?.narration === 'fallback')) return null
  return `Beat ${index} narration fell back to a deterministic stand-in.`
}

export function useStoryProvider(
  storyId: string | Ref<string>,
  client: {
    readStoryProvider(id: string): Promise<StoryProviderView>
  } = { readStoryProvider: (id: string) => getStoryProvider(id) }
) {
  const view = ref<StoryProviderView | null>(null)
  const loading = ref(false)
  const failed = ref(false)
  let cycle = 0

  async function load(): Promise<void> {
    const seen = ++cycle
    loading.value = true
    failed.value = false
    try {
      const next = await client.readStoryProvider(unref(storyId))
      if (seen !== cycle) return
      view.value = next
    } catch {
      if (seen !== cycle) return
      failed.value = true
    } finally {
      if (seen === cycle) loading.value = false
    }
  }

  const banner = computed(() => describeStoryProvider(view.value, failed.value))

  return { view, banner, loading, failed, load }
}
