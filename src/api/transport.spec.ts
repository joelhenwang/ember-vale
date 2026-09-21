import { describe, expect, it, vi } from 'vitest'
import { ApiError, apiFetch, isIdempotencyConflict, isVersionConflict } from './http'

function ok(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status })
}

describe('api transport', () => {
  it('sends role, character and idempotency headers', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(ok({ ok: true }))
    await apiFetch('/stories', {
      fetchImpl: fetchImpl as unknown as typeof fetch,
      role: 'player',
      characterId: 'char-1',
      idempotencyKey: 'key-1',
      method: 'POST',
      body: { a: 1 }
    })
    const [, init] = fetchImpl.mock.calls[0] as [string, RequestInit]
    const headers = init.headers as Record<string, string>
    expect(headers['X-Worldsim-Role']).toBe('player')
    expect(headers['X-Worldsim-Character']).toBe('char-1')
    expect(headers['Idempotency-Key']).toBe('key-1')
  })

  it('parses the stable error envelope and marks retryability', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ error: { code: 'VERSION_CONFLICT', message: 'stale' } }), {
        status: 409
      })
    )
    const err = await apiFetch('/stories/x', {
      fetchImpl: fetchImpl as unknown as typeof fetch
    }).catch((e: unknown) => e)
    expect(err).toBeInstanceOf(ApiError)
    const apiErr = err as ApiError
    expect(apiErr.code).toBe('VERSION_CONFLICT')
    expect(apiErr.status).toBe(409)
    expect(apiErr.retryable).toBe(false)
    expect(isVersionConflict(err)).toBe(true)
    expect(isIdempotencyConflict(err)).toBe(false)
  })

  it('marks 503 retryable and falls back without an envelope', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(new Response('oops', { status: 503 }))
    const err = (await apiFetch('/health/ready', {
      fetchImpl: fetchImpl as unknown as typeof fetch
    }).catch((e: unknown) => e)) as ApiError
    expect(err.code).toBe('HTTP_503')
    expect(err.retryable).toBe(true)
  })

  it('reports cancellation as cancelled, never as success', async () => {
    const controller = new AbortController()
    controller.abort()
    const fetchImpl = vi.fn().mockRejectedValue(new Error('REQUEST_ABORTED'))
    const err = (await apiFetch('/stories', {
      fetchImpl: fetchImpl as unknown as typeof fetch,
      signal: controller.signal
    }).catch((e: unknown) => e)) as ApiError
    expect(err.cancelled).toBe(true)
    expect(isVersionConflict(err)).toBe(false)
  })

  it('reports a network outage as retryable transport failure, not cancellation', async () => {
    const fetchImpl = vi.fn().mockRejectedValue(new TypeError('Failed to fetch'))
    const err = (await apiFetch('/stories', {
      fetchImpl: fetchImpl as unknown as typeof fetch
    }).catch((e: unknown) => e)) as ApiError
    expect(err).toBeInstanceOf(ApiError)
    expect(err.code).toBe('REQUEST_TRANSPORT')
    expect(err.cancelled).toBe(false)
    expect(err.retryable).toBe(true)
  })

  it('reports an unreadable response body as transport failure', async () => {
    const res = new Response('ok', { status: 200 })
    vi.spyOn(res, 'json').mockRejectedValue(new TypeError('body stream closed'))
    const fetchImpl = vi.fn().mockResolvedValue(res)
    const err = (await apiFetch('/stories', {
      fetchImpl: fetchImpl as unknown as typeof fetch
    }).catch((e: unknown) => e)) as ApiError
    expect(err.code).toBe('REQUEST_TRANSPORT')
    expect(err.cancelled).toBe(false)
    expect(err.retryable).toBe(true)
  })

  it('reports the internal timeout as timeout, not cancellation', async () => {
    const fetchImpl = vi.fn().mockRejectedValue(new Error('REQUEST_TIMEOUT'))
    const err = (await apiFetch('/stories', {
      fetchImpl: fetchImpl as unknown as typeof fetch
    }).catch((e: unknown) => e)) as ApiError
    expect(err.code).toBe('REQUEST_TIMEOUT')
    expect(err.cancelled).toBe(false)
    expect(err.retryable).toBe(true)
  })

  it('keeps timeout identity when the body stalls after headers', async () => {
    const res = new Response('partial', { status: 200 })
    vi.spyOn(res, 'json').mockRejectedValue(new Error('REQUEST_TIMEOUT'))
    const fetchImpl = vi.fn().mockResolvedValue(res)
    const err = (await apiFetch('/stories', {
      fetchImpl: fetchImpl as unknown as typeof fetch
    }).catch((e: unknown) => e)) as ApiError
    expect(err.code).toBe('REQUEST_TIMEOUT')
    expect(err.cancelled).toBe(false)
    expect(err.retryable).toBe(true)
  })

  it('keeps cancellation identity when an abort lands mid-body', async () => {
    const controller = new AbortController()
    controller.abort()
    const res = new Response('partial', { status: 200 })
    vi.spyOn(res, 'json').mockRejectedValue(new DOMException('aborted', 'AbortError'))
    const fetchImpl = vi.fn().mockResolvedValue(res)
    const err = (await apiFetch('/stories', {
      fetchImpl: fetchImpl as unknown as typeof fetch,
      signal: controller.signal
    }).catch((e: unknown) => e)) as ApiError
    expect(err.code).toBe('REQUEST_ABORTED')
    expect(err.cancelled).toBe(true)
  })

  it('reports a real outer abort as cancellation even with a native AbortError', async () => {
    const controller = new AbortController()
    controller.abort()
    const fetchImpl = vi.fn().mockRejectedValue(new DOMException('aborted', 'AbortError'))
    const err = (await apiFetch('/stories', {
      fetchImpl: fetchImpl as unknown as typeof fetch,
      signal: controller.signal
    }).catch((e: unknown) => e)) as ApiError
    expect(err.code).toBe('REQUEST_ABORTED')
    expect(err.cancelled).toBe(true)
    expect(err.retryable).toBe(false)
  })
})
