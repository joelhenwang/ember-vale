import type {
  ProviderConnectionCreate,
  ProviderConnectionPatch,
  ProviderConnectionView,
  ProviderProfileCreate,
  ProviderProfileView,
  ProviderTestView
} from '../../content/clients/worldsim'

/**
 * Storyteller connections as the backend models them (Settings page).
 *
 * A connection names an adapter, an endpoint and the NAME of a server-side
 * environment variable holding the key (the key never reaches the client).
 * Model and sampling live in append-only profile revisions: saving changed
 * values adds revision N+1, and stories keep the revision they pinned.
 * Connection tests run against the SAVED connection, never unsaved input.
 *
 * Pure helpers only; the composable owns requests and timing.
 */

export type Adapter = 'openrouter' | 'venice' | 'fake'

export const ADAPTER_LABELS: Record<Adapter, string> = {
  openrouter: 'OpenRouter',
  venice: 'Venice',
  fake: 'Offline stand-in (no model calls)'
}

export const DEFAULT_ENDPOINT = 'https://openrouter.ai/api/v1'
export const DEFAULT_CREDENTIAL_ENV = 'WORLDSIM_PROVIDER__OPENROUTER_API_KEY'
/** Where each live adapter's endpoint and key variable start. */
export const ADAPTER_DEFAULTS: Record<Adapter, { endpoint: string; credentialEnv: string }> = {
  openrouter: { endpoint: DEFAULT_ENDPOINT, credentialEnv: DEFAULT_CREDENTIAL_ENV },
  venice: {
    endpoint: 'https://api.venice.ai/api/v1',
    credentialEnv: 'WORLDSIM_PROVIDER__VENICE_API_KEY'
  },
  fake: { endpoint: DEFAULT_ENDPOINT, credentialEnv: '' }
}
export const DEFAULT_MODEL: Record<Adapter, string> = {
  openrouter: 'openrouter/auto',
  venice: 'venice-uncensored-1-2',
  fake: 'fake-echo'
}

/** Form state; numbers stay strings so half-typed input is representable. */
export interface ProviderForm {
  name: string
  adapter: Adapter
  endpoint: string
  credentialEnv: string
  allowLocal: boolean
  modelId: string
  temperature: string
  topP: string
  topK: string
  maxTokens: string
}

export type FieldErrors = Partial<Record<keyof ProviderForm, string>>

export type ConnStatus = 'untested' | 'testing' | 'reachable' | 'unreachable' | 'unavailable'

export function emptyForm(): ProviderForm {
  return {
    name: 'OpenRouter',
    adapter: 'openrouter',
    endpoint: DEFAULT_ENDPOINT,
    credentialEnv: DEFAULT_CREDENTIAL_ENV,
    allowLocal: false,
    modelId: DEFAULT_MODEL.openrouter,
    temperature: '',
    topP: '',
    topK: '',
    maxTokens: '512'
  }
}

export function asAdapter(raw: string): Adapter {
  return raw === 'fake' || raw === 'venice' ? raw : 'openrouter'
}

/** The generated client types float fields as `unknown`; read numbers only. */
function numText(value: unknown): string {
  return typeof value === 'number' && Number.isFinite(value) ? String(value) : ''
}

function numOrNull(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

/** Form for a saved connection and its newest profile revision. */
export function formFrom(
  connection: ProviderConnectionView,
  profile: ProviderProfileView | null
): ProviderForm {
  const adapter = asAdapter(connection.adapter)
  return {
    name: connection.name,
    adapter,
    endpoint: connection.endpoint,
    credentialEnv: connection.credential_env ?? '',
    allowLocal: connection.allow_local_endpoint ?? false,
    modelId: profile?.model_id ?? DEFAULT_MODEL[adapter],
    temperature: numText(profile?.temperature),
    topP: numText(profile?.top_p),
    topK: numText(profile?.top_k),
    maxTokens: numText(profile?.max_tokens ?? 512)
  }
}

/** Newest revision first; null when the connection has none. */
export function latestProfile(
  profiles: readonly ProviderProfileView[]
): ProviderProfileView | null {
  let best: ProviderProfileView | null = null
  for (const p of profiles) if (best === null || p.revision > best.revision) best = p
  return best
}

function optionalNumber(
  raw: string,
  field: keyof ProviderForm,
  errors: FieldErrors,
  min: number,
  max: number,
  integer: boolean
): number | null {
  const text = raw.trim()
  if (text === '') return null
  const value = Number(text)
  if (!Number.isFinite(value) || (integer && !Number.isInteger(value))) {
    errors[field] = integer ? 'Whole number' : 'Number'
    return null
  }
  if (value < min || value > max) {
    errors[field] = `${min}–${max}`
    return null
  }
  return value
}

/** Validation mirroring the backend schema limits (schemas.py). */
export function validateForm(form: ProviderForm): FieldErrors {
  const errors: FieldErrors = {}
  const name = form.name.trim()
  if (name.length < 1 || name.length > 128) errors.name = 'Name is required (up to 128)'
  const endpoint = form.endpoint.trim()
  if (!/^https?:\/\/\S+$/.test(endpoint)) errors.endpoint = 'Must start with http:// or https://'
  else if (endpoint.length > 512) errors.endpoint = 'Up to 512 characters'
  if (form.credentialEnv.length > 128) errors.credentialEnv = 'Up to 128 characters'
  else if (form.credentialEnv && !/^[A-Za-z_][A-Za-z0-9_]*$/.test(form.credentialEnv.trim()))
    errors.credentialEnv = 'An environment variable name, e.g. MY_KEY'
  const model = form.modelId.trim()
  if (model.length < 1 || model.length > 128) errors.modelId = 'Model is required'
  optionalNumber(form.temperature, 'temperature', errors, 0, 2, false)
  optionalNumber(form.topP, 'topP', errors, 0, 1, false)
  optionalNumber(form.topK, 'topK', errors, 1, 100, true)
  if (form.maxTokens.trim() === '') errors.maxTokens = 'Required'
  else optionalNumber(form.maxTokens, 'maxTokens', errors, 1, 4096, true)
  return errors
}

/** Profile request for the form; call only when validateForm is clean. */
export function profileRequest(form: ProviderForm): ProviderProfileCreate {
  const errors: FieldErrors = {}
  return {
    model_id: form.modelId.trim(),
    temperature: optionalNumber(form.temperature, 'temperature', errors, 0, 2, false),
    top_p: optionalNumber(form.topP, 'topP', errors, 0, 1, false),
    top_k: optionalNumber(form.topK, 'topK', errors, 1, 100, true),
    max_tokens: optionalNumber(form.maxTokens, 'maxTokens', errors, 1, 4096, true) ?? 512
  }
}

/** True when saving would add a new profile revision. */
export function profileChanged(form: ProviderForm, profile: ProviderProfileView | null): boolean {
  if (profile === null) return true
  const next = profileRequest(form)
  return (
    next.model_id !== profile.model_id ||
    numOrNull(next.temperature) !== numOrNull(profile.temperature) ||
    numOrNull(next.top_p) !== numOrNull(profile.top_p) ||
    numOrNull(next.top_k) !== numOrNull(profile.top_k) ||
    next.max_tokens !== profile.max_tokens
  )
}

export function createRequest(form: ProviderForm): ProviderConnectionCreate {
  return {
    adapter: form.adapter,
    name: form.name.trim(),
    endpoint: form.endpoint.trim(),
    credential_env: form.credentialEnv.trim() || null,
    allow_local_endpoint: form.allowLocal
  }
}

/** Patch with only the changed connection fields, or null when unchanged. */
export function patchRequest(
  form: ProviderForm,
  connection: ProviderConnectionView
): ProviderConnectionPatch | null {
  const patch: ProviderConnectionPatch = { expected_version: connection.config_version }
  let changed = false
  if (form.name.trim() !== connection.name) {
    patch.name = form.name.trim()
    changed = true
  }
  if (form.endpoint.trim() !== connection.endpoint) {
    patch.endpoint = form.endpoint.trim()
    changed = true
  }
  if (form.credentialEnv.trim() !== (connection.credential_env ?? '')) {
    patch.credential_env = form.credentialEnv.trim()
    changed = true
  }
  if (form.allowLocal !== (connection.allow_local_endpoint ?? false)) {
    patch.allow_local_endpoint = form.allowLocal
    changed = true
  }
  return changed ? patch : null
}

/**
 * Card status from the last test. A test of an older configuration (the
 * connection was edited since) is reported as untested, never as reachable.
 */
export function statusFromTest(
  result: ProviderTestView | null,
  connection: ProviderConnectionView | null
): ConnStatus {
  if (result === null || connection === null) return 'untested'
  if (result.tested_config_revision !== connection.config_version) return 'untested'
  return result.reachable ? 'reachable' : 'unreachable'
}
