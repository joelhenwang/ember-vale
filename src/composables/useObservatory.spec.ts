import { describe, expect, it } from 'vitest'
import { ref } from 'vue'
import type {
  AutoplayView,
  ChronicleEntry,
  PresentationResponse,
  RoleGrantView
} from '../../content/clients/worldsim'
import {
  ACTIVE_POLL_MS,
  IDLE_POLL_MS,
  PRESENCE_MS,
  useObservatory,
  type ObservatoryApi
} from './useObservatory'

function presentation(over: Partial<PresentationResponse> = {}): PresentationResponse {
  return {
    world_id: 'w',
    day: 1,
    phase: 'noon',
    absolute_index: 3,
    revision: 3,
    capabilities: { role: 'watcher', capabilities: ['advance', 'read_world'] },
    manifest: {
      id: 'm',
      version: 1,
      schematic: false,
      anchors: [{ location_id: 'hearth', x: 0.2, y: 0.3 }]
    },
    cast: [{ character_id: 'wren', name: 'Wren', location_id: 'hearth', life_status: 'alive' }],
    ...over
  }
}

function autoplay(over: Partial<AutoplayView> = {}): AutoplayView {
  return {
    world_id: 'w',
    status: 'paused',
    delay_seconds: 0,
    beats_left: 0,
    beats_run: 0,
    runner_enabled: true,
    version: 0,
    ...over
  }
}

const event = (seq: number, index: number): ChronicleEntry => ({
  sequence: seq,
  absolute_index: index,
  event_id: `e${seq}`,
  event_type: 'action_resolved',
  title: `scene ${seq}`
})

/** In-memory backend: records calls, serves chronicle pages from a list. */
function fakeApi(opts: { grant?: RoleGrantView | null; events?: ChronicleEntry[] } = {}) {
  const calls: string[] = []
  let state = autoplay()
  let view = presentation()
  const events = opts.events ?? [event(1, 1), event(2, 2), event(3, 3)]
  const api: ObservatoryApi = {
    async getRole() {
      return opts.grant ?? null
    },
    async getStory() {
      return { title: 'Ember Vale' } as Awaited<ReturnType<ObservatoryApi['getStory']>>
    },
    async getMap() {
      return {
        world_id: 'w',
        places: [{ id: 'hearth', name: 'Hearth', region: '', discovered: true }]
      }
    },
    async getPresentation(_w, o) {
      calls.push(`presentation:${o.role}`)
      return view
    },
    async getChronicle(_w, after) {
      calls.push(`chronicle:${after}`)
      const page = events.filter((e) => e.sequence > after).slice(0, 2)
      const last = page.length ? page[page.length - 1].sequence : after
      return {
        world_id: 'w',
        entries: page,
        next_after: last,
        has_more: events.some((e) => e.sequence > last),
        watermark: events.length
      }
    },
    async getAutoplay() {
      return state
    },
    async playAutoplay(_w, body) {
      calls.push(`play:${body.delay_seconds}:${body.beat_limit}`)
      state = autoplay({
        status: 'playing',
        delay_seconds: body.delay_seconds ?? 0,
        beats_left: body.beat_limit ?? 10
      })
      return state
    },
    async pauseAutoplay() {
      calls.push('pause')
      state = autoplay({ stop_reason: 'user' })
      return state
    },
    async reportPresence() {
      calls.push('presence')
      return state
    }
  }
  return {
    api,
    calls,
    setView: (v: PresentationResponse) => (view = v)
  }
}

/** Timer stand-in: remembers scheduled callbacks so a test runs them. */
function fakeTimers() {
  const pending: { fn: () => void; ms: number; cancelled: boolean }[] = []
  return {
    schedule(fn: () => void, ms: number) {
      const item = { fn, ms, cancelled: false }
      pending.push(item)
      return () => {
        item.cancelled = true
      }
    },
    live: () => pending.filter((p) => !p.cancelled),
    run(ms: number) {
      for (const p of pending.filter((x) => !x.cancelled && x.ms === ms)) {
        p.cancelled = true
        p.fn()
      }
    }
  }
}

const flush = () => new Promise((r) => setTimeout(r, 0))

describe('useObservatory', () => {
  it('loads the map projection and pages the whole chronicle', async () => {
    const { api, calls } = fakeApi()
    const timers = fakeTimers()
    const obs = useObservatory(ref('w'), { api, schedule: timers.schedule, visible: () => true })
    await obs.load()

    expect(obs.tokens.value.map((t) => t.name)).toEqual(['Wren'])
    expect(obs.feed.value.map((b) => b.index)).toEqual([3, 2, 1])
    expect(calls.filter((c) => c.startsWith('chronicle'))).toEqual(['chronicle:0', 'chronicle:2'])
    expect(obs.canOperate.value).toBe(true)
    expect(obs.title.value).toBe('Ember Vale')
    expect(obs.places.value.map((p) => p.name)).toEqual(['Hearth'])
  })

  it('polls slowly when idle and quickly once playing', async () => {
    const { api } = fakeApi()
    const timers = fakeTimers()
    const obs = useObservatory(ref('w'), { api, schedule: timers.schedule, visible: () => true })
    await obs.load()
    expect(timers.live().map((t) => t.ms)).toContain(IDLE_POLL_MS)

    await obs.play(15, 10)
    expect(timers.live().map((t) => t.ms)).toContain(ACTIVE_POLL_MS)
    expect(timers.live().map((t) => t.ms)).not.toContain(IDLE_POLL_MS)
  })

  it('step asks the server for exactly one beat', async () => {
    const { api, calls } = fakeApi()
    const obs = useObservatory(ref('w'), { api, schedule: fakeTimers().schedule })
    await obs.load()
    await obs.step()
    expect(calls).toContain('play:0:1')
  })

  it('reports presence only while playing and visible', async () => {
    const { api, calls } = fakeApi()
    const timers = fakeTimers()
    let shown = true
    const obs = useObservatory(ref('w'), {
      api,
      schedule: timers.schedule,
      visible: () => shown
    })
    await obs.load()
    timers.run(PRESENCE_MS)
    await flush()
    expect(calls).not.toContain('presence') // paused: nothing to keep alive

    await obs.play(0, 5)
    shown = false
    timers.run(PRESENCE_MS)
    await flush()
    expect(calls).not.toContain('presence') // hidden tab: let the grace period lapse

    shown = true
    timers.run(PRESENCE_MS)
    await flush()
    expect(calls).toContain('presence')
  })

  it('a Player story can watch but not operate autoplay', async () => {
    const { api, calls } = fakeApi({
      grant: {
        id: 'g',
        world_id: 'w',
        role: 'player',
        character_id: 'wren',
        granted_absolute: 0,
        version: 0
      }
    })
    const obs = useObservatory(ref('w'), { api, schedule: fakeTimers().schedule })
    await obs.load()
    expect(obs.canOperate.value).toBe(false)
    expect(calls).toContain('presentation:player')
  })

  it('surfaces action failures without dropping the view', async () => {
    const { api } = fakeApi()
    api.pauseAutoplay = async () => {
      throw new Error('autoplay is for watching')
    }
    const obs = useObservatory(ref('w'), { api, schedule: fakeTimers().schedule })
    await obs.load()
    await obs.pause()
    expect(obs.actionError.value).toBe('autoplay is for watching')
    expect(obs.presentation.value).not.toBeNull()
  })

  it('keeps the first-seen time of an open beat while its stage advances', async () => {
    const { api, setView } = fakeApi()
    let clock = 1_000
    const obs = useObservatory(ref('w'), {
      api,
      schedule: fakeTimers().schedule,
      now: () => clock
    })
    setView(presentation({ open_run_id: 'r1', run_state: 'snapshot_sealed' }))
    await obs.load()
    expect(obs.openBeat.value).toEqual({ state: 'snapshot_sealed', seenAtMs: 1_000 })

    clock = 9_000
    setView(presentation({ open_run_id: 'r1', run_state: 'intents_complete' }))
    await obs.refresh()
    expect(obs.openBeat.value).toEqual({ state: 'intents_complete', seenAtMs: 1_000 })

    setView(presentation({ open_run_id: 'r2', run_state: 'created' }))
    await obs.refresh()
    expect(obs.openBeat.value?.seenAtMs).toBe(9_000)

    setView(presentation())
    await obs.refresh()
    expect(obs.openBeat.value).toBeNull()
    expect(obs.beatOpen.value).toBe(false)
  })

  it('re-reads place names when the world gains a place', async () => {
    const { api, setView } = fakeApi()
    let mapReads = 0
    const placesNow = [{ id: 'hearth', name: 'Hearth', region: '', discovered: true }]
    api.getMap = async () => {
      mapReads += 1
      return { world_id: 'w', places: [...placesNow] }
    }
    const obs = useObservatory(ref('w'), { api, schedule: fakeTimers().schedule })
    await obs.load()
    await obs.refresh()
    expect(mapReads).toBe(1) // nothing new: no extra read

    placesNow.push({ id: 'forge', name: 'Old Forge', region: '', discovered: true })
    setView(
      presentation({
        manifest: {
          id: 'm',
          version: 1,
          schematic: false,
          anchors: [
            { location_id: 'hearth', x: 0.2, y: 0.3 },
            { location_id: 'forge', x: 0.3, y: 0.4 }
          ]
        }
      })
    )
    await obs.refresh()
    expect(mapReads).toBe(2)
    expect(obs.places.value.map((p) => p.name)).toEqual(['Hearth', 'Old Forge'])
  })

  it('stops scheduling after dispose', async () => {
    const { api } = fakeApi()
    const timers = fakeTimers()
    const obs = useObservatory(ref('w'), { api, schedule: timers.schedule })
    await obs.load()
    obs.dispose()
    expect(timers.live()).toEqual([])
  })
})
