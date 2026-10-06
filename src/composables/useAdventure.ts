import { computed, getCurrentInstance, onUnmounted, ref, type Ref } from 'vue'
import {
  advanceStory,
  getCharacter,
  getChronicle,
  getMap,
  getPresentation,
  getRole,
  getSceneNarration,
  getStory,
  openStory,
  getSuggestions,
  listItems,
  type CallOptions
} from '../api/worldsim'
import type {
  BeatView,
  CharacterDetail,
  ChronicleEntry,
  ChronicleResponse,
  ItemListResponse,
  ItemView,
  MapPlace,
  MapResponse,
  PresentationResponse,
  RoleGrantView,
  Stage1AdvanceResponse,
  StoryDetail,
  SuggestionView
} from '../../content/clients/worldsim'
import type { Role } from '../api/http'
import { buildLog, quickChips, scenesToLoad, waitIntent, type Intent } from '../game/adventure'
import { beatStageLabel, mergeChronicle } from '../game/observatory'

export interface AdventureApi {
  getRole(worldId: string): Promise<RoleGrantView | null>
  getStory(worldId: string, opts: CallOptions): Promise<StoryDetail>
  openStory(worldId: string, opts: CallOptions): Promise<StoryDetail>
  getMap(worldId: string, opts: CallOptions): Promise<MapResponse>
  getPresentation(worldId: string, opts: CallOptions): Promise<PresentationResponse>
  getChronicle(worldId: string, after: number, opts: CallOptions): Promise<ChronicleResponse>
  getSceneNarration(sceneId: string, opts: CallOptions): Promise<BeatView[]>
  getCharacter(characterId: string, opts: CallOptions): Promise<CharacterDetail>
  getSuggestions(characterId: string, opts: CallOptions): Promise<SuggestionView[]>
  listItems(worldId: string, ownerId: string | null, opts: CallOptions): Promise<ItemListResponse>
  advance(
    worldId: string,
    index: number,
    intents: Record<string, Intent>,
    opts: CallOptions
  ): Promise<Stage1AdvanceResponse>
}

const LIVE_API: AdventureApi = {
  getRole: (id) => getRole(id),
  getStory: (id, o) => getStory(id, o),
  openStory: (id, o) => openStory(id, o),
  getMap: (id, o) => getMap(id, o),
  getPresentation: (id, o) => getPresentation(id, o),
  getChronicle: (id, after, o) => getChronicle(id, after, o),
  getSceneNarration: (id, o) => getSceneNarration(id, o),
  getCharacter: (id, o) => getCharacter(id, o),
  getSuggestions: (id, o) => getSuggestions(id, o),
  listItems: (id, owner, o) => listItems(id, owner, o),
  advance: (id, index, intents, o) =>
    advanceStory(id, index, intents as Parameters<typeof advanceStory>[2], o)
}

/** A beat runs every character plus the narrator; live models can take minutes. */
export const ADVANCE_TIMEOUT_MS = 600000
/** While the world answers, how often to read which stage the beat is in. */
export const STAGE_POLL_MS = 1500
/** Between turns: late narration and other players' changes still arrive. */
export const IDLE_POLL_MS = 12000

export interface AdventureOptions {
  api?: AdventureApi
  schedule?: (fn: () => void, ms: number) => () => void
}

const defaultSchedule = (fn: () => void, ms: number): (() => void) => {
  const handle = setTimeout(fn, ms)
  return () => clearTimeout(handle)
}

function message(err: unknown, fallback: string): string {
  return err instanceof Error && err.message ? err.message : fallback
}

/**
 * One player's view of a story: where they are, who is with them, what
 * they carry, and the story so far. `act` sends one action and runs the
 * beat; every other character answers in the same beat.
 */
export function useAdventure(worldId: Ref<string>, options: AdventureOptions = {}) {
  const api = options.api ?? LIVE_API
  const schedule = options.schedule ?? defaultSchedule

  const grant = ref<RoleGrantView | null>(null)
  const title = ref<string | null>(null)
  const places = ref<MapPlace[]>([])
  const presentation = ref<PresentationResponse | null>(null)
  const entries = ref<ChronicleEntry[]>([])
  const beats = ref<Record<string, BeatView[] | undefined>>({})
  const sheet = ref<CharacterDetail | null>(null)
  const items = ref<ItemView[]>([])
  const suggestions = ref<SuggestionView[]>([])
  const loading = ref(true)
  const error = ref<string | null>(null)
  const actionError = ref<string | null>(null)
  const acting = ref(false)
  const runState = ref<string | null>(null)
  let cursor = 0
  let cancelPoll: (() => void) | null = null
  let disposed = false

  const me = computed<string | null>(() =>
    grant.value?.role === 'player' ? (grant.value.character_id ?? null) : null
  )
  const opts = computed<CallOptions>(() => ({
    role: (grant.value?.role as Role | undefined) ?? 'watcher',
    characterId: me.value ?? undefined
  }))
  const cast = computed(() => presentation.value?.cast ?? [])
  const self = computed(() => cast.value.find((c) => c.character_id === me.value) ?? null)
  const hereId = computed(() => self.value?.location_id ?? null)
  const here = computed(() => places.value.find((p) => p.id === hereId.value) ?? null)
  const present = computed(() =>
    cast.value.filter(
      (c) =>
        c.character_id !== me.value && c.location_id === hereId.value && c.life_status === 'alive'
    )
  )
  const anchor = computed(() => {
    const found = (presentation.value?.manifest.anchors ?? []).find(
      (a) => a.location_id === hereId.value
    )
    return found ? { x: Number(found.x), y: Number(found.y) } : null
  })
  const mapAssetId = computed(() => presentation.value?.manifest.asset_id ?? null)
  const log = computed(() =>
    me.value
      ? buildLog({ entries: entries.value, beats: beats.value, me: me.value, hereId: hereId.value })
      : []
  )
  const chips = computed(() => quickChips(suggestions.value))
  const talkable = computed(() => present.value)
  const stage = computed(() => beatStageLabel(runState.value))
  const nextIndex = computed(() => (presentation.value?.absolute_index ?? 0) + 1)
  const alive = computed(() => (self.value?.life_status ?? 'alive') === 'alive')

  async function readChronicle(): Promise<void> {
    // Re-read from the first scene still waiting for its words, so late
    // narration replaces "still being written" without a reload.
    const pending = entries.value.find((e) => e.scene_id && !e.text)
    let after = pending ? Math.min(cursor, pending.sequence - 1) : cursor
    for (let page = 0; page < 20; page++) {
      const res = await api.getChronicle(worldId.value, after, opts.value)
      entries.value = mergeChronicle(entries.value, res.entries ?? [])
      after = res.next_after
      cursor = Math.max(cursor, after)
      if (!res.has_more) return
    }
  }

  async function readNarration(): Promise<void> {
    if (!me.value) return
    const wanted = scenesToLoad({
      entries: entries.value,
      beats: beats.value,
      me: me.value,
      hereId: hereId.value
    })
    const loaded = await Promise.allSettled(
      wanted.map(async (id) => [id, await api.getSceneNarration(id, opts.value)] as const)
    )
    const next = { ...beats.value }
    for (const result of loaded) {
      if (result.status === 'fulfilled') next[result.value[0]] = result.value[1]
    }
    beats.value = next
  }

  async function readSelf(): Promise<void> {
    if (!me.value) return
    const [detail, owned, offered] = await Promise.allSettled([
      api.getCharacter(me.value, opts.value),
      api.listItems(worldId.value, me.value, opts.value),
      api.getSuggestions(me.value, opts.value)
    ])
    if (detail.status === 'fulfilled') sheet.value = detail.value
    if (owned.status === 'fulfilled') items.value = owned.value.members ?? []
    if (offered.status === 'fulfilled') suggestions.value = offered.value
  }

  async function refreshPlacesIfNew(view: PresentationResponse): Promise<void> {
    const known = new Set(places.value.map((p) => p.id))
    if (!(view.manifest.anchors ?? []).some((a) => !known.has(a.location_id))) return
    try {
      places.value = (await api.getMap(worldId.value, opts.value)).places ?? places.value
    } catch {
      // Keep the old names; the next refresh tries again.
    }
  }

  async function refresh(): Promise<void> {
    try {
      const view = await api.getPresentation(worldId.value, opts.value)
      presentation.value = view
      runState.value = view.run_state ?? null
      await refreshPlacesIfNew(view)
      await readChronicle()
      await Promise.all([readNarration(), readSelf()])
      error.value = null
    } catch (err) {
      error.value = message(err, 'Could not reach the world.')
    }
  }

  function planPoll(): void {
    cancelPoll?.()
    if (disposed) return
    cancelPoll = schedule(
      () => {
        if (acting.value) {
          // During a turn only the beat's stage is read; the turn refreshes at its end.
          void api
            .getPresentation(worldId.value, opts.value)
            .then((view) => (runState.value = view.run_state ?? null))
            .catch(() => undefined)
            .finally(planPoll)
        } else {
          void refresh().then(planPoll)
        }
      },
      acting.value ? STAGE_POLL_MS : IDLE_POLL_MS
    )
  }

  async function load(): Promise<void> {
    loading.value = true
    entries.value = []
    beats.value = {}
    cursor = 0
    try {
      grant.value = await api.getRole(worldId.value)
    } catch {
      grant.value = null
    }
    // Opening records the visit, so the shelf and home list it as just played.
    const [story, map] = await Promise.allSettled([
      api.openStory(worldId.value, opts.value),
      api.getMap(worldId.value, opts.value)
    ])
    title.value = story.status === 'fulfilled' ? story.value.title : null
    places.value = map.status === 'fulfilled' ? (map.value.places ?? []) : []
    await refresh()
    loading.value = false
    planPoll()
  }

  /** Send one action and run the beat; every character answers in it. */
  async function act(intent: Intent): Promise<boolean> {
    if (!me.value || acting.value) return false
    acting.value = true
    actionError.value = null
    runState.value = 'created'
    planPoll()
    try {
      // A beat runs every character and the narrator: give it minutes, not seconds.
      await api.advance(
        worldId.value,
        nextIndex.value,
        { [me.value]: intent },
        { ...opts.value, timeoutMs: ADVANCE_TIMEOUT_MS }
      )
      return true
    } catch (err) {
      const text = message(err, '')
      actionError.value = /timed out/i.test(text)
        ? 'The world is slow to answer — the turn keeps going and will appear here when it is done.'
        : text || 'The world could not answer that. Try something else.'
      return false
    } finally {
      acting.value = false
      runState.value = null
      await refresh()
      planPoll()
    }
  }

  function wait(): Promise<boolean> {
    return me.value ? act(waitIntent(me.value)) : Promise.resolve(false)
  }

  function dispose(): void {
    disposed = true
    cancelPoll?.()
  }

  if (getCurrentInstance()) onUnmounted(dispose)

  return {
    grant,
    me,
    title,
    places,
    presentation,
    entries,
    beats,
    sheet,
    items,
    suggestions,
    loading,
    error,
    actionError,
    acting,
    runState,
    stage,
    self,
    hereId,
    here,
    present,
    talkable,
    anchor,
    mapAssetId,
    log,
    chips,
    alive,
    load,
    refresh,
    act,
    wait,
    dispose
  }
}
