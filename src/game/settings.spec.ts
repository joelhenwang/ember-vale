import { describe, expect, it } from 'vitest'
import {
  applyConnectionTest,
  discardSettings,
  isSettingsDirty,
  providerModels,
  saveSettings,
  setProvider,
  settings
} from './settings'

describe('settings dirty cycle', () => {
  it('save clears dirty; an edit re-arms it; discard restores values', () => {
    settings.story.endpoint = 'http://example.test/v1'
    saveSettings()
    expect(isSettingsDirty()).toBe(false)

    settings.story.endpoint = 'http://changed.test/v1'
    expect(isSettingsDirty()).toBe(true)

    discardSettings()
    expect(settings.story.endpoint).toBe('http://example.test/v1')
    expect(isSettingsDirty()).toBe(false)
  })
})

describe('connection tests', () => {
  it('marks an endpoint-less provider unreachable and blanks the check note', () => {
    settings.story.endpoint = ''
    applyConnectionTest('story')
    expect(settings.story.status).toBe('unreachable')
    expect(settings.story.lastChecked).toBe('just now')
  })
  it('reaches a set endpoint', () => {
    settings.story.endpoint = 'http://localhost:9/v1'
    applyConnectionTest('story')
    expect(settings.story.status).toBe('reachable')
  })
  it('a reachable image provider reports its capabilities', () => {
    settings.image.provider = 'OpenAI Images'
    settings.image.endpoint = 'https://api.example.test'
    applyConnectionTest('image')
    expect(settings.image.status).toBe('reachable')
    expect(settings.image.envImages).toBe('supported')
    expect(settings.image.charRefs).toBe('supported')
  })
})

describe('provider/model coupling', () => {
  it('lists models per provider and none without a provider', () => {
    expect(providerModels('story').length).toBeGreaterThan(0)
    settings.image.provider = ''
    expect(providerModels('image')).toEqual([])
  })
  it('switching provider clears a now-invalid model but keeps a valid one', () => {
    setProvider('story', 'Anthropic')
    expect(settings.story.provider).toBe('Anthropic')
    settings.story.model = 'claude-sonnet-4-5'
    setProvider('story', 'Anthropic')
    expect(settings.story.model).toBe('claude-sonnet-4-5')
    setProvider('story', 'Google Gemini')
    expect(settings.story.model).toBe('')
  })
})
