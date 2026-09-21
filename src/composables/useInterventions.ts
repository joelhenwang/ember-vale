/**
 * Director/God intervention queue for one story (E6).
 *
 * Typed directions go through the shared queue: submit (idempotent per
 * client request id), list operator-visible items, read one for
 * reconciliation, edit text before claim (version-checked), and cancel
 * before application. Identity rides the caller's header (seat grant
 * wins server-side); this composable never invents a role.
 */

import { ref } from 'vue'
import type { InterventionView } from '../../content/clients/worldsim'
import { ApiError } from '../api/http'
import {
  cancelIntervention,
  editIntervention,
  listInterventions,
  readIntervention,
  submitIntervention,
  type CallOptions
} from '../api/worldsim'

export type DirectMode = 'influence' | 'force' | 'attempt'

export interface QueueNotice {
  kind: 'info' | 'error'
  text: string
}

interface PendingSubmission {
  key: string
  mode: DirectMode
  text: string
  /** Owning world: a retry never re-targets another world. */
  worldId: string
  /** Seat header the filing went out under: a seat change must not
   * silently reinterpret its retry. */
  role: string | undefined
}

function newRequestId(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) return crypto.randomUUID()
  return `req-${Date.now()}-${Math.floor(Math.random() * 1e9)}`
}

function messageOf(err: unknown, fallback: string): string {
  return err instanceof Error ? err.message : fallback
}

export function useInterventions(worldId: () => string, header: () => CallOptions) {
  const queue = ref<InterventionView[]>([])
  const active = ref<InterventionView | null>(null)
  const busy = ref(false)
  const notice = ref<QueueNotice | null>(null)
  /** Last submission key, kept so a transport failure retries the same
   * queue item instead of filing a duplicate. */
  const pending = ref<PendingSubmission | null>(null)
  let cycle = 0

  function upsert(item: InterventionView): void {
    const at = queue.value.findIndex((entry) => entry.id === item.id)
    queue.value =
      at >= 0
        ? queue.value.map((entry) => (entry.id === item.id ? item : entry))
        : [item, ...queue.value]
    active.value = item
  }

  async function refresh(): Promise<void> {
    const seen = cycle
    try {
      const items = await listInterventions(worldId(), header())
      if (seen !== cycle) return
      queue.value = items
      if (active.value) {
        active.value = items.find((entry) => entry.id === active.value?.id) ?? null
      }
    } catch (err) {
      if (seen !== cycle) return
      if (err instanceof ApiError && err.cancelled) return
      notice.value = { kind: 'error', text: messageOf(err, 'could not load the queue') }
    }
  }

  async function submit(mode: DirectMode, text: string): Promise<InterventionView | null> {
    // An unresolved filing blocks a fresh key: reconcile (select the
    // filed item) or discard it explicitly before filing anew.
    if (pending.value) {
      notice.value = {
        kind: 'error',
        text: 'A direction is still unresolved — retry the filing or discard it before filing anew.'
      }
      return null
    }
    const seen = cycle
    busy.value = true
    notice.value = null
    const submission: PendingSubmission = {
      key: newRequestId(),
      mode,
      text,
      worldId: worldId(),
      role: header().role
    }
    try {
      const item = await submitIntervention(worldId(), mode, text, submission.key, header())
      if (seen !== cycle) return null
      pending.value = null
      upsert(item)
      if (item.status === 'needs_clarification') {
        notice.value = {
          kind: 'info',
          text:
            item.failure_reason || 'The direction needs clarification — edit the text and resubmit.'
        }
      } else if (item.status === 'failed') {
        notice.value = { kind: 'error', text: item.failure_reason || 'The direction failed.' }
      }
      return item
    } catch (err) {
      if (seen !== cycle) return null
      if (err instanceof ApiError && err.cancelled) return null
      // The server may still have queued it: keep the key so the retry
      // replays the same item instead of filing a duplicate.
      pending.value = submission
      notice.value = { kind: 'error', text: messageOf(err, 'could not file the direction') }
      return null
    } finally {
      if (seen === cycle) busy.value = false
    }
  }

  /** Retry the last failed submission with its original key (replay, not duplicate). */
  async function retry(): Promise<InterventionView | null> {
    const last = pending.value
    if (!last) return null
    // Frozen ownership: a world or seat change since the filing must not
    // silently reinterpret its retry.
    if (last.worldId !== worldId() || last.role !== header().role) {
      notice.value = {
        kind: 'error',
        text: 'The world or seat changed since this was filed — review the queue, then file anew.'
      }
      return null
    }
    const seen = cycle
    busy.value = true
    try {
      const item = await submitIntervention(worldId(), last.mode, last.text, last.key, header())
      if (seen !== cycle) return null
      pending.value = null
      notice.value = null
      upsert(item)
      return item
    } catch (err) {
      if (seen !== cycle) return null
      if (err instanceof ApiError && err.cancelled) return null
      notice.value = { kind: 'error', text: messageOf(err, 'could not file the direction') }
      return null
    } finally {
      if (seen === cycle) busy.value = false
    }
  }

  async function reconcile(id: string): Promise<void> {
    const seen = cycle
    try {
      const item = await readIntervention(id, header())
      if (seen !== cycle) return
      upsert(item)
    } catch (err) {
      if (seen !== cycle) return
      if (err instanceof ApiError && err.cancelled) return
      notice.value = { kind: 'error', text: messageOf(err, 'could not read the direction') }
    }
  }

  /** Edit the active item's text before claim; restarts its history. */
  async function editActive(text: string): Promise<InterventionView | null> {
    const current = active.value
    if (!current || busy.value) return null
    const seen = cycle
    busy.value = true
    notice.value = null
    try {
      const item = await editIntervention(current.id, current.version, text, header())
      if (seen !== cycle) return null
      upsert(item)
      if (item.status === 'needs_clarification') {
        notice.value = {
          kind: 'info',
          text: item.failure_reason || 'Still needs clarification — edit again.'
        }
      }
      return item
    } catch (err) {
      if (seen !== cycle) return null
      if (err instanceof ApiError && err.cancelled) return null
      if (err instanceof ApiError && err.code === 'VERSION_CONFLICT') {
        notice.value = {
          kind: 'error',
          text: 'The direction changed underneath — reloading it.'
        }
        await reconcile(current.id)
        return null
      }
      notice.value = { kind: 'error', text: messageOf(err, 'could not edit the direction') }
      return null
    } finally {
      if (seen === cycle) busy.value = false
    }
  }

  /** Cancel the active item before application; history is preserved. */
  async function cancelActive(): Promise<boolean> {
    const current = active.value
    if (!current || busy.value) return false
    const seen = cycle
    busy.value = true
    notice.value = null
    try {
      const item = await cancelIntervention(current.id, current.version, header())
      if (seen !== cycle) return false
      upsert(item)
      return true
    } catch (err) {
      if (seen !== cycle) return false
      if (err instanceof ApiError && err.cancelled) return false
      notice.value = { kind: 'error', text: messageOf(err, 'could not cancel the direction') }
      return false
    } finally {
      if (seen === cycle) busy.value = false
    }
  }

  function select(id: string | null): void {
    const found = queue.value.find((entry) => entry.id === id) ?? null
    active.value = found
    // Reconcile an ambiguous filing only against its own item: the
    // request key and the owning world must both match. Selecting an
    // unrelated direction preserves Retry/Discard, and clearing the
    // selection alone never reconciles.
    const last = pending.value
    if (
      found &&
      last &&
      found.client_request_id === last.key &&
      found.world_id === last.worldId
    ) {
      pending.value = null
    }
  }

  /** Abandon local reconciliation of the unresolved filing so a fresh key may be filed.
   * Discarding never cancels a possibly accepted server operation: the filing may
   * still be queued server-side under its key. */
  function discardPending(): void {
    if (!pending.value) return
    pending.value = null
    notice.value = { kind: 'info', text: 'Stopped tracking the unresolved filing — file anew.' }
  }

  function dispose(): void {
    cycle += 1
    busy.value = false
  }

  return {
    queue,
    active,
    busy,
    notice,
    pending,
    refresh,
    submit,
    retry,
    reconcile,
    editActive,
    cancelActive,
    select,
    discardPending,
    dispose
  }
}
