import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  loadCreateRequest,
  resetPresetCreationMemoryForTests,
  usePresetCreation
} from './usePresetCreation'
import { resetEditorDraftMemoryForTests } from './useEditorDraft'

let bodies: Array<{ key: string; body: Record<string, unknown> }> = []
let held: Array<() => void> = []
let failNextCreate: 'transport' | 'conflict' | null = null
let nextId = 0

function installFetch(): void {
  bodies = []
  held = []
  failNextCreate = null
  nextId = 0
  resetPresetCreationMemoryForTests()
  resetEditorDraftMemoryForTests()
  vi.stubGlobal(
    'fetch',
    vi.fn(async (rawUrl: string, init: RequestInit = {}) => {
      const url = new URL(rawUrl, 'http://test')
      if (url.pathname === '/api/v1/library/presets' && (init.method ?? 'GET') === 'POST') {
        if (holdCreate) {
          await new Promise<void>((resolve) => held.push(resolve))
        }
        const headers = (init.headers ?? {}) as Record<string, string>
        const body = JSON.parse(String(init.body)) as Record<string, unknown>
        bodies.push({ key: headers['Idempotency-Key'] ?? '', body })
        if (failNextCreate === 'transport') {
          failNextCreate = null
          throw new Error('network failure: connection reset')
        }
        if (failNextCreate === 'conflict') {
          failNextCreate = null
          return new Response(
            JSON.stringify({
              error: { code: 'IDEMPOTENCY_CONFLICT', message: 'key used for different request' }
            }),
            { status: 409 }
          )
        }
        nextId += 1
        return new Response(
          JSON.stringify({ id: `preset-${nextId}`, kind: body['kind'], current_revision: 1 }),
          { status: 200 }
        )
      }
      return new Response(JSON.stringify({}), { status: 200 })
    })
  )
}

let holdCreate = false

afterEach(() => {
  vi.unstubAllGlobals()
  holdCreate = false
})

const payloadA = () => ({ kind: 'world', name: 'Basin Vale', description: 'Basin.' })
const payloadB = () => ({ kind: 'world', name: 'Basin Vale', description: 'Basin, revised.' })

describe('usePresetCreation', () => {
  it('creates under a stable key and clears the frozen state on receipt', async () => {
    installFetch()
    const ctl = usePresetCreation('world-new')
    expect(ctl.pending.value).toBe(false)
    const id = await ctl.submit('world', payloadA())
    expect(id).toBe('preset-1')
    expect(ctl.status.value).toBe('idle')
    expect(ctl.pending.value).toBe(false)
    expect(bodies).toHaveLength(1)
    expect(bodies[0]!.key).toMatch(/^[0-9a-f-]{36}$/)
    expect(bodies[0]!.body).toMatchObject({ kind: 'world', name: 'Basin Vale' })
    expect(loadCreateRequest('world-new')).toBeNull()
  })

  it('retries a lost response with identical bytes under the same key', async () => {
    installFetch()
    const ctl = usePresetCreation('world-new')
    failNextCreate = 'transport'
    expect(await ctl.submit('world', payloadA())).toBeNull()
    expect(ctl.status.value).toBe('failed')
    expect(ctl.pending.value).toBe(true)
    const retry = await ctl.submit('world', payloadA())
    expect(retry).toBe('preset-1')
    // Same key, byte-identical body: the server replays the receipt.
    expect(bodies).toHaveLength(2)
    expect(bodies[1]!.key).toBe(bodies[0]!.key)
    expect(JSON.stringify(bodies[1]!.body)).toBe(JSON.stringify(bodies[0]!.body))
    expect(loadCreateRequest('world-new')).toBeNull()
  })

  it('resumes the frozen submission in a fresh mount (reload)', async () => {
    installFetch()
    const first = usePresetCreation('world-new')
    failNextCreate = 'transport'
    expect(await first.submit('world', payloadA())).toBeNull()
    // A remount (reload) sees the pending submission and reuses its key.
    const second = usePresetCreation('world-new')
    expect(second.pending.value).toBe(true)
    expect(await second.submit('world', payloadA())).toBe('preset-1')
    expect(bodies).toHaveLength(2)
    expect(bodies[1]!.key).toBe(bodies[0]!.key)
  })

  it('changed content starts a distinct submission under a fresh key', async () => {
    installFetch()
    const ctl = usePresetCreation('world-new')
    failNextCreate = 'transport'
    expect(await ctl.submit('world', payloadA())).toBeNull()
    const id = await ctl.submit('world', payloadB())
    expect(id).toBe('preset-1')
    expect(bodies).toHaveLength(2)
    expect(bodies[1]!.key).not.toBe(bodies[0]!.key)
    expect(bodies[1]!.body).toMatchObject({ name: 'Basin Vale' })
  })

  it('surfaces a key conflict and keeps the frozen request for recovery', async () => {
    installFetch()
    const ctl = usePresetCreation('world-new')
    failNextCreate = 'conflict'
    expect(await ctl.submit('world', payloadA())).toBeNull()
    expect(ctl.status.value).toBe('failed')
    expect(ctl.error.value).toMatch(/already recorded a different submission/)
    // The frozen bytes stay: retrying them unchanged replays the receipt.
    expect(ctl.pending.value).toBe(true)
    expect(loadCreateRequest('world-new')).not.toBeNull()
  })

  it('collapses concurrent submissions into one request', async () => {
    installFetch()
    holdCreate = true
    const ctl = usePresetCreation('world-new')
    const first = ctl.submit('world', payloadA())
    const second = await ctl.submit('world', payloadA())
    expect(second).toBeNull()
    holdCreate = false
    held.splice(0).forEach((release) => release())
    expect(await first).toBe('preset-1')
    expect(bodies).toHaveLength(1)
  })

  it('requires a name before creating', async () => {
    installFetch()
    const ctl = usePresetCreation('world-new')
    expect(await ctl.submit('world', { kind: 'world', name: '   ' })).toBeNull()
    expect(ctl.status.value).toBe('failed')
    expect(bodies).toHaveLength(0)
  })
})
