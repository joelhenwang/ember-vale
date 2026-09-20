import { describe, expect, it, vi } from 'vitest'
import { allChecksPass, buildApiUrl, fetchReady, isBackendReady } from './client'

describe('api client spine', () => {
  it('joins paths without double slashes', () => {
    expect(buildApiUrl('/health/ready')).toBe('/api/v1/health/ready')
    expect(buildApiUrl('health/live')).toBe('/api/v1/health/live')
  })

  it('accepts only an exact ready status', () => {
    expect(isBackendReady({ status: 'ready' })).toBe(true)
    expect(isBackendReady({ status: 'degraded' })).toBe(false)
    expect(isBackendReady({ status: 'READY' })).toBe(false)
  })

  it('requires at least one check and no failures', () => {
    expect(allChecksPass({ status: 'ready', checks: [] })).toBe(false)
    expect(allChecksPass({ status: 'ready' })).toBe(false)
    expect(
      allChecksPass({
        status: 'ready',
        checks: [
          { name: 'database', status: 'ok' },
          { name: 'migrations', status: 'ok' }
        ]
      })
    ).toBe(true)
    expect(
      allChecksPass({ status: 'ready', checks: [{ name: 'database', status: 'failed' }] })
    ).toBe(false)
  })

  it('throws on non-OK readiness HTTP, never reports success', async () => {
    const fetchImpl = vi.fn().mockResolvedValue({ ok: false, status: 503 })
    await expect(fetchReady(fetchImpl as unknown as typeof fetch)).rejects.toThrow('HTTP 503')
  })
})
