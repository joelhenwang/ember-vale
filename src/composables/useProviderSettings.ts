import { computed, getCurrentInstance, onUnmounted, ref } from 'vue'
import {
  addProfile,
  createProvider,
  listProfiles,
  listProviders,
  testProvider,
  updateProvider
} from '../api/worldsim'
import { isVersionConflict } from '../api/http'
import type {
  ProviderConnectionCreate,
  ProviderConnectionPatch,
  ProviderConnectionView,
  ProviderProfileCreate,
  ProviderProfileView,
  ProviderTestView
} from '../../content/clients/worldsim'
import {
  createRequest,
  emptyForm,
  formFrom,
  latestProfile,
  patchRequest,
  profileChanged,
  profileRequest,
  statusFromTest,
  validateForm,
  type ProviderForm
} from '../game/providerSettings'

export interface ProviderSettingsApi {
  listProviders(): Promise<ProviderConnectionView[]>
  listProfiles(connectionId: string): Promise<ProviderProfileView[]>
  createProvider(body: ProviderConnectionCreate): Promise<ProviderConnectionView>
  updateProvider(id: string, body: ProviderConnectionPatch): Promise<ProviderConnectionView>
  addProfile(id: string, body: ProviderProfileCreate): Promise<ProviderProfileView>
  testProvider(id: string): Promise<ProviderTestView>
}

const LIVE_API: ProviderSettingsApi = {
  listProviders: () => listProviders(),
  listProfiles: (id) => listProfiles(id),
  createProvider: (body) => createProvider(body),
  updateProvider: (id, body) => updateProvider(id, body),
  addProfile: (id, body) => addProfile(id, body),
  testProvider: (id) => testProvider(id)
}

/** Selection value for an unsaved connection. */
export const NEW_CONNECTION = 'new'

function message(err: unknown, fallback: string): string {
  if (isVersionConflict(err)) {
    return 'This connection changed elsewhere. Reload the page to see the latest values.'
  }
  return err instanceof Error && err.message ? err.message : fallback
}

/**
 * Settings page state for storyteller connections.
 *
 * The form is compared against the server baseline for dirty tracking;
 * nothing is shown as saved or reachable before the server says so.
 * Saving patches only changed connection fields and adds a profile
 * revision only when model or sampling changed.
 */
export function useProviderSettings(api: ProviderSettingsApi = LIVE_API) {
  const connections = ref<ProviderConnectionView[]>([])
  const profiles = ref<Record<string, ProviderProfileView | null>>({})
  const selected = ref<string>(NEW_CONNECTION)
  const form = ref<ProviderForm>(emptyForm())
  const baseline = ref<ProviderForm>(emptyForm())
  const loading = ref(false)
  const saving = ref(false)
  const testing = ref(false)
  const error = ref<string | null>(null)
  const lastTest = ref<ProviderTestView | null>(null)

  let alive = true
  if (getCurrentInstance()) {
    onUnmounted(() => {
      alive = false
    })
  }

  const connection = computed(() => connections.value.find((c) => c.id === selected.value) ?? null)
  const profile = computed(() => (connection.value ? profiles.value[connection.value.id] : null))
  const errors = computed(() => validateForm(form.value))
  const valid = computed(() => Object.keys(errors.value).length === 0)
  const dirty = computed(() => JSON.stringify(form.value) !== JSON.stringify(baseline.value))
  const status = computed(() =>
    testing.value ? 'testing' : statusFromTest(lastTest.value, connection.value)
  )
  /** Tests probe the saved connection, so unsaved edits block them. */
  const canTest = computed(
    () => connection.value !== null && !dirty.value && !testing.value && !saving.value
  )

  function resetForm(): void {
    const next = connection.value ? formFrom(connection.value, profile.value ?? null) : emptyForm()
    form.value = { ...next }
    baseline.value = { ...next }
  }

  async function loadProfileFor(id: string): Promise<void> {
    const rows = await api.listProfiles(id)
    profiles.value = { ...profiles.value, [id]: latestProfile(rows) }
  }

  async function load(): Promise<void> {
    loading.value = true
    error.value = null
    try {
      const rows = await api.listProviders()
      if (!alive) return
      connections.value = rows
      await Promise.all(rows.map((row) => loadProfileFor(row.id)))
      if (!alive) return
      if (selected.value === NEW_CONNECTION && rows.length > 0) selected.value = rows[0].id
      resetForm()
    } catch (err) {
      if (alive) error.value = message(err, 'Could not load connections.')
    } finally {
      if (alive) loading.value = false
    }
  }

  function select(id: string): void {
    selected.value = id
    lastTest.value = null
    error.value = null
    resetForm()
  }

  function discard(): void {
    form.value = { ...baseline.value }
    error.value = null
  }

  async function save(): Promise<boolean> {
    if (!valid.value || saving.value) return false
    saving.value = true
    error.value = null
    try {
      let saved = connection.value
      if (saved === null) {
        saved = await api.createProvider(createRequest(form.value))
        connections.value = [...connections.value, saved]
        selected.value = saved.id
        await loadProfileFor(saved.id)
      } else {
        const patch = patchRequest(form.value, saved)
        if (patch !== null) {
          const updated = await api.updateProvider(saved.id, patch)
          connections.value = connections.value.map((c) => (c.id === updated.id ? updated : c))
          saved = updated
        }
      }
      if (profileChanged(form.value, profiles.value[saved.id] ?? null)) {
        const added = await api.addProfile(saved.id, profileRequest(form.value))
        profiles.value = { ...profiles.value, [saved.id]: added }
      }
      if (!alive) return false
      resetForm()
      return true
    } catch (err) {
      if (alive) error.value = message(err, 'Could not save the connection.')
      return false
    } finally {
      if (alive) saving.value = false
    }
  }

  async function test(): Promise<void> {
    const target = connection.value
    if (!canTest.value || target === null) return
    testing.value = true
    error.value = null
    try {
      const result = await api.testProvider(target.id)
      // A late result for a connection that is no longer selected is dropped.
      if (alive && selected.value === target.id) lastTest.value = result
    } catch (err) {
      if (alive) error.value = message(err, 'The connection test could not run.')
    } finally {
      if (alive) testing.value = false
    }
  }

  return {
    connections,
    selected,
    form,
    connection,
    profile,
    errors,
    valid,
    dirty,
    status,
    canTest,
    loading,
    saving,
    testing,
    error,
    lastTest,
    load,
    select,
    discard,
    save,
    test
  }
}
