import { computed, getCurrentInstance, onUnmounted, ref } from 'vue'
import { listProfiles, listProviders } from '../api/worldsim'
import type { ProviderConnectionView, ProviderProfileView } from '../../content/clients/worldsim'

export interface StorytellerPin {
  profileId: string
  profileRevision: number
}

export interface PinApi {
  listProviders(): Promise<ProviderConnectionView[]>
  listProfiles(connectionId: string): Promise<ProviderProfileView[]>
}

/**
 * Storyteller pin selection with request ownership.
 *
 * Every profile load carries the generation that started it: a response
 * that arrives after the provider changed (or after Environment default
 * was chosen) is discarded, so a late callback can never stamp another
 * provider's profile onto the current selection. Retry always reloads
 * the selected provider, even when no profile has resolved yet.
 */
export function useStorytellerPin(api: PinApi = { listProviders, listProfiles }) {
  const providers = ref<ProviderConnectionView[]>([])
  const profiles = ref<ProviderProfileView[]>([])
  const providerId = ref('')
  const profileId = ref('')
  const profileRevision = ref(1)
  const loading = ref(false)
  const error = ref<string | null>(null)

  let alive = true
  let providersLoaded = false
  let profilesReadyFor: string | null = null
  let profilesGen = 0
  if (getCurrentInstance()) {
    onUnmounted(() => {
      alive = false
    })
  }

  async function loadProviders(): Promise<void> {
    if (providersLoaded || loading.value) return
    loading.value = true
    error.value = null
    try {
      const rows = await api.listProviders()
      if (!alive) return
      providers.value = rows
      providersLoaded = true
    } catch (err) {
      if (!alive) return
      error.value = err instanceof Error ? err.message : 'could not load providers'
    } finally {
      if (alive) loading.value = false
    }
  }

  async function loadProfiles(connectionId: string): Promise<void> {
    const gen = ++profilesGen
    loading.value = true
    error.value = null
    try {
      const rows = await api.listProfiles(connectionId)
      // Stale response: another provider (or Environment default) owns
      // the selection now — discard without touching it.
      if (!alive || gen !== profilesGen || providerId.value !== connectionId) return
      profiles.value = [...rows].sort((a, b) => b.revision - a.revision)
      profilesReadyFor = connectionId
      // Default to the newest revision; the choice stays explicit and
      // editable, and never fires for a superseded provider.
      const newest = profiles.value[0]
      if (newest && !profileId.value) {
        profileId.value = newest.id
        profileRevision.value = newest.revision
      }
    } catch (err) {
      if (!alive || gen !== profilesGen || providerId.value !== connectionId) return
      profiles.value = []
      profilesReadyFor = null
      error.value = err instanceof Error ? err.message : 'could not load profiles'
    } finally {
      if (alive && gen === profilesGen) loading.value = false
    }
  }

  /** Load lists for the current selection; resolves the owning
   * connection for pins restored from a saved draft. */
  async function ensure(): Promise<void> {
    await loadProviders()
    if (!alive) return
    if (!providerId.value && profileId.value) {
      const gen = profilesGen
      for (const connection of providers.value) {
        if (!alive || gen !== profilesGen) return
        const rows = await api.listProfiles(connection.id).catch(() => [])
        if (!alive || gen !== profilesGen) return
        if (rows.some((p) => p.id === profileId.value)) {
          providerId.value = connection.id
          break
        }
      }
    }
    if (providerId.value && profilesReadyFor !== providerId.value) {
      await loadProfiles(providerId.value)
    }
  }

  function selectProvider(id: string): void {
    providerId.value = id
    profileId.value = ''
    profiles.value = []
    profilesReadyFor = null
    if (id) void loadProfiles(id)
  }

  function selectProfile(id: string): void {
    const found = profiles.value.find((p) => p.id === id)
    if (!found) return
    profileId.value = found.id
    profileRevision.value = found.revision
  }

  /** Retry after a failure: reload providers, then the selected
   * provider's profiles even when none has resolved yet. */
  async function retry(): Promise<void> {
    providersLoaded = false
    profilesReadyFor = null
    await ensure()
  }

  /** Restore a pin persisted by an earlier save. */
  function restorePin(id: string, revision: number): void {
    providerId.value = ''
    profileId.value = id
    profileRevision.value = revision
    profiles.value = []
    profilesReadyFor = null
  }

  function reset(): void {
    providerId.value = ''
    profileId.value = ''
    profileRevision.value = 1
    profiles.value = []
    profilesReadyFor = null
    error.value = null
  }

  const pin = computed<StorytellerPin | undefined>(() =>
    profileId.value
      ? { profileId: profileId.value, profileRevision: profileRevision.value }
      : undefined
  )

  const summary = computed(() => {
    // Only a clean default reads as default: anything selected or
    // restored but unresolved says so explicitly, on the AI step and
    // on Review alike.
    if (!providerId.value && !profileId.value) return 'Environment default'
    const connection = providerId.value
      ? providers.value.find((c) => c.id === providerId.value)
      : undefined
    const where = connection?.name ?? 'unknown provider'
    if (!profileId.value) {
      return `${where} · profiles unavailable — retry or choose Environment default`
    }
    const profile = profiles.value.find((p) => p.id === profileId.value)
    const model = profile?.model_id ?? 'unknown model'
    const rev = profile?.revision ?? profileRevision.value
    return `${where} · ${model} · rev ${rev}`
  })

  return {
    providers,
    profiles,
    providerId,
    profileId,
    summary,
    pin,
    loading,
    error,
    ensure,
    selectProvider,
    selectProfile,
    retry,
    restorePin,
    reset
  }
}
