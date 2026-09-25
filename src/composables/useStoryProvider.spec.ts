import { describe, expect, it } from 'vitest'
import {
  beatFallbackNotice,
  describeEnvironment,
  describeStoryProvider,
  useStoryProvider
} from './useStoryProvider'
import type { StoryProviderView } from '../../content/clients/worldsim'

function view(overrides: Partial<StoryProviderView>): StoryProviderView {
  return {
    story_id: 'story-1',
    world_id: 'world-1',
    pin_state: 'none',
    environment: { active_profile: 'fake', adapter: 'fake' },
    effective_source: 'environment',
    effective_adapter: 'fake',
    ...overrides
  }
}

describe('describeStoryProvider', () => {
  it('names a live pin with model and revision, never as stand-ins', () => {
    const banner = describeStoryProvider(
      view({
        pin_state: 'ok',
        pin: {
          profile_id: 'p1',
          revision: 3,
          model_id: 'live-model',
          adapter: 'openrouter',
          connection_name: 'Live'
        },
        effective_source: 'pin',
        effective_adapter: 'openrouter',
        effective_model_id: 'live-model',
        effective_revision: 3
      }),
      false
    )
    expect(banner?.tone).toBe('info')
    expect(banner?.text).toContain('live-model')
    expect(banner?.text).toContain('rev 3')
    expect(banner?.text).toContain('pinned')
    expect(banner?.text).toContain('live provider configured')
    expect(banner?.text).not.toContain('stand-in')
  })

  it('reserves stand-ins wording for an actually fake pin', () => {
    const banner = describeStoryProvider(
      view({
        pin_state: 'ok',
        pin: {
          profile_id: 'p1',
          revision: 1,
          model_id: 'fake-echo',
          adapter: 'fake',
          connection_name: 'Demo'
        },
        effective_source: 'pin',
        effective_adapter: 'fake',
        effective_model_id: 'fake-echo',
        effective_revision: 1
      }),
      false
    )
    expect(banner?.text).toContain('deterministic stand-ins')
  })

  it('identifies environment defaults explicitly', () => {
    const live = describeStoryProvider(
      view({
        environment: { active_profile: 'openrouter', adapter: 'openrouter', model_id: 'm' },
        effective_source: 'environment',
        effective_adapter: 'openrouter',
        effective_model_id: 'm'
      }),
      false
    )
    expect(live?.text).toContain('environment default')
    expect(live?.text).toContain('live provider configured')

    const fake = describeStoryProvider(view({}), false)
    expect(fake?.text).toContain('environment default')
    expect(fake?.text).toContain('deterministic stand-ins')
  })

  it('reports a broken pin as unavailable, not as a default', () => {
    const banner = describeStoryProvider(
      view({ pin_state: 'broken', pin_error: 'story pins unknown provider profile' }),
      false
    )
    expect(banner?.tone).toBe('error')
    expect(banner?.text).toContain('unavailable')
    expect(banner?.text).not.toContain('environment default')
  })

  it('stays silent while loading and honest when unreachable', () => {
    expect(describeStoryProvider(null, false)).toBeNull()
    const unknown = describeStoryProvider(null, true)
    expect(unknown?.text).toContain('unknown')
  })

  it('labels a retained view last-known after a failed refresh', () => {
    const fresh = describeStoryProvider(view({}), false)
    expect(fresh?.text).not.toContain('Last known')
    const stale = describeStoryProvider(view({}), true)
    expect(stale?.text).toContain('Last known')
    expect(stale?.text).toContain('environment default')
    expect(stale?.text).toContain('could not be refreshed')
  })
})

describe('describeEnvironment', () => {
  it('claims stand-ins only for the fake profile', () => {
    const fake = describeEnvironment('active:fake')
    expect(fake?.text).toContain('Environment default')
    expect(fake?.text).toContain('deterministic stand-ins')
    const live = describeEnvironment('active:openrouter')
    expect(live?.text).toContain('Environment default')
    expect(live?.text).toContain('live provider configured')
    expect(live?.text).not.toContain('stand-in')
    expect(describeEnvironment(null)).toBeNull()
  })
})

describe('beatFallbackNotice', () => {
  it('scopes fallback to the beat whose scenes report it', () => {
    expect(beatFallbackNotice(2, [{ narration: 'narrated' }])).toBeNull()
    expect(beatFallbackNotice(2, undefined)).toBeNull()
    const note = beatFallbackNotice(3, [{ narration: 'narrated' }, { narration: 'fallback' }])
    expect(note).toContain('Beat 3')
    expect(note).toContain('fell back')
  })
})

describe('useStoryProvider', () => {
  it('a late first load never overwrites a newer one', async () => {
    let resolveFirst!: (value: StoryProviderView) => void
    const first = new Promise<StoryProviderView>((res) => {
      resolveFirst = res
    })
    const pinned = view({
      pin_state: 'ok',
      pin: {
        profile_id: 'p1',
        revision: 2,
        model_id: 'live-model',
        adapter: 'openrouter',
        connection_name: 'Live'
      },
      effective_source: 'pin',
      effective_adapter: 'openrouter',
      effective_model_id: 'live-model',
      effective_revision: 2
    })
    let calls = 0
    const client = {
      readStoryProvider(): Promise<StoryProviderView> {
        calls += 1
        return calls === 1 ? first : Promise.resolve(view({}))
      }
    }
    const provider = useStoryProvider('story-a', client)
    const pendingFirst = provider.load()
    await provider.load()
    resolveFirst(pinned)
    await pendingFirst
    expect(provider.banner.value?.text).toContain('environment default')
  })

  it('a failed load renders unknown, and a retry recovers', async () => {
    let fail = true
    const client = {
      readStoryProvider(): Promise<StoryProviderView> {
        return fail ? Promise.reject(new Error('down')) : Promise.resolve(view({}))
      }
    }
    const provider = useStoryProvider('story-a', client)
    await provider.load()
    expect(provider.failed.value).toBe(true)
    expect(provider.banner.value?.text).toContain('unknown')
    fail = false
    await provider.load()
    expect(provider.failed.value).toBe(false)
    expect(provider.banner.value?.text).toContain('environment default')
  })

  it('success, then failure, then recovery labels staleness in between', async () => {
    let mode: 'ok' | 'down' = 'ok'
    const client = {
      readStoryProvider(): Promise<StoryProviderView> {
        return mode === 'ok' ? Promise.resolve(view({})) : Promise.reject(new Error('down'))
      }
    }
    const provider = useStoryProvider('story-a', client)
    await provider.load()
    expect(provider.banner.value?.text).toContain('environment default')
    expect(provider.banner.value?.text).not.toContain('Last known')
    mode = 'down'
    await provider.load()
    expect(provider.failed.value).toBe(true)
    expect(provider.banner.value?.text).toContain('Last known')
    expect(provider.banner.value?.text).toContain('could not be refreshed')
    mode = 'ok'
    await provider.load()
    expect(provider.failed.value).toBe(false)
    expect(provider.banner.value?.text).not.toContain('Last known')
  })
})
