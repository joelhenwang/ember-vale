import { describe, expect, it } from 'vitest'
import { useStorytellerPin, type PinApi } from './useStorytellerPin'
import type { ProviderConnectionView, ProviderProfileView } from '../../content/clients/worldsim'

function connection(id: string, name: string): ProviderConnectionView {
  return {
    id,
    name,
    adapter: 'openrouter',
    endpoint: 'https://example.invalid/v1',
    config_version: 1,
    created_at: '2026-09-24T00:00:00Z'
  }
}

function profile(
  connectionId: string,
  id: string,
  model: string,
  revision: number
): ProviderProfileView {
  return {
    connection_id: connectionId,
    id,
    model_id: model,
    revision,
    max_tokens: 1024,
    created_at: ''
  }
}

/** Manually settled promises standing in for network latency. */
function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

function flush(): Promise<void> {
  return new Promise((res) => setTimeout(res, 0))
}

describe('useStorytellerPin', () => {
  it('a late response never stamps a deselected provider pin', async () => {
    const profilesA = deferred<ProviderProfileView[]>()
    const api: PinApi = {
      listProviders: async () => [connection('a', 'A'), connection('b', 'B')],
      listProfiles: async (id: string) => (id === 'a' ? profilesA.promise : [])
    }
    const pin = useStorytellerPin(api)
    await pin.ensure()
    pin.selectProvider('a')
    await flush()
    // Deselect while A's profiles are still pending.
    pin.selectProvider('')
    profilesA.resolve([profile('a', 'pa', 'model-a', 2)])
    await flush()
    await flush()
    expect(pin.providerId.value).toBe('')
    expect(pin.profileId.value).toBe('')
    expect(pin.pin.value).toBeUndefined()
    expect(pin.summary.value).toBe('Environment default')
  })

  it('out-of-order responses resolve to the current provider', async () => {
    const profilesA = deferred<ProviderProfileView[]>()
    const profilesB = deferred<ProviderProfileView[]>()
    const api: PinApi = {
      listProviders: async () => [connection('a', 'A'), connection('b', 'B')],
      listProfiles: async (id: string) => (id === 'a' ? profilesA.promise : profilesB.promise)
    }
    const pin = useStorytellerPin(api)
    await pin.ensure()
    pin.selectProvider('a')
    await flush()
    pin.selectProvider('b')
    await flush()
    // A's stale response arrives first: no profiles, no default.
    profilesA.resolve([profile('a', 'pa', 'model-a', 2)])
    await flush()
    await flush()
    expect(pin.profiles.value).toEqual([])
    expect(pin.profileId.value).toBe('')
    // B's response wins: newest revision becomes the pin.
    profilesB.resolve([profile('b', 'pb1', 'model-b', 1), profile('b', 'pb2', 'model-b', 2)])
    await flush()
    await flush()
    expect(pin.profiles.value.map((p) => p.id)).toEqual(['pb2', 'pb1'])
    expect(pin.pin.value).toEqual({ profileId: 'pb2', profileRevision: 2 })
    expect(pin.summary.value).toBe('B · model-b · rev 2')
  })

  it('retry reloads a selected provider whose profiles failed', async () => {
    let fail = true
    const api: PinApi = {
      listProviders: async () => [connection('a', 'A')],
      listProfiles: async () => {
        if (fail) throw new Error('provider down')
        return [profile('a', 'pa', 'model-a', 3)]
      }
    }
    const pin = useStorytellerPin(api)
    await pin.ensure()
    pin.selectProvider('a')
    await flush()
    await flush()
    expect(pin.profileId.value).toBe('')
    expect(pin.error.value).toBe('provider down')
    expect(pin.summary.value).toBe('A · profiles unavailable — retry or choose Environment default')
    // Previously retry returned early here because no profile had loaded.
    fail = false
    await pin.retry()
    expect(pin.error.value).toBeNull()
    expect(pin.pin.value).toEqual({ profileId: 'pa', profileRevision: 3 })
    expect(pin.summary.value).toBe('A · model-a · rev 3')
  })

  it('creation validity follows resolution, not intent', async () => {
    const profilesA = deferred<ProviderProfileView[]>()
    const api: PinApi = {
      listProviders: async () => [connection('a', 'A')],
      listProfiles: async () => profilesA.promise
    }
    const pin = useStorytellerPin(api)
    await pin.ensure()
    // Explicit default is valid.
    expect(pin.pinValid.value).toBe(true)
    expect(pin.pinIssue.value).toBeNull()
    // A selected provider with profiles still pending is not.
    pin.selectProvider('a')
    await flush()
    expect(pin.pinValid.value).toBe(false)
    expect(pin.pinIssue.value).toContain('no resolved profile')
    // Resolution unblocks.
    profilesA.resolve([profile('a', 'pa', 'model-a', 2)])
    await flush()
    await flush()
    expect(pin.pinValid.value).toBe(true)
    expect(pin.pinIssue.value).toBeNull()
    // Explicit default again is valid.
    pin.selectProvider('')
    expect(pin.pinValid.value).toBe(true)
  })

  it('an exact restored pin stays submittable through metadata failure', async () => {
    const api: PinApi = {
      listProviders: async () => {
        throw new Error('library unreachable')
      },
      listProfiles: async () => []
    }
    const pin = useStorytellerPin(api)
    pin.restorePin('saved-profile', 4)
    await pin.ensure()
    // No provider could be named, but the exact pin survived.
    expect(pin.providerId.value).toBe('')
    expect(pin.pin.value).toEqual({ profileId: 'saved-profile', profileRevision: 4 })
    expect(pin.pinValid.value).toBe(true)
    expect(pin.summary.value).toContain('unknown provider')
    expect(pin.summary.value).not.toBe('Environment default')
  })

  it('an explicit profile choice survives and clears cleanly', async () => {
    const api: PinApi = {
      listProviders: async () => [connection('a', 'A')],
      listProfiles: async () => [
        profile('a', 'pa1', 'model-a', 1),
        profile('a', 'pa2', 'model-a', 2)
      ]
    }
    const pin = useStorytellerPin(api)
    await pin.ensure()
    pin.selectProvider('a')
    await flush()
    await flush()
    expect(pin.profileId.value).toBe('pa2')
    pin.selectProfile('pa1')
    expect(pin.pin.value).toEqual({ profileId: 'pa1', profileRevision: 1 })
    pin.reset()
    expect(pin.pin.value).toBeUndefined()
    expect(pin.summary.value).toBe('Environment default')
  })
})
