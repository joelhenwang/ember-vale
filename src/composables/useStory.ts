/**
 * One story's live state for the story room (C4).
 *
 * Identity comes from the persisted grant (GET /stage2/roles), never from
 * matching display names: the grant's character_id is a runtime id matched
 * directly against map occupant ids. The feed pages through the server
 * cursor (next_after/has_more) instead of re-reading page one. Advance uses
 * the next absolute index; a timeout retries the SAME index (the server
 * replays). Travel reconciles the activity list (members) on 409/timeout
 * instead of claiming a journey is underway. Mutations freeze an immutable
 * operation context (world, target, role, actor, generation) at start:
 * attempts, retries and reconciliation never re-read the reactive route
 * id, and a timeout never retries after the lifecycle moved on. History
 * continues explicitly from the stored cursor via loadMore().
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

/** Bounded history fetch: 25 pages of 50 source events per continuation. */
const MAX_PAGES = 25
const PAGE_LIMIT = 50

interface OpHeader {
  role: Role
  characterId?: string
  signal?: AbortSignal
}

/**
 * Immutable mutation context frozen at operation start. Every attempt and
 * reconciliation request uses these values — never the reactive route id —
 * so a response held across navigation cannot be retried into another
 * world. `generation` ties the operation to its lifecycle: only the
 * originating cycle may retry or reconcile it.
 */
interface AdvanceOp {
  worldId: string
  index: number
  header: OpHeader
  /** Player attempt filed with this beat; omitted beats carry none. */
  intents?: Parameters<typeof advanceStory>[2]
  generation: number
}

interface TravelOp {
  worldId: string
  actorId: string
  toLocationId: string
  header: OpHeader
  generation: number
}

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
  const loadingMore = ref(false)
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

  function mergeEntries(page: TimelineEntry[]): number {
    const seen = new Set(entries.value.map((e) => e.event_id))
    let added = 0
    for (const entry of page ?? []) {
      if (!seen.has(entry.event_id)) {
        seen.add(entry.event_id)
        entries.value.push(entry)
        added += 1
      }
    }
    return added
  }

  /**
   * Page from `after` toward exhaustion for one fixed world. Follows
   * next_after even across role-filtered empty pages, but stops when the
   * cursor stops progressing with nothing new — a stuck cursor must not
   * spin, and the user continues explicitly via loadMore().
   */
  async function pageThrough(
    worldId: string,
    seen: number,
    header: OpHeader,
    after: number
  ): Promise<void> {
    let next = after
    let more = false
    let idleRounds = 0
    for (let pages = 0; pages < MAX_PAGES; pages += 1) {
      const timeline = await getTimeline(worldId, next, header, PAGE_LIMIT)
      if (seen !== cycle) return
      const added = mergeEntries(timeline.entries ?? [])
      total.value = timeline.total
      if (timeline.next_after === next && added === 0) {
        idleRounds += 1
        if (idleRounds >= 2) {
          more = timeline.has_more
          break
        }
      } else {
        idleRounds = 0
      }
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
    // A new lifecycle owns all mutation state: nothing stays pending from
    // a cancelled operation on a reused instance.
    advancing.value = false
    traveling.value = false
    loadingMore.value = false
    loading.value = true
    loadError.value = null
    entries.value = []
    cursor.value = 0
    hasMore.value = false
    grant.value = null
    grantLoaded.value = false
    // Frozen for this load: a route change mid-load must not retarget reads.
    const worldId = id()
    try {
      const [story, initialSetup, activeGrant, worldMap] = await Promise.all([
        getStory(worldId, opts()),
        getSetup(worldId, opts()),
        getRole(worldId, opts()),
        getMap(worldId, opts())
      ])
      if (seen !== cycle) return
      detail.value = story
      setup.value = initialSetup
      grant.value = activeGrant
      grantLoaded.value = true
      map.value = worldMap
      await pageThrough(worldId, seen, opts(), 0)
      if (seen !== cycle) return
      // Record the room open (updates last_played_at) without advancing
      // gameplay. Best-effort: a failure leaves stale metadata, honestly so.
      if (openedFor.value !== worldId) {
        try {
          const reopened = await openStory(worldId, opts())
          if (seen === cycle) {
            detail.value = reopened
            openedFor.value = worldId
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
    advancing.value = false
    traveling.value = false
    loadingMore.value = false
  }

  async function refreshTimeline(full = false, worldId: string = id()): Promise<void> {
    if (!detail.value) return
    const seen = cycle
    try {
      const header: OpHeader = { role: unref(role), characterId: unref(characterId) }
      if (full) {
        entries.value = []
        await pageThrough(worldId, seen, header, 0)
      } else {
        await pageThrough(worldId, seen, header, cursor.value)
      }
      if (seen !== cycle) return
      const [story, worldMap] = await Promise.all([
        getStory(worldId, header),
        getMap(worldId, header)
      ])
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

  /** Explicit history continuation from the stored cursor. */
  async function loadMore(): Promise<void> {
    if (!detail.value || loadingMore.value || !hasMore.value) return
    loadingMore.value = true
    const seen = cycle
    try {
      await pageThrough(id(), seen, opts(), cursor.value)
    } catch (err) {
      if (seen !== cycle) return
      if (err instanceof ApiError && err.cancelled) return
      notice.value = {
        kind: 'error',
        text: err instanceof Error ? err.message : 'could not load more history'
      }
    } finally {
      if (seen === cycle) loadingMore.value = false
    }
  }

  async function advance(intents?: Parameters<typeof advanceStory>[2]): Promise<boolean> {
    if (!detail.value || advancing.value) return false
    advancing.value = true
    notice.value = null
    // Frozen operation context: every attempt below targets this world,
    // index, role and actor even if the route changes mid-request.
    const op: AdvanceOp = {
      worldId: id(),
      index: detail.value.absolute_index + 1,
      header: {
        role: unref(role),
        characterId: unref(characterId),
        signal: controller?.signal
      },
      intents,
      generation: cycle
    }
    const alive = (): boolean => op.generation === cycle
    const attempt = async (): Promise<void> => {
      const result = await advanceStory(op.worldId, op.index, op.intents, op.header)
      if (alive() && result.duplicate) {
        notice.value = { kind: 'info', text: 'That beat already committed — showing it.' }
      }
    }
    try {
      await attempt()
    } catch (err) {
      if (err instanceof ApiError && err.code === 'REQUEST_TIMEOUT' && alive()) {
        // Same frozen target retry: the server replays a committed beat.
        // No retry after navigation or disposal — the original request may
        // have committed, and A’s operation must never be sent to B.
        try {
          await attempt()
        } catch (retryErr) {
          if (alive()) {
            notice.value = {
              kind: 'error',
              text: retryErr instanceof Error ? retryErr.message : 'advance timed out'
            }
          }
          return false
        }
      } else if (err instanceof ApiError && err.code === 'VERSION_CONFLICT') {
        if (alive()) notice.value = { kind: 'info', text: 'Newer state arrived — refreshed.' }
      } else {
        if (alive()) {
          if (err instanceof ApiError && err.cancelled) return false
          notice.value = {
            kind: 'error',
            text: err instanceof Error ? err.message : 'could not advance'
          }
        }
        return false
      }
    } finally {
      // Stay pending through acknowledgement AND reconciliation refresh so
      // no second beat starts against stale displayed state — scoped to the
      // operation's own world. Always release the flag: a reused instance
      // must not stick mid-advance after cancellation.
      if (alive()) {
        await refreshTimeline(false, op.worldId)
      }
      advancing.value = false
    }
    return alive()
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

  async function reconcileTravel(op: TravelOp, failure: string): Promise<void> {
    try {
      // Reconciliation reads the operation's own world, even after the
      // route moved on — or not at all when the lifecycle is gone.
      const active = await listActivities(op.worldId, op.header)
      if (op.generation !== cycle) return
      const { mine, elsewhere } = matchActivity(active.members, op.actorId, op.toLocationId)
      notice.value = {
        kind: mine || elsewhere ? 'info' : 'error',
        text: mine
          ? 'That journey is already underway — advance the story to complete it.'
          : elsewhere
            ? 'This character already has a journey underway elsewhere.'
            : failure
      }
    } catch {
      if (op.generation === cycle) notice.value = { kind: 'error', text: failure }
    }
  }

  async function travel(characterId_: string, toLocationId: string): Promise<boolean> {
    if (traveling.value) return false
    traveling.value = true
    notice.value = null
    const op: TravelOp = {
      worldId: id(),
      actorId: characterId_,
      toLocationId,
      header: {
        role: unref(role),
        characterId: unref(characterId),
        signal: controller?.signal
      },
      generation: cycle
    }
    const alive = (): boolean => op.generation === cycle
    try {
      await startTravel(op.worldId, op.actorId, op.toLocationId, op.header)
      if (alive()) {
        notice.value = {
          kind: 'info',
          text: 'Journey begun — advance the story to complete it.'
        }
      }
      return alive()
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        // 409 covers underway journeys AND other preconditions (no route,
        // busy character): reconcile instead of assuming underway.
        await reconcileTravel(op, err.message || 'could not start the journey')
        return false
      }
      if (err instanceof ApiError && err.code === 'REQUEST_TIMEOUT') {
        // No idempotency key on this route: reconcile before reporting, so a
        // committed-but-unacknowledged start is not retried blindly.
        await reconcileTravel(op, 'the journey request timed out — check the cast before retrying')
        return false
      }
      if (alive()) {
        if (err instanceof ApiError && err.cancelled) return false
        notice.value = {
          kind: 'error',
          text: err instanceof Error ? err.message : 'could not start the journey'
        }
      }
      return false
    } finally {
      traveling.value = false
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
    loadingMore,
    notice,
    load,
    cancel,
    advance,
    travel,
    refreshTimeline,
    loadMore
  }
}
