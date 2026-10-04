import { describe, expect, it } from 'vitest'
import { ApiError } from '../api/http'
import type {
  ProviderConnectionView,
  ProviderProfileView,
  ProviderTestView
} from '../../content/clients/worldsim'
import {
  NEW_CONNECTION,
  useProviderSettings,
  type ProviderSettingsApi
} from './useProviderSettings'

function connection(over: Partial<ProviderConnectionView> = {}): ProviderConnectionView {
  return {
    id: 'c1',
    adapter: 'openrouter',
    name: 'OpenRouter',
    endpoint: 'https://openrouter.ai/api/v1',
    credential_env: 'MY_KEY',
    has_credential: true,
    config_version: 1,
    created_at: '',
    ...over
  }
}

function profile(over: Partial<ProviderProfileView> = {}): ProviderProfileView {
  return {
    id: 'p1',
    connection_id: 'c1',
    revision: 1,
    model_id: 'openrouter/auto',
    max_tokens: 512,
    created_at: '',
    ...over
  }
}

/** In-memory backend that records every call. */
function fakeApi(initial: ProviderConnectionView[] = []) {
  const calls: string[] = []
  const rows = [...initial]
  const revisions: Record<string, ProviderProfileView[]> = Object.fromEntries(
    initial.map((c) => [c.id, [profile({ connection_id: c.id })]])
  )
  let testResult: ProviderTestView = { state: 'succeeded', reachable: true }
  const api: ProviderSettingsApi = {
    listProviders: async () => {
      calls.push('list')
      return rows.map((row) => ({ ...row }))
    },
    listProfiles: async (id) => revisions[id] ?? [],
    createProvider: async (body) => {
      calls.push('create')
      const created = connection({
        id: 'c-new',
        name: body.name,
        endpoint: body.endpoint,
        credential_env: body.credential_env ?? null
      })
      rows.push(created)
      revisions[created.id] = [profile({ id: 'p-new', connection_id: created.id })]
      return created
    },
    updateProvider: async (id, body) => {
      calls.push(`patch:${Object.keys(body).sort().join(',')}`)
      const current = rows.find((c) => c.id === id)!
      if (body.expected_version !== current.config_version) {
        throw new ApiError('VERSION_CONFLICT', 'stale', 409, false)
      }
      const updated = { ...current, name: body.name ?? current.name, config_version: 2 }
      rows.splice(rows.indexOf(current), 1, updated)
      return updated
    },
    addProfile: async (id, body) => {
      calls.push(`profile:${body.model_id}`)
      const next = profile({
        id: `p${(revisions[id]?.length ?? 0) + 1}`,
        connection_id: id,
        revision: (revisions[id]?.length ?? 0) + 1,
        model_id: body.model_id,
        max_tokens: body.max_tokens ?? 512
      })
      revisions[id] = [...(revisions[id] ?? []), next]
      return next
    },
    testProvider: async (id) => {
      calls.push(`test:${id}`)
      const current = rows.find((c) => c.id === id)!
      return { ...testResult, tested_config_revision: current.config_version }
    }
  }
  return {
    api,
    calls,
    setTest(result: ProviderTestView) {
      testResult = result
    },
    /** Another client saved this connection on the server. */
    bumpServerVersion(id: string) {
      const i = rows.findIndex((c) => c.id === id)
      rows[i] = { ...rows[i], config_version: rows[i].config_version + 1 }
    }
  }
}

describe('useProviderSettings', () => {
  it('starts on a new connection when none exist and creates it on save', async () => {
    const { api, calls } = fakeApi()
    const s = useProviderSettings(api)
    await s.load()
    expect(s.selected.value).toBe(NEW_CONNECTION)
    s.form.value.modelId = 'mistralai/mistral-nemo'
    expect(await s.save()).toBe(true)
    // The server creates revision 1 with the default model; the chosen
    // model becomes revision 2.
    expect(calls).toEqual(['list', 'create', 'profile:mistralai/mistral-nemo'])
    expect(s.selected.value).toBe('c-new')
    expect(s.dirty.value).toBe(false)
    expect(s.profile.value?.revision).toBe(2)
  })

  it('selects the first saved connection and starts clean', async () => {
    const { api } = fakeApi([connection()])
    const s = useProviderSettings(api)
    await s.load()
    expect(s.selected.value).toBe('c1')
    expect(s.dirty.value).toBe(false)
    expect(s.status.value).toBe('untested')
  })

  it('patches a rename without adding a profile revision', async () => {
    const { api, calls } = fakeApi([connection()])
    const s = useProviderSettings(api)
    await s.load()
    s.form.value.name = 'Main'
    await s.save()
    expect(calls).toEqual(['list', 'patch:expected_version,name'])
  })

  it('does not test unsaved values and reports reachability after saving', async () => {
    const { api, calls } = fakeApi([connection()])
    const s = useProviderSettings(api)
    await s.load()
    s.form.value.name = 'Main'
    expect(s.canTest.value).toBe(false)
    await s.test()
    expect(calls).not.toContain('test:c1')
    await s.save()
    await s.test()
    expect(s.status.value).toBe('reachable')
  })

  it('surfaces a version conflict without claiming the save worked', async () => {
    const { api, bumpServerVersion } = fakeApi([connection()])
    const s = useProviderSettings(api)
    await s.load()
    bumpServerVersion('c1') // another tab saved meanwhile
    s.form.value.name = 'Main'
    expect(await s.save()).toBe(false)
    expect(s.error.value).toMatch(/changed elsewhere/)
    expect(s.dirty.value).toBe(true)
  })

  it('refuses to save invalid input', async () => {
    const { api, calls } = fakeApi([connection()])
    const s = useProviderSettings(api)
    await s.load()
    s.form.value.endpoint = 'not a url'
    expect(s.valid.value).toBe(false)
    expect(await s.save()).toBe(false)
    expect(calls).toEqual(['list'])
  })

  it('discard restores the saved values', async () => {
    const { api } = fakeApi([connection()])
    const s = useProviderSettings(api)
    await s.load()
    s.form.value.modelId = 'something/else'
    s.discard()
    expect(s.form.value.modelId).toBe('openrouter/auto')
    expect(s.dirty.value).toBe(false)
  })

  it('reports an unreachable endpoint honestly', async () => {
    const { api, setTest } = fakeApi([connection()])
    setTest({ state: 'failed', reachable: false, detail: 'unreachable: refused' })
    const s = useProviderSettings(api)
    await s.load()
    await s.test()
    expect(s.status.value).toBe('unreachable')
    expect(s.lastTest.value?.detail).toContain('refused')
  })
})
