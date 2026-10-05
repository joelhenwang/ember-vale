import { computed, getCurrentInstance, onUnmounted, ref, type Ref } from 'vue'
import {
  getAutoplay,
  getChronicle,
  getMap,
  getPresentation,
  getRole,
  getStory,
  pauseAutoplay,
  playAutoplay,
  reportPresence,
  type CallOptions
} from '../api/worldsim'
import type {
  AutoplayPlayRequest,
  AutoplayView,
  ChronicleEntry,
  ChronicleResponse,
  MapPlace,
  MapResponse,
  PresentationResponse,
  RoleGrantView,
  StoryDetail
} from '../../content/clients/worldsim'
import type { Role } from '../api/http'
import { groupFeed, layoutTokens, mergeChronicle } from '../game/observatory'

export interface ObservatoryApi {
  getRole(worldId: string): Promise<RoleGrantView | null>
  getStory(worldId: string, opts: CallOptions): Promise<StoryDetail>
  getMap(worldId: string, opts: CallOptions): Promise<MapResponse>
  getPresentation(worldId: string, opts: CallOptions): Promise<PresentationResponse>
  getChronicle(worldId: string, after: number, opts: CallOptions): Promise<ChronicleResponse>
  getAutoplay(worldId: string, opts: CallOptions): Promise<AutoplayView>
  playAutoplay(worldId: string, body: AutoplayPlayRequest, opts: CallOptions): Promise<AutoplayView>
  pauseAutoplay(worldId: string, opts: CallOptions): Promise<AutoplayView>
  reportPresence(worldId: string, opts: CallOptions): Promise<AutoplayView>
}

const LIVE_API: ObservatoryApi = {
  getRole: (id) => getRole(id),
  getStory: (id, o) => getStory(id, o),
  getMap: (id, o) => getMap(id, o),
  getPresentation: (id, o) => getPresentation(id, o),
  getChronicle: (id, after, o) => getChronicle(id, after, o),
  getAutoplay: (id, o) => getAutoplay(id, o),
  playAutoplay: (id, body, o) => playAutoplay(id, body, o),
  pauseAutoplay: (id, o) => pauseAutoplay(id, o),
  reportPresence: (id, o) => reportPresence(id, o)
}

/** How often to re-read the world: quickly while something is happening. */
export const ACTIVE_POLL_MS = 2000
export const IDLE_POLL_MS = 15000
/** Presence well inside the server's grace period (60 s). */
export const PRESENCE_MS = 20000

export interface ObservatoryOptions {
  api?: ObservatoryApi
  /** Injectable timer for tests; returns a cancel function. */
  schedule?: (fn: () => void, ms: number) => () => void
  /** Whether the page is visible (presence only counts a looking viewer). */
  visible?: () => boolean
}

function message(err: unknown, fallback: string): string {
  return err instanceof Error && err.message ? err.message : fallback
}

const defaultSchedule = (fn: () => void, ms: number): (() => void) => {
  const handle = setTimeout(fn, ms)
  return () => clearTimeout(handle)
}

/**
 * The observatory's live view of one story: map projection, chronicle
 * feed and server-side autoplay. Polls faster while autoplay plays or a
 * beat is open, and reports presence while the page is visible so the
 * server keeps playing only for someone who is watching.
 */
export function useObservatory(worldId: Ref<string>, options: ObservatoryOptions = {}) {
  const api = options.api ?? LIVE_API
  const schedule = options.schedule ?? defaultSchedule
  const visible =
    options.visible ??
    (() => typeof document === 'undefined' || document.visibilityState === 'visible')

  const grant = ref<RoleGrantView | null>(null)
  const title = ref<string | null>(null)
  /** Place names and routes; geography is fixed for a story, read once. */
  const places = ref<MapPlace[]>([])
  const presentation = ref<PresentationResponse | null>(null)
  const entries = ref<ChronicleEntry[]>([])
  const autoplay = ref<AutoplayView | null>(null)
  const loading = ref(true)
  const error = ref<string | null>(null)
  const actionError = ref<string | null>(null)
  const acting = ref(false)
  let cursor = 0
  let cancelPoll: (() => void) | null = null
  let cancelPresence: (() => void) | null = null
  let disposed = false

  const role = computed<Role>(() => (grant.value?.role as Role | undefined) ?? 'watcher')
  const opts = computed<CallOptions>(() => ({
    role: role.value,
    characterId: grant.value?.character_id ?? undefined
  }))
  /** Autoplay runs the whole cast, so Player stories only watch. */
  const canOperate = computed(
    () =>
      role.value !== 'player' &&
      (presentation.value?.capabilities.capabilities ?? []).includes('advance')
  )
  const beatOpen = computed(() => Boolean(presentation.value?.open_run_id))
  const playing = computed(() => autoplay.value?.status === 'playing')
  const tokens = computed(() =>
    presentation.value
      ? layoutTokens(presentation.value.manifest.anchors ?? [], presentation.value.cast ?? [])
      : []
  )
  const feed = computed(() => groupFeed(entries.value))

  async function readChronicle(): Promise<void> {
    for (let page = 0; page < 20; page++) {
      const res = await api.getChronicle(worldId.value, cursor, opts.value)
      entries.value = mergeChronicle(entries.value, res.entries ?? [])
      cursor = res.next_after
      if (!res.has_more) return
    }
  }

  async function refresh(): Promise<void> {
    try {
      const [view, state] = await Promise.all([
        api.getPresentation(worldId.value, opts.value),
        api.getAutoplay(worldId.value, opts.value)
      ])
      presentation.value = view
      autoplay.value = state
      await readChronicle()
      error.value = null
    } catch (err) {
      error.value = message(err, 'Could not reach the world.')
    }
  }

  function planPoll(): void {
    cancelPoll?.()
    if (disposed) return
    const ms = playing.value || beatOpen.value ? ACTIVE_POLL_MS : IDLE_POLL_MS
    cancelPoll = schedule(() => {
      void refresh().then(planPoll)
    }, ms)
  }

  async function sendPresence(): Promise<void> {
    if (visible() && playing.value) {
      try {
        autoplay.value = await api.reportPresence(worldId.value, opts.value)
      } catch {
        // The next refresh shows the outcome; presence is best effort.
      }
    }
  }

  function planPresence(): void {
    cancelPresence?.()
    if (disposed) return
    cancelPresence = schedule(() => {
      void sendPresence().then(planPresence)
    }, PRESENCE_MS)
  }

  async function load(): Promise<void> {
    loading.value = true
    entries.value = []
    cursor = 0
    try {
      grant.value = await api.getRole(worldId.value)
    } catch {
      grant.value = null
    }
    const [story, map] = await Promise.allSettled([
      api.getStory(worldId.value, opts.value),
      api.getMap(worldId.value, opts.value)
    ])
    title.value = story.status === 'fulfilled' ? story.value.title : null
    places.value = map.status === 'fulfilled' ? (map.value.places ?? []) : []
    await refresh()
    loading.value = false
    planPoll()
    planPresence()
  }

  async function act(run: () => Promise<AutoplayView>, fallback: string): Promise<void> {
    acting.value = true
    actionError.value = null
    try {
      autoplay.value = await run()
      await refresh()
      planPoll()
    } catch (err) {
      actionError.value = message(err, fallback)
    } finally {
      acting.value = false
    }
  }

  function play(delaySeconds: number, beatLimit: number): Promise<void> {
    return act(
      () =>
        api.playAutoplay(
          worldId.value,
          { delay_seconds: delaySeconds, beat_limit: beatLimit },
          opts.value
        ),
      'Could not start autoplay.'
    )
  }

  /** One beat, run by the server like autoplay, so closing the tab is safe. */
  function step(): Promise<void> {
    return act(
      () => api.playAutoplay(worldId.value, { delay_seconds: 0, beat_limit: 1 }, opts.value),
      'Could not start the beat.'
    )
  }

  function pause(): Promise<void> {
    return act(() => api.pauseAutoplay(worldId.value, opts.value), 'Could not pause.')
  }

  /** Call when the page becomes visible again: report presence at once. */
  function onVisible(): void {
    void sendPresence()
    void refresh().then(planPoll)
  }

  function dispose(): void {
    disposed = true
    cancelPoll?.()
    cancelPresence?.()
  }

  if (getCurrentInstance()) onUnmounted(dispose)

  return {
    grant,
    title,
    places,
    role,
    presentation,
    entries,
    autoplay,
    loading,
    error,
    actionError,
    acting,
    canOperate,
    beatOpen,
    playing,
    tokens,
    feed,
    load,
    refresh,
    play,
    step,
    pause,
    onVisible,
    dispose
  }
}
