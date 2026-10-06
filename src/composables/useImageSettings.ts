import { computed, getCurrentInstance, onUnmounted, ref } from 'vue'
import {
  getImageService,
  getPreferences,
  previewImages,
  savePreferences,
  type ImagePreviewItem,
  type ImageServiceView
} from '../api/worldsim'
import { isVersionConflict } from '../api/http'
import type { PreferencesPatchRequest, PreferencesView } from '../../content/clients/worldsim'
import {
  DEFAULT_IMAGE_PREFS,
  estimateSeconds,
  imagePrefsFrom,
  switchesCheckpoint,
  validateImagePrefs,
  type ImagePrefs,
  type ImageRatio
} from '../game/imageSettings'

export interface ImageSettingsApi {
  getPreferences(): Promise<PreferencesView>
  savePreferences(body: PreferencesPatchRequest): Promise<PreferencesView>
  getImageService(): Promise<ImageServiceView>
  previewImages(body: {
    prompt: string
    ratio: string
    count: number
    images?: Record<string, unknown>
  }): Promise<{ images: ImagePreviewItem[] }>
}

const LIVE_API: ImageSettingsApi = {
  getPreferences: () => getPreferences(),
  savePreferences: (body) => savePreferences(body),
  getImageService: () => getImageService(),
  previewImages: (body) => previewImages(body)
}

export const PREVIEW_PROMPT =
  'Portrait of a young traveller with a lantern at the edge of a misty village, warm evening light'

function message(err: unknown, fallback: string): string {
  if (isVersionConflict(err)) {
    return 'These settings changed elsewhere. Reload the page to see the latest values.'
  }
  return err instanceof Error && err.message ? err.message : fallback
}

/**
 * Settings page state for image generation: the saved choices (operator
 * preferences, section `images`), the image service's live status and
 * catalog, and a preview that draws with unsaved choices.
 */
export function useImageSettings(api: ImageSettingsApi = LIVE_API) {
  const form = ref<ImagePrefs>({ ...DEFAULT_IMAGE_PREFS })
  const baseline = ref<ImagePrefs>({ ...DEFAULT_IMAGE_PREFS })
  const version = ref(0)
  const service = ref<ImageServiceView | null>(null)
  const loading = ref(false)
  const checking = ref(false)
  const saving = ref(false)
  const error = ref<string | null>(null)

  const previewPrompt = ref(PREVIEW_PROMPT)
  const previewRatio = ref<ImageRatio>('1:1')
  const previewCount = ref(1)
  const previewing = ref(false)
  const previewError = ref<string | null>(null)
  const previews = ref<ImagePreviewItem[]>([])

  let alive = true
  if (getCurrentInstance()) {
    onUnmounted(() => {
      alive = false
    })
  }

  const errors = computed(() => validateImagePrefs(form.value))
  const valid = computed(() => Object.keys(errors.value).length === 0)
  const dirty = computed(() => JSON.stringify(form.value) !== JSON.stringify(baseline.value))
  const seconds = computed(() => estimateSeconds(form.value))
  const switching = computed(() => switchesCheckpoint(form.value, service.value?.checkpoint))
  /** live: drawing works; off: switched off here; missing / down: the service. */
  const status = computed<'checking' | 'live' | 'off' | 'missing' | 'down' | 'loading'>(() => {
    const s = service.value
    if (checking.value && s === null) return 'checking'
    if (s === null || !s.configured) return 'missing'
    if (!s.reachable) return 'down'
    if (!s.loaded) return 'loading'
    return baseline.value.enabled ? 'live' : 'off'
  })
  const canPreview = computed(
    () =>
      service.value?.reachable === true &&
      valid.value &&
      !previewing.value &&
      previewPrompt.value.trim().length > 0
  )

  async function refreshService(): Promise<void> {
    checking.value = true
    try {
      const next = await api.getImageService()
      if (alive) service.value = next
    } catch (err) {
      if (alive) error.value = message(err, 'Could not reach the server.')
    } finally {
      if (alive) checking.value = false
    }
  }

  async function load(): Promise<void> {
    loading.value = true
    error.value = null
    try {
      const prefs = await api.getPreferences()
      if (!alive) return
      version.value = prefs.version
      baseline.value = imagePrefsFrom(prefs.images)
      form.value = { ...baseline.value }
    } catch (err) {
      if (alive) error.value = message(err, 'Could not load image settings.')
    } finally {
      if (alive) loading.value = false
    }
    await refreshService()
  }

  function discard(): void {
    form.value = { ...baseline.value }
    error.value = null
  }

  function restoreDefaults(): void {
    form.value = { ...DEFAULT_IMAGE_PREFS, enabled: form.value.enabled }
  }

  async function save(): Promise<boolean> {
    if (!valid.value || saving.value) return false
    saving.value = true
    error.value = null
    try {
      const saved = await api.savePreferences({
        images: { ...form.value },
        expected_version: version.value
      })
      if (!alive) return false
      version.value = saved.version
      baseline.value = imagePrefsFrom(saved.images)
      form.value = { ...baseline.value }
      return true
    } catch (err) {
      if (alive) error.value = message(err, 'Could not save image settings.')
      return false
    } finally {
      if (alive) saving.value = false
    }
  }

  async function preview(): Promise<void> {
    if (!canPreview.value) return
    previewing.value = true
    previewError.value = null
    try {
      const result = await api.previewImages({
        prompt: previewPrompt.value.trim(),
        ratio: previewRatio.value,
        count: previewCount.value,
        images: { ...form.value }
      })
      if (alive) previews.value = result.images
    } catch (err) {
      if (alive) previewError.value = message(err, 'The preview could not be drawn.')
    } finally {
      if (alive) previewing.value = false
    }
    // A preview may have switched the checkpoint: show what is loaded now.
    if (alive) await refreshService()
  }

  return {
    form,
    service,
    loading,
    checking,
    saving,
    error,
    errors,
    valid,
    dirty,
    seconds,
    switching,
    status,
    previewPrompt,
    previewRatio,
    previewCount,
    previewing,
    previewError,
    previews,
    canPreview,
    load,
    refreshService,
    discard,
    restoreDefaults,
    save,
    preview
  }
}
