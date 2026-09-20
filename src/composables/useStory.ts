/**
 * One story's live state for the story room (C4).
 *
 * Identity comes from the persisted grant (GET /stage2/roles), never from
 * matching display names: the grant's character_id is a runtime id matched
 * directly against map occupant ids. The feed pages through the server
 * cursor (next_after/has_more) instead of re-reading page one. Advance uses
 * the next absolute index; a timeout retries the SAME index (the server
 * replays). Travel reconciles the activity list (members) on 409/timeout
 * instead of claiming a journey is underway. Every state update is guarded
 * by the story lifecycle generation so late responses for a previous story
 * are ignored; mutations stay pending through acknowledgement and refresh.
 */

import { computed, ref, unref, type Ref } from 'vue'
import type {
  ActivityView,
  MapResponse,
  RoleGrantView,
  StoryDetail,
  StorySetupView,
  TimelineEntry
} from '../../content/clients/worldsim'
import { ApiError, type Role } from '../api/http'
import {
  advanceStory,
  getMap,
  getRole,
  getSetup,
  getStory,
  getTimeline,
  listActivities,
  openStory,
  startTravel
} from '../api/worldsim'

export interface StoryNotice {
  kind: 'error' | 'info'
  text: string
}

/** Bounded full-history fetch: 25 pages of 50 source events. */
const MAX_PAGES = 25
const PAGE_LIMIT = 50

export function useStory(
  storyId: string | Ref<string>,
  role: Role | Ref<Role>,
  characterId?: string | Ref<string | undefined>
) {
  const detail = ref<StoryDetail | null>(null)
  const setup = ref<StorySetupView | null>(null)
  const grant = ref<RoleGrantView | null>(null)
  const grantLoaded = ref(false)
  const entries = ref<TimelineEntry[]>([])
  const cursor = ref(0)
  const hasMore = ref(false)
  const total = ref(0)
  const map = ref<MapResponse | null>(null)
  const loading = ref(true)
  const loadError = ref<string | null>(null)
  const advancing = ref(false)
  const traveling = ref(false)
  const notice = ref<StoryNotice | null>(null)
  const openedFor = ref<string | null>(null)

  let cycle = 0
  let controller: AbortController | null = null

  const id = (): string => unref(storyId)

  const opts = (): { role: Role; characterId?: string; signal?: AbortSignal } => ({
    role: unref(role),
    characterId: unref(characterId),
    signal: controller?.signal
  })

  /** Authoritative controlled runtime id: grant first, setup snapshot second. */
  const controlledRuntimeId = computed<string | null>(() => {
    if (grant.value?.role === 'player' && grant.value.character_id) {
      return grant.value.character_id
    }
    const payload = setup.value?.payload as unknown as
      { mode?: { role?: string; controlled_character_id?: string | null } } | undefined
    if (payload?.mode?.role === 'player' && payload.mode.controlled_character_id) {
      return payload.mode.controlled_character_id
    }
    return null
  })

  /** The actual mode: persisted grant wins over headers, like the backend. */
  const effectiveRole = computed<Role>(() => {
    if (grant.value && grant.value.role !== 'director' && grant.value.role !== 'deity') {
      return grant.value.role as Role
    }
    return detail.value?.mode === 'player' ? 'player' : 'watcher'
  })

  const occupantsByPlace = computed(() => {
    const out = new Map<string, { name: string; places: string[] }>()
    for (const place of map.value?.places ?? []) {
      for (let i = 0; i < (place.occupant_ids?.length ?? 0); i += 1) {
        const oid = place.occupant_ids?.[i]
        const name = place.occupants?.[i]
        if (!oid || !name) continue
        const row = out.get(oid) ?? { name, places: [] }
        row.places.push(place.name)
        out.set(oid, row)
      }
    }
    return out
  })

  function mergeEntries(page: TimelineEntry[]): void {
    const seen = new Set(entries.value.map((e) => e.event_id))
    for (const entry of page ?? []) {
      if (!seen.has(entry.event_id)) {
        seen.add(entry.event_id)
        entries.value.push(entry)
      }
    }
  }

  /** Page from `after` to exhaustion, following next_after unconditionally. */
  async function pageThrough(
    seen: number,
    header: { role: Role; characterId?: string; signal?: AbortSignal },
    after: number
  ): Promise<void> {
    let next = after
    let more = false
    for (let pages = 0; pages < MAX_PAGES; pages += 1) {
      const timeline = await getTimeline(id(), next, header, PAGE_LIMIT)
      if (seen !== cycle) return
      mergeEntries(timeline.entries ?? [])
      total.value = timeline.total
      next = timeline.next_after
      more = timeline.has_more
      if (!more) break
    }
    cursor.value = next
    hasMore.value = more
  }

  async function load(): Promise<void> {
    cycle += 1
    const seen = cycle
    controller?.abort()
    controller = new AbortController()
    loading.value = true
    loadError.value = null
    entries.value = []
    cursor.value = 0
    grant.value = null
    grantLoaded.value = false
    try {
      const [story, initialSetup, activeGrant, worldMap] = await Promise.all([
        getStory(id(), opts()),
        getSetup(id(), opts()),
        getRole(id(), opts()),
        getMap(id(), opts())
      ])
      if (seen !== cycle) return
      detail.value = story
      setup.value = initialSetup
      grant.value = activeGrant
      grantLoaded.value = true
      map.value = worldMap
      await pageThrough(seen, opts(), 0)
      if (seen !== cycle) return
      // Record the room open (updates last_played_at) without advancing
      // gameplay. Best-effort: a failure leaves stale metadata, honestly so.
      if (openedFor.value !== id()) {
        try {
          const reopened = await openStory(id(), opts())
          if (seen === cycle) {
            detail.value = reopened
            openedFor.value = id()
          }
        } catch {
          /* last_played_at stays as-is */
        }
      }
    } catch (err) {
      if (seen !== cycle) return
      if (err instanceof ApiError && err.cancelled) return
      loadError.value = err instanceof Error ? err.message : 'could not load the story'
    } finally {
      if (seen === cycle) loading.value = false
    }
  }

  function cancel(): void {
    cycle += 1
    controller?.abort()
    controller = null
  }

  async function refreshTimeline(full = false): Promise<void> {
    if (!detail.value) return
    const seen = cycle
    try {
      const header = { role: unref(role), characterId: unref(characterId) }
      if (full) {
        entries.value = []
        await pageThrough(seen, header, 0)
      } else {
        await pageThrough(seen, header, cursor.value)
      }
      if (seen !== cycle) return
      const [story, worldMap] = await Promise.all([getStory(id(), header), getMap(id(), header)])
      if (seen !== cycle) return
      detail.value = story
      map.value = worldMap
    } catch (err) {
      if (seen !== cycle) return
      if (err instanceof ApiError && err.cancelled) return
      notice.value = {
        kind: 'error',
        text: err instanceof Error ? err.message : 'could not refresh'
      }
    }
  }

  async function advance(): Promise<boolean> {
    if (!detail.value || advancing.value) return false
    advancing.value = true
    notice.value = null
    const seen = cycle
    const index = detail.value.absolute_index + 1
    const header = { role: unref(role), characterId: unref(characterId) }
    const attempt = async (): Promise<void> => {
      const result = await advanceStory(id(), index, undefined, header)
      if (seen === cycle && result.duplicate) {
        notice.value = { kind: 'info', text: 'That beat already committed — showing it.' }
      }
    }
    try {
      await attempt()
    } catch (err) {
      if (err instanceof ApiError && err.code === 'REQUEST_TIMEOUT') {
        // Same index retry: the server replays a committed beat.
        try {
          await attempt()
        } catch (retryErr) {
          if (seen === cycle) {
            notice.value = {
              kind: 'error',
              text: retryErr instanceof Error ? retryErr.message : 'advance timed out'
            }
          }
          return false
        }
      } else if (err instanceof ApiError && err.code === 'VERSION_CONFLICT') {
        if (seen === cycle)
          notice.value = { kind: 'info', text: 'Newer state arrived — refreshed.' }
      } else {
        if (seen === cycle) {
          notice.value = {
            kind: 'error',
            text: err instanceof Error ? err.message : 'could not advance'
          }
        }
        return false
      }
    } finally {
      // Stay pending through acknowledgement AND reconciliation refresh so
      // no second beat starts against stale displayed state.
      if (seen === cycle) {
        await refreshTimeline()
        advancing.value = false
      }
    }
    return seen === cycle
  }

  function matchActivity(
    members: ActivityView[] | undefined,
    characterId_: string,
    toLocationId: string
  ): { mine: boolean; elsewhere: boolean } {
    let elsewhere = false
    for (const activity of members ?? []) {
      if (activity.character_id !== characterId_) continue
      if (activity.kind !== 'travel' || activity.status !== 'active') continue
      if (activity.to_location_id === toLocationId) return { mine: true, elsewhere: false }
      elsewhere = true
    }
    return { mine: false, elsewhere }
  }

  async function reconcileTravel(
    seen: number,
    header: { role: Role; characterId?: string; signal?: AbortSignal },
    characterId_: string,
    toLocationId: string,
    failure: string
  ): Promise<void> {
    try {
      const active = await listActivities(id(), header)
      if (seen !== cycle) return
      const { mine, elsewhere } = matchActivity(active.members, characterId_, toLocationId)
      notice.value = {
        kind: mine || elsewhere ? 'info' : 'error',
        text: mine
          ? 'That journey is already underway — advance the story to complete it.'
          : elsewhere
            ? 'This character already has a journey underway elsewhere.'
            : failure
      }
    } catch {
      if (seen === cycle) notice.value = { kind: 'error', text: failure }
    }
  }

  async function travel(characterId_: string, toLocationId: string): Promise<boolean> {
    if (traveling.value) return false
    traveling.value = true
    notice.value = null
    const seen = cycle
    const header = {
      role: unref(role),
      characterId: unref(characterId),
      signal: controller?.signal
    }
    try {
      await startTravel(id(), characterId_, toLocationId, header)
      if (seen === cycle) {
        notice.value = {
          kind: 'info',
          text: 'Journey begun — advance the story to complete it.'
        }
      }
      return seen === cycle
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        // 409 covers underway journeys AND other preconditions (no route,
        // busy character): reconcile instead of assuming underway.
        await reconcileTravel(
          seen,
          header,
          characterId_,
          toLocationId,
          err.message || 'could not start the journey'
        )
        return false
      }
      if (err instanceof ApiError && err.code === 'REQUEST_TIMEOUT') {
        // No idempotency key on this route: reconcile before reporting, so a
        // committed-but-unacknowledged start is not retried blindly.
        await reconcileTravel(
          seen,
          header,
          characterId_,
          toLocationId,
          'the journey request timed out — check the cast before retrying'
        )
        return false
      }
      if (seen === cycle) {
        if (err instanceof ApiError && err.cancelled) return false
        notice.value = {
          kind: 'error',
          text: err instanceof Error ? err.message : 'could not start the journey'
        }
      }
      return false
    } finally {
      if (seen === cycle) traveling.value = false
    }
  }

  return {
    detail,
    setup,
    grant,
    grantLoaded,
    controlledRuntimeId,
    effectiveRole,
    entries,
    cursor,
    hasMore,
    total,
    map,
    occupantsByPlace,
    loading,
    loadError,
    advancing,
    traveling,
    notice,
    load,
    cancel,
    advance,
    travel,
    refreshTimeline
  }
}
