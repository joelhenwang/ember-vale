/**
 * Minimal Ember Vale API spine (E1).
 *
 * Same-origin in production; the Vite dev proxy forwards `/api` to the
 * compose API service. Full DTOs arrive with the generated contract in E2 —
 * this module only owns URL joining, the readiness envelope, and error shape
 * so the UI never shows success before server acknowledgement.
 */

export const API_BASE = '/api/v1'

export type ReadyStatus = 'ready' | 'degraded'

export interface DependencyCheck {
  name: string
  status: string
  detail?: string | null
}

export interface ReadyResponse {
  status: ReadyStatus | string
  version?: string
  environment?: string
  migration_head?: string | null
  schema_version?: string | null
  checks?: DependencyCheck[]
}

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

/** True only when the readiness envelope reports exactly `ready`. */
export function isBackendReady(body: ReadyResponse): boolean {
  return body.status === 'ready'
}

/** True when every reported dependency check passed. */
export function allChecksPass(body: ReadyResponse): boolean {
  const checks = body.checks ?? []
  return checks.length > 0 && checks.every((c) => c.status !== 'failed')
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
