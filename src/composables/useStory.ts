/**
 * One story's live state for the story room (C4).
 *
 * Loads detail, setup, timeline and map behind a story-scoped
 * AbortController: navigating away cancels in-flight work and late
 * responses for a previous story are ignored. Advance uses the next
 * absolute index; a timeout retries the SAME index (the server replays).
 * A 409 on travel-start means an activity is already running, so the view
 * reconciles the activity list instead of failing.
 */

import { computed, ref, unref, type Ref } from 'vue'
import type {
  MapResponse,
  StoryDetail,
  StorySetupView,
  TimelineEntry
} from '../../content/clients/worldsim'
import { ApiError, type Role } from '../api/http'
import {
  advanceStory,
  getMap,
  getSetup,
  getStory,
  getTimeline,
  listActivities,
  startTravel
} from '../api/worldsim'

export interface StoryNotice {
  kind: 'error' | 'info'
  text: string
}

export function useStory(
  storyId: string,
  role: Role | Ref<Role>,
  characterId?: string | Ref<string | undefined>
) {
  const detail = ref<StoryDetail | null>(null)
  const setup = ref<StorySetupView | null>(null)
  const entries = ref<TimelineEntry[]>([])
  const map = ref<MapResponse | null>(null)
  const loading = ref(true)
  const loadError = ref<string | null>(null)
  const advancing = ref(false)
  const traveling = ref(false)
  const notice = ref<StoryNotice | null>(null)

  let cycle = 0
  let controller: AbortController | null = null

  const opts = (): { role: Role; characterId?: string; signal?: AbortSignal } => ({
    role: unref(role),
    characterId: unref(characterId),
    signal: controller?.signal
  })

  const occupantsByPlace = computed(() => {
    const out = new Map<string, { name: string; places: string[] }>()
    for (const place of map.value?.places ?? []) {
      for (let i = 0; i < (place.occupant_ids?.length ?? 0); i += 1) {
        const id = place.occupant_ids?.[i]
        const name = place.occupants?.[i]
        if (!id || !name) continue
        const row = out.get(id) ?? { name, places: [] }
        row.places.push(place.name)
        out.set(id, row)
      }
    }
    return out
  })

  async function load(): Promise<void> {
    cycle += 1
    const seen = cycle
    controller?.abort()
    controller = new AbortController()
    loading.value = true
    loadError.value = null
    try {
      const [story, initialSetup, timeline, worldMap] = await Promise.all([
        getStory(storyId, opts()),
        getSetup(storyId, opts()),
        getTimeline(storyId, 0, opts()),
        getMap(storyId, opts())
      ])
      if (seen !== cycle) return
      detail.value = story
      setup.value = initialSetup
      entries.value = timeline.entries ?? []
      map.value = worldMap
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

  async function refreshTimeline(): Promise<void> {
    if (!detail.value) return
    try {
      const header = { role: unref(role), characterId: unref(characterId) }
      const timeline = await getTimeline(storyId, 0, header)
      entries.value = timeline.entries ?? []
      const [story, worldMap] = await Promise.all([
        getStory(storyId, header),
        getMap(storyId, header)
      ])
      detail.value = story
      map.value = worldMap
    } catch (err) {
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
    const index = detail.value.absolute_index + 1
    const header = { role: unref(role), characterId: unref(characterId) }
    const attempt = async (): Promise<boolean> => {
      const result = await advanceStory(storyId, index, null, header)
      if (result.duplicate) {
        notice.value = { kind: 'info', text: 'That beat already committed — showing it.' }
      }
      return true
    }
    try {
      await attempt()
    } catch (err) {
      if (err instanceof ApiError && err.code === 'REQUEST_TIMEOUT') {
        // Same index retry: the server replays a committed beat.
        try {
          await attempt()
        } catch (retryErr) {
          notice.value = {
            kind: 'error',
            text: retryErr instanceof Error ? retryErr.message : 'advance timed out'
          }
          return false
        }
      } else if (err instanceof ApiError && err.code === 'VERSION_CONFLICT') {
        notice.value = { kind: 'info', text: 'Newer state arrived — refreshed.' }
      } else {
        notice.value = {
          kind: 'error',
          text: err instanceof Error ? err.message : 'could not advance'
        }
        return false
      }
    } finally {
      advancing.value = false
    }
    await refreshTimeline()
    return true
  }

  async function travel(characterId_: string, toLocationId: string): Promise<boolean> {
    if (traveling.value) return false
    traveling.value = true
    notice.value = null
    try {
      await startTravel(storyId, characterId_, toLocationId, {
        role: unref(role),
        characterId: unref(characterId)
      })
      notice.value = {
        kind: 'info',
        text: 'Journey begun — advance the story to complete it.'
      }
      return true
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        // An activity is already running for this character: reconcile
        // instead of failing, then let the user advance it.
        try {
          const active = await listActivities(storyId, {
            role: unref(role),
            characterId: unref(characterId)
          })
          const mine = (active.items ?? []).find((a) => a.character_id === characterId_)
          notice.value = {
            kind: 'info',
            text: mine
              ? 'That journey is already underway — advance the story to complete it.'
              : 'Something is already underway — refreshed the list.'
          }
        } catch {
          notice.value = { kind: 'error', text: 'could not start the journey' }
        }
        return false
      }
      notice.value = {
        kind: 'error',
        text: err instanceof Error ? err.message : 'could not start the journey'
      }
      return false
    } finally {
      traveling.value = false
    }
  }

  return {
    detail,
    setup,
    entries,
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
