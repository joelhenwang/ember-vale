/**
 * Central request handling for the Ember Vale API spine (C1).
 *
 * - Same-origin `/api/v1` in production; the Vite dev proxy forwards to the
 *   compose API and injects the loopback operator key server-side, so this
 *   module never holds credentials and never puts them in URLs.
 * - Every request carries an explicit role header; player requests also name
 *   their character. The backend grant governs; headers select the subject.
 * - Errors use the backend stable envelope `{error: {code, message}}`.
 *   Nothing here reports success before the server acknowledges it:
 *   non-2xx always throws ApiError, and callers distinguish retryable /
 *   version-conflict / cancelled explicitly. Only an actual outer-signal
 *   abort is reported as cancelled; timeouts and transport failures keep
 *   their own retryable codes so outages are never silently ignored.
 */

import { API_BASE } from './client'

export type Role = 'watcher' | 'player' | 'director' | 'deity'

export interface EnvelopeError {
  code: string
  message: string
}

export class ApiError extends Error {
  readonly code: string
  readonly status: number
  readonly retryable: boolean
  readonly cancelled: boolean

  constructor(code: string, message: string, status: number, retryable: boolean) {
    super(message)
    this.name = 'ApiError'
    this.code = code
    this.status = status
    this.retryable = retryable
    this.cancelled = code === 'REQUEST_ABORTED'
  }
}

const RETRYABLE_STATUS = new Set([408, 425, 429, 502, 503, 504])

function statusToRetryable(status: number): boolean {
  return RETRYABLE_STATUS.has(status)
}

export function isVersionConflict(err: unknown): boolean {
  return err instanceof ApiError && err.code === 'VERSION_CONFLICT'
}

export function isIdempotencyConflict(err: unknown): boolean {
  return err instanceof ApiError && err.code === 'IDEMPOTENCY_CONFLICT'
}

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'DELETE'
  body?: unknown
  /** Preserved across retries of the same user operation; fresh per operation. */
  idempotencyKey?: string
  role?: Role
  /** Required with role 'player': the controlled character id. */
  characterId?: string
  /** Per-story cancellation: late responses after navigation are ignored. */
  signal?: AbortSignal
  timeoutMs?: number
  fetchImpl?: typeof fetch
}

function readEnvelope(raw: unknown): EnvelopeError | null {
  if (typeof raw !== 'object' || raw === null) return null
  const error = (raw as { error?: unknown }).error
  if (typeof error !== 'object' || error === null) return null
  const { code, message } = error as { code?: unknown; message?: unknown }
  if (typeof code !== 'string' || typeof message !== 'string') return null
  return { code, message }
}

export async function apiFetch<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const {
    method = 'GET',
    body,
    idempotencyKey,
    role,
    characterId,
    signal,
    timeoutMs = 30000,
    fetchImpl = fetch
  } = options
  const controller = new AbortController()
  let timedOut = false
  const timer = setTimeout(() => {
    timedOut = true
    controller.abort(new Error('REQUEST_TIMEOUT'))
  }, timeoutMs)
  let outerAborted = false
  const onOuterAbort = (): void => {
    outerAborted = true
    controller.abort(signal?.reason ?? new Error('REQUEST_ABORTED'))
  }
  if (signal) {
    if (signal.aborted) onOuterAbort()
    else signal.addEventListener('abort', onOuterAbort, { once: true })
  }
  try {
    const headers: Record<string, string> = { Accept: 'application/json' }
    if (body !== undefined) headers['Content-Type'] = 'application/json'
    if (idempotencyKey) headers['Idempotency-Key'] = idempotencyKey
    if (role) headers['X-Worldsim-Role'] = role
    if (characterId) headers['X-Worldsim-Character'] = characterId
    let res: Response
    try {
      res = await fetchImpl(`${API_BASE}${path}`, {
        method,
        headers,
        body: body !== undefined ? JSON.stringify(body) : undefined,
        signal: controller.signal
      })
    } catch (err) {
      // Modern fetch rejects with the abort reason itself, so our own
      // timeout/cancel reasons surface here directly. Anything else is a
      // transport failure (DNS, refused, offline) — retryable, not a cancel.
      // A cancelled client request says nothing about the server mutation.
      if (err instanceof Error && err.message === 'REQUEST_TIMEOUT') {
        throw new ApiError('REQUEST_TIMEOUT', 'request timed out', 0, true)
      }
      if (timedOut) {
        throw new ApiError('REQUEST_TIMEOUT', 'request timed out', 0, true)
      }
      if (
        (err instanceof Error && err.message === 'REQUEST_ABORTED') ||
        outerAborted ||
        signal?.aborted
      ) {
        throw new ApiError('REQUEST_ABORTED', 'request cancelled', 0, false)
      }
      throw new ApiError(
        'REQUEST_TRANSPORT',
        err instanceof Error ? `network failure: ${err.message}` : 'network failure',
        0,
        true
      )
    }
    if (!res.ok) {
      let envelope: EnvelopeError | null = null
      try {
        envelope = readEnvelope(await res.json())
      } catch {
        envelope = null
      }
      throw new ApiError(
        envelope?.code ?? `HTTP_${res.status}`,
        envelope?.message ?? `request failed: HTTP ${res.status}`,
        res.status,
        statusToRetryable(res.status)
      )
    }
    if (res.status === 204) return undefined as T
    try {
      return (await res.json()) as T
    } catch (err) {
      // Body consumption rejects with the abort reason too: preserve
      // timeout/cancellation identity so mutation recovery paths (selected
      // by REQUEST_TIMEOUT) still trigger. Only a genuinely malformed body
      // is a transport/protocol error.
      if (err instanceof Error && err.message === 'REQUEST_TIMEOUT') {
        throw new ApiError('REQUEST_TIMEOUT', 'request timed out', 0, true)
      }
      if (timedOut) {
        throw new ApiError('REQUEST_TIMEOUT', 'request timed out', 0, true)
      }
      if (
        (err instanceof Error && err.message === 'REQUEST_ABORTED') ||
        outerAborted ||
        signal?.aborted
      ) {
        throw new ApiError('REQUEST_ABORTED', 'request cancelled', 0, false)
      }
      throw new ApiError(
        'REQUEST_TRANSPORT',
        err instanceof Error ? `unreadable response: ${err.message}` : 'unreadable response',
        res.status,
        true
      )
    }
  } finally {
    clearTimeout(timer)
    signal?.removeEventListener('abort', onOuterAbort)
  }
}

/** Fresh idempotency key per user operation (retries reuse the same key). */
export function newOperationKey(): string {
  return crypto.randomUUID()
}
