import { describe, expect, it, vi } from 'vitest'
import {
  allChecksPass,
  buildApiUrl,
  fetchReady,
  findCheck,
  isBackendReady,
  modelProfileDetail,
  seedStatus,
  type ReadyResponse
} from './client'

const READY_FIXTURE: ReadyResponse = {
  status: 'ready',
  version: '0.1.0',
  environment: 'local',
  migration_head: '0031_settings_pipeline',
  schema_version: 1,
  checks: [
    { name: 'database', status: 'ok', detail: '' },
    { name: 'migrations', status: 'ok', detail: '0031_settings_pipeline' },
    { name: 'extensions', status: 'ok', detail: 'vector' },
    { name: 'seed', status: 'degraded', detail: 'worlds:0 versions:' },
    { name: 'model_profile', status: 'ok', detail: 'active:fake' }
  ]
}

describe('api client spine', () => {
  it('joins paths without double slashes', () => {
    expect(buildApiUrl('/health/ready')).toBe('/api/v1/health/ready')
    expect(buildApiUrl('health/live')).toBe('/api/v1/health/live')
  })

  it('accepts only an exact ready status', () => {
    expect(isBackendReady({ ...READY_FIXTURE, status: 'ready' })).toBe(true)
    expect(isBackendReady({ ...READY_FIXTURE, status: 'degraded' })).toBe(false)
  })

  it('passes only when every check is positively ok', () => {
    expect(allChecksPass({ ...READY_FIXTURE, status: 'ready', checks: [] })).toBe(false)
    // fresh-install fixture: seed is degraded, so the whole set does not pass
    expect(allChecksPass(READY_FIXTURE)).toBe(false)
    expect(
      allChecksPass({
        ...READY_FIXTURE,
        checks: [
          { name: 'database', status: 'ok' },
          { name: 'migrations', status: 'ok' }
        ]
      })
    ).toBe(true)
    // degraded / failed / unknown-status checks never pass
    for (const status of ['degraded', 'failed', 'unknown'] as const) {
      expect(
        allChecksPass({
          ...READY_FIXTURE,
          checks: [
            { name: 'database', status: 'ok' },
            { name: 'migrations', status: status as never }
          ]
        })
      ).toBe(false)
    }
  })

  it('treats an empty seed as advisory, not blocking', () => {
    expect(seedStatus(READY_FIXTURE)).toBe('degraded')
    expect(seedStatus({ ...READY_FIXTURE, checks: [] })).toBe('missing')
    expect(
      seedStatus({
        ...READY_FIXTURE,
        checks: [{ name: 'seed', status: 'ok', detail: 'worlds:1 versions:v1' }]
      })
    ).toBe('ok')
  })

  it('reports the provider profile separately from readiness', () => {
    expect(modelProfileDetail(READY_FIXTURE)).toBe('active:fake')
    expect(modelProfileDetail({ ...READY_FIXTURE, checks: [] })).toBeNull()
    expect(findCheck(READY_FIXTURE, 'nope')).toBeUndefined()
  })

  it('matches the authoritative envelope shape (integer schema_version)', () => {
    expect(typeof READY_FIXTURE.schema_version).toBe('number')
    expect(READY_FIXTURE.migration_head).toBe('0031_settings_pipeline')
  })

  it('throws on non-OK readiness HTTP, never reports success', async () => {
    const fetchImpl = vi.fn().mockResolvedValue({ ok: false, status: 503 })
    await expect(fetchReady(fetchImpl as unknown as typeof fetch)).rejects.toThrow('HTTP 503')
  })
})
