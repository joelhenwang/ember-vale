import { describe, expect, it } from 'vitest'
import type {
  ProviderConnectionView,
  ProviderProfileView,
  ProviderTestView
} from '../../content/clients/worldsim'
import {
  createRequest,
  emptyForm,
  formFrom,
  latestProfile,
  patchRequest,
  profileChanged,
  profileRequest,
  statusFromTest,
  validateForm
} from './providerSettings'

function connection(over: Partial<ProviderConnectionView> = {}): ProviderConnectionView {
  return {
    id: 'c1',
    adapter: 'openrouter',
    name: 'OpenRouter',
    endpoint: 'https://openrouter.ai/api/v1',
    credential_env: 'MY_KEY',
    has_credential: true,
    allow_local_endpoint: false,
    config_version: 3,
    created_at: '2026-10-04T00:00:00Z',
    ...over
  }
}

function profile(over: Partial<ProviderProfileView> = {}): ProviderProfileView {
  return {
    id: 'p1',
    connection_id: 'c1',
    revision: 2,
    model_id: 'mistralai/mistral-nemo',
    temperature: 0.2,
    top_p: null,
    top_k: null,
    max_tokens: 1024,
    created_at: '2026-10-04T00:00:00Z',
    ...over
  }
}

describe('providerSettings', () => {
  it('round-trips a saved connection into the form without changes', () => {
    const form = formFrom(connection(), profile())
    expect(form.modelId).toBe('mistralai/mistral-nemo')
    expect(form.temperature).toBe('0.2')
    expect(form.topP).toBe('')
    expect(patchRequest(form, connection())).toBeNull()
    expect(profileChanged(form, profile())).toBe(false)
  })

  it('patches only the fields that changed, with the expected version', () => {
    const form = { ...formFrom(connection(), profile()), name: 'Main' }
    expect(patchRequest(form, connection())).toEqual({ expected_version: 3, name: 'Main' })
  })

  it('adds a profile revision only when model or sampling changed', () => {
    const base = formFrom(connection(), profile())
    expect(profileChanged({ ...base, name: 'Renamed' }, profile())).toBe(false)
    expect(profileChanged({ ...base, temperature: '0.7' }, profile())).toBe(true)
    expect(profileChanged({ ...base, modelId: 'other/model' }, profile())).toBe(true)
    expect(profileChanged(base, null)).toBe(true)
  })

  it('sends blank sampling fields as null and keeps max tokens', () => {
    const form = { ...emptyForm(), temperature: ' ', topK: '40', maxTokens: '2048' }
    expect(profileRequest(form)).toEqual({
      model_id: 'openrouter/auto',
      temperature: null,
      top_p: null,
      top_k: 40,
      max_tokens: 2048
    })
  })

  it('validates the same limits as the backend', () => {
    const errors = validateForm({
      ...emptyForm(),
      name: '',
      endpoint: 'openrouter.ai',
      credentialEnv: 'not a var',
      temperature: '3',
      topK: '2.5',
      maxTokens: '5000'
    })
    expect(Object.keys(errors).sort()).toEqual(
      ['credentialEnv', 'endpoint', 'maxTokens', 'name', 'temperature', 'topK'].sort()
    )
    expect(validateForm(emptyForm())).toEqual({})
  })

  it('creates with a null credential reference when none is given', () => {
    expect(createRequest({ ...emptyForm(), credentialEnv: '' }).credential_env).toBeNull()
  })

  it('never reports a test of an older configuration as reachable', () => {
    const result: ProviderTestView = {
      state: 'succeeded',
      reachable: true,
      tested_config_revision: 2
    }
    expect(statusFromTest(result, connection({ config_version: 2 }))).toBe('reachable')
    expect(statusFromTest(result, connection({ config_version: 3 }))).toBe('untested')
    expect(statusFromTest({ ...result, reachable: false }, connection({ config_version: 2 }))).toBe(
      'unreachable'
    )
    expect(statusFromTest(null, connection())).toBe('untested')
  })

  it('picks the newest profile revision', () => {
    expect(latestProfile([profile({ revision: 1 }), profile({ revision: 4 })])?.revision).toBe(4)
    expect(latestProfile([])).toBeNull()
  })
})
