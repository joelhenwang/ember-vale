import { reactive } from 'vue'
import { resolveImage, setGeneratedImage } from './images'

/**
 * Settings store — defaults applied to NEW stories (existing stories keep
 * their own configuration, hence the page subtitle).
 *
 * Like the studio drafts, save state is a JSON snapshot: edits make the
 * page dirty, "Save settings" re-snapshots, "Discard" restores it.
 * Connection "tests" are DEMO fakes — see applyConnectionTest for the pure
 * transition that a production client would perform against the endpoint.
 */

export type ConnStatus = 'untested' | 'testing' | 'reachable' | 'unreachable'
export type Capability = 'unknown' | 'supported' | 'unsupported'

export interface ConnectionState {
  provider: string
  model: string
  endpoint: string
  /** Name of a server-side secret — the real key never reaches the client. */
  cred: string
  status: ConnStatus
  lastChecked: string
}

export interface ImageConnectionState extends ConnectionState {
  envImages: Capability
  charRefs: Capability
}

export const STORY_PROVIDERS = [
  'OpenAI-compatible',
  'Anthropic',
  'Google Gemini',
  'Local (llama.cpp)',
  'Custom endpoint'
] as const

export const IMAGE_PROVIDERS = [
  'OpenAI Images',
  'Stability AI',
  'Flux (BFL)',
  'Local ComfyUI'
] as const

/** DEMO model catalogues; production would query /models from the endpoint. */
export const STORY_MODELS: Record<string, string[]> = {
  'OpenAI-compatible': ['gpt-4o', 'gpt-4o-mini', 'o4-mini', 'llama-3.3-70b (served)'],
  Anthropic: ['claude-sonnet-4-5', 'claude-haiku-4-5'],
  'Google Gemini': ['gemini-2.5-pro', 'gemini-2.5-flash'],
  'Local (llama.cpp)': ['qwen2.5-32b-instruct', 'mistral-small-24b'],
  'Custom endpoint': ['(discovered from endpoint)']
}

export const IMAGE_MODELS: Record<string, string[]> = {
  'OpenAI Images': ['gpt-image-1'],
  'Stability AI': ['sd3.5-large', 'sd3.5-medium'],
  'Flux (BFL)': ['flux-1.1-pro', 'flux-dev'],
  'Local ComfyUI': ['sdxl-ember-style (lora)']
}

export const settings = reactive<{
  story: ConnectionState
  image: ImageConnectionState
}>({
  story: {
    provider: 'OpenAI-compatible',
    model: '',
    endpoint: 'http://localhost:8000/v1',
    cred: 'STORY_API_KEY',
    status: 'reachable',
    lastChecked: 'just now'
  },
  image: {
    provider: '',
    model: '',
    endpoint: '',
    cred: 'IMAGE_API_KEY',
    status: 'untested',
    lastChecked: '',
    envImages: 'unknown',
    charRefs: 'unknown'
  }
})

/* ————— save / dirty (snapshot pattern shared with the studios) ————— */

// DEMO: the baseline intentionally lags one edit behind so the page opens in
// the mockup's "Unsaved changes" state. Production starts clean.
let snap = JSON.stringify({ ...settings, story: { ...settings.story, endpoint: '' } })

export function isSettingsDirty(): boolean {
  return JSON.stringify(settings) !== snap
}
export function saveSettings(): void {
  snap = JSON.stringify(settings)
}
export function discardSettings(): void {
  const restored = JSON.parse(snap) as typeof settings
  Object.assign(settings.story, restored.story)
  Object.assign(settings.image, restored.image)
}

/* ————— connection tests ————— */

/**
 * Pure transition the (future) real client performs after probing an
 * endpoint. Story-gen reaches "reachable" whenever an endpoint is set;
 * the image provider additionally reports its capabilities, which unlocks
 * the test-image button.
 */
export function applyConnectionTest(which: 'story' | 'image'): void {
  const c = settings[which]
  c.status = c.endpoint.trim() ? 'reachable' : 'unreachable'
  c.lastChecked = 'just now'
  if (which === 'image' && c.status === 'reachable') {
    const img = c as ImageConnectionState
    img.envImages = 'supported'
    img.charRefs = 'supported'
  }
}

export function providerModels(which: 'story' | 'image'): string[] {
  const c = settings[which]
  if (!c.provider) return []
  return (which === 'story' ? STORY_MODELS : IMAGE_MODELS)[c.provider] ?? []
}

export function setProvider(which: 'story' | 'image', provider: string): void {
  const c = settings[which]
  c.provider = provider
  const models = (which === 'story' ? STORY_MODELS : IMAGE_MODELS)[provider] ?? []
  if (c.model && !models.includes(c.model)) c.model = ''
}

/** DEMO: renders through the same registry the whole app reads from. */
export function generateTestImage(): void {
  const stamp = Date.now()
  setGeneratedImage('world.map', `${resolveImage('world.map')}?t=${stamp}`)
  settings.image.lastChecked = 'just now'
}
