/**
 * First-preset creation for the studios (E3).
 *
 * A local draft becomes a server preset exactly once per distinct
 * submission. Each submission freezes its request bytes
 * ({key, name, payload}) and persists them across reloads, so every
 * retry — after a lost response, a concurrent double-click, or a
 * browser restart — resends the identical key and content and replays
 * the recorded receipt instead of minting a second preset.
 *
 * A deliberate resubmission of changed content is a NEW submission: it
 * rotates to a fresh key rather than conflicting under the old one.
 * Only the receipt clears the frozen state and rotates the slot key.
 */

import { ref } from 'vue'
import { ApiError } from '../api/http'
import { createPreset } from '../api/worldsim'
import type { PresetDetail } from '../../content/clients/worldsim'
import { clearCreateKey, stableCreateKey } from './useEditorDraft'

export interface FrozenCreateRequest {
  key: string
  kind: string
  /** Complete creation payload, including its `name`. */
  payload: Record<string, unknown>
}

export type CreationStatus = 'idle' | 'creating' | 'failed'

const REQUEST_KEY = (localId: string): string => `ember-vale.preset-create-request.${localId}`

const memoryRequests = new Map<string, string>()

/** Test hook: clear module-level request memory between isolated cases. */
export function resetPresetCreationMemoryForTests(): void {
  memoryRequests.clear()
}

function readStorage(key: string): string | null {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}

/** The frozen submission for a slot, if one is still awaiting its receipt. */
export function loadCreateRequest(localId: string): FrozenCreateRequest | null {
  const raw = memoryRequests.get(REQUEST_KEY(localId)) ?? readStorage(REQUEST_KEY(localId))
  if (!raw) return null
  try {
    const parsed = JSON.parse(raw) as unknown
    if (typeof parsed !== 'object' || parsed === null) return null
    const rec = parsed as Record<string, unknown>
    if (
      typeof rec['key'] !== 'string' ||
      typeof rec['kind'] !== 'string' ||
      typeof rec['payload'] !== 'object' ||
      rec['payload'] === null
    ) {
      return null
    }
    return {
      key: rec['key'],
      kind: rec['kind'],
      payload: rec['payload'] as Record<string, unknown>
    }
  } catch {
    return null
  }
}

function storeCreateRequest(localId: string, req: FrozenCreateRequest): void {
  const raw = JSON.stringify(req)
  memoryRequests.set(REQUEST_KEY(localId), raw)
  try {
    localStorage.setItem(REQUEST_KEY(localId), raw)
  } catch {
    /* memory map still holds it */
  }
}

function clearCreateRequest(localId: string): void {
  memoryRequests.delete(REQUEST_KEY(localId))
  try {
    localStorage.removeItem(REQUEST_KEY(localId))
  } catch {
    /* best-effort */
  }
}

function sameSubmission(
  a: FrozenCreateRequest,
  kind: string,
  payload: Record<string, unknown>
): boolean {
  return a.kind === kind && JSON.stringify(a.payload) === JSON.stringify(payload)
}

export function usePresetCreation(localId: string) {
  const status = ref<CreationStatus>('idle')
  const error = ref<string | null>(null)
  /** A submission is frozen while it awaits its receipt (survives reload). */
  const pending = ref(loadCreateRequest(localId) !== null)

  /**
   * Submit the packed form for first creation (`payload` carries its
   * `name`). An unchanged form resends the frozen bytes under the frozen
   * key (safe replay); changed content starts a distinct submission
   * under a fresh key. Resolves the created preset id, or null when the
   * request failed (error explains; the frozen state is kept for retry).
   * Concurrent calls collapse into one.
   */
  async function submit(kind: string, payload: Record<string, unknown>): Promise<string | null> {
    if (status.value === 'creating') return null
    const rawName = payload['name']
    const trimmed = typeof rawName === 'string' ? rawName.trim() : ''
    if (!trimmed) {
      status.value = 'failed'
      error.value = 'Name this preset before creating it.'
      return null
    }
    status.value = 'creating'
    error.value = null
    const frozen = loadCreateRequest(localId)
    let req: FrozenCreateRequest
    if (frozen && sameSubmission(frozen, kind, payload)) {
      req = frozen
    } else {
      // A deliberate resubmission of changed content is a distinct
      // submission under a fresh key — never a conflicting reuse of the
      // old one. (If the frozen request committed unseen, its preset
      // stands alongside as an orphan rather than blocking progress.)
      clearCreateKey(localId)
      req = { key: stableCreateKey(localId), kind, payload }
      storeCreateRequest(localId, req)
      pending.value = true
    }
    let detail: PresetDetail
    try {
      detail = await createPreset(req.kind, trimmed, req.payload, req.key)
    } catch (err) {
      status.value = 'failed'
      if (err instanceof ApiError && err.code === 'IDEMPOTENCY_CONFLICT') {
        error.value =
          'This creation key already recorded a different submission. ' +
          'Change nothing and retry to recover it, or start a fresh submission.'
      } else {
        error.value = err instanceof Error ? err.message : 'could not create the preset'
      }
      return null
    }
    clearCreateRequest(localId)
    clearCreateKey(localId)
    pending.value = false
    status.value = 'idle'
    return detail.id
  }

  return { status, error, pending, submit }
}
