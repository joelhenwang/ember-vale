/**
 * Minimal Ember Vale API spine (E1, corrected per review).
 *
 * Shape mirrors the authoritative backend DTOs in
 * `backend/src/worldsim/interfaces/http/schemas.py` (status
 * `ready|degraded`, integer `schema_version`, check statuses
 * `ok|degraded|failed`) until the generated contract replaces this module
 * in E2. The UI must never show success before server acknowledgement.
 *
 * Readiness vocabulary (backend `readiness.py`):
 * - top-level `ready` means every check ok; `degraded` means at least one
 *   check is degraded/failed — see `isBackendReady`.
 * - the `seed` check reports `degraded` on an empty installation
 *   (`worlds:0`). That is ADVISORY: onboarding, preset selection and
 *   first-story creation must work on an empty database. Never seed a fake
 *   played world to turn readiness green.
 * - readiness says nothing about live text/image generation. The
 *   `model_profile` check detail (e.g. `active:fake`) names the active
 *   provider profile; report it separately via `modelProfileDetail`.
 */

export const API_BASE = '/api/v1'

/** Top-level readiness, exactly the backend Literal. */
export type ReadyStatus = 'ready' | 'degraded'

/** Per-check status, exactly the backend Literal. */
export type CheckStatus = 'ok' | 'degraded' | 'failed'

export interface DependencyCheck {
  name: string
  status: CheckStatus
  detail?: string | null
}

export interface ReadyResponse {
  status: ReadyStatus
  version: string
  environment: string
  migration_head: string | null
  schema_version: number
  checks: DependencyCheck[]
}

/** Stable error shape the UI renders; never synthesize success. */
export interface ApiError {
  code: string
  message: string
  retryable: boolean
  fields?: Record<string, string[]>
}

/** Join API_BASE + path without double slashes. */
export function buildApiUrl(path: string): string {
  const clean = path.startsWith('/') ? path : `/${path}`
  return `${API_BASE}${clean}`
}

/** True only when the envelope reports exactly `ready`. */
export function isBackendReady(body: ReadyResponse): boolean {
  return body.status === 'ready'
}

/**
 * True only when at least one check is reported and EVERY check has the
 * positive `ok` status. `degraded`, `failed` and any other value fail.
 */
export function allChecksPass(body: ReadyResponse): boolean {
  const checks = body.checks ?? []
  return checks.length > 0 && checks.every((c) => c.status === 'ok')
}

/** Find one dependency check by name. */
export function findCheck(body: ReadyResponse, name: string): DependencyCheck | undefined {
  return (body.checks ?? []).find((c) => c.name === name)
}

/**
 * Seed/world-count state for onboarding decisions. Returns the raw check
 * status, or `missing` when the backend omits it. A `degraded` seed (empty
 * installation) must NOT block preset selection or first-story creation.
 */
export function seedStatus(body: ReadyResponse): CheckStatus | 'missing' {
  return findCheck(body, 'seed')?.status ?? 'missing'
}

/**
 * Active provider profile detail (e.g. `active:fake`), or null when absent.
 * A development/fake profile must be visibly distinguished from a live
 * provider; health readiness alone never proves generation works.
 */
export function modelProfileDetail(body: ReadyResponse): string | null {
  return findCheck(body, 'model_profile')?.detail ?? null
}

export async function fetchReady(
  fetchImpl: typeof fetch = fetch,
  init?: RequestInit
): Promise<ReadyResponse> {
  const res = await fetchImpl(buildApiUrl('/health/ready'), init)
  if (!res.ok) {
    throw new Error(`ready probe failed: HTTP ${res.status}`)
  }
  return (await res.json()) as ReadyResponse
}
