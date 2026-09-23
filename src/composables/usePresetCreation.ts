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
 * While a submission is unresolved (its receipt has not landed), every
 * retry replays the ORIGINAL frozen request under its ORIGINAL key,
 * even when the form has moved on. Newer edits are stashed aside as
 * superseded — never sent implicitly — so a lost response followed by
 * an edit and a retry still yields exactly one preset. A second preset
 * is only ever minted through the explicit `submitFresh` action.
 *
 * Reload safety depends on the frozen request surviving in storage: a
 * freeze that only reaches memory is flagged via `requestPersisted`,
 * and the views must not present that state as reload-safe.
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

/** Newer form content set aside while an older submission replays. */
export interface SupersededCreateEdits {
  kind: string
  payload: Record<string, unknown>
}

export type CreationStatus = 'idle' | 'creating' | 'failed'

const REQUEST_KEY = (localId: string): string => `ember-vale.preset-create-request.${localId}`
const SUPERSEDED_KEY = (localId: string): string => `ember-vale.preset-create-superseded.${localId}`
const RECOVERED_KEY = (localId: string): string => `ember-vale.preset-create-recovered.${localId}`

const memoryRequests = new Map<string, string>()
const memorySuperseded = new Map<string, string>()
const memoryRecovered = new Map<string, string>()
/** Slots whose frozen request never reached storage: reload-unsafe. */
const memoryOnlyRequests = new Set<string>()

/** Test hook: clear module-level request memory between isolated cases. */
export function resetPresetCreationMemoryForTests(): void {
  memoryRequests.clear()
  memorySuperseded.clear()
  memoryRecovered.clear()
  memoryOnlyRequests.clear()
}

function readStorage(key: string): string | null {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}

function isFrozenCreateRequest(raw: unknown): raw is FrozenCreateRequest {
  if (typeof raw !== 'object' || raw === null) return false
  const rec = raw as Record<string, unknown>
  return (
    typeof rec['key'] === 'string' &&
    typeof rec['kind'] === 'string' &&
    typeof rec['payload'] === 'object' &&
    rec['payload'] !== null
  )
}

function isSupersededEdits(raw: unknown): raw is SupersededCreateEdits {
  if (typeof raw !== 'object' || raw === null) return false
  const rec = raw as Record<string, unknown>
  return (
    typeof rec['kind'] === 'string' && typeof rec['payload'] === 'object' && rec['payload'] !== null
  )
}

/** The frozen submission for a slot, if one is still awaiting its receipt. */
export function loadCreateRequest(localId: string): FrozenCreateRequest | null {
  const raw = memoryRequests.get(REQUEST_KEY(localId)) ?? readStorage(REQUEST_KEY(localId))
  if (!raw) return null
  try {
    const parsed = JSON.parse(raw) as unknown
    if (!isFrozenCreateRequest(parsed)) return null
    return { key: parsed.key, kind: parsed.kind, payload: parsed.payload }
  } catch {
    return null
  }
}

/**
 * Freeze a submission. Returns true when the record reached storage
 * (reload-safe); false when it lives in memory only. Callers must surface
 * the memory-only case instead of claiming reload safety.
 */
function storeCreateRequest(localId: string, req: FrozenCreateRequest): boolean {
  const raw = JSON.stringify(req)
  memoryRequests.set(REQUEST_KEY(localId), raw)
  try {
    localStorage.setItem(REQUEST_KEY(localId), raw)
    memoryOnlyRequests.delete(localId)
    return true
  } catch {
    memoryOnlyRequests.add(localId)
    return false
  }
}

function clearCreateRequest(localId: string): void {
  memoryRequests.delete(REQUEST_KEY(localId))
  memoryOnlyRequests.delete(localId)
  try {
    localStorage.removeItem(REQUEST_KEY(localId))
  } catch {
    /* best-effort */
  }
}

/** Newer edits set aside while an older submission replays (advisory copy). */
export function loadSupersededEdits(localId: string): SupersededCreateEdits | null {
  const raw = memorySuperseded.get(SUPERSEDED_KEY(localId)) ?? readStorage(SUPERSEDED_KEY(localId))
  if (!raw) return null
  try {
    const parsed = JSON.parse(raw) as unknown
    if (!isSupersededEdits(parsed)) return null
    return { kind: parsed.kind, payload: parsed.payload }
  } catch {
    return null
  }
}

function storeSupersededEdits(localId: string, edits: SupersededCreateEdits): void {
  const raw = JSON.stringify(edits)
  memorySuperseded.set(SUPERSEDED_KEY(localId), raw)
  try {
    localStorage.setItem(SUPERSEDED_KEY(localId), raw)
  } catch {
    /* the live form remains the primary store */
  }
}

function clearSupersededEdits(localId: string): void {
  memorySuperseded.delete(SUPERSEDED_KEY(localId))
  try {
    localStorage.removeItem(SUPERSEDED_KEY(localId))
  } catch {
    /* best-effort */
  }
}

/** Preset id recovered by replaying a frozen submission with edits set aside. */
export function loadRecoveredPresetId(localId: string): string | null {
  const raw = memoryRecovered.get(RECOVERED_KEY(localId)) ?? readStorage(RECOVERED_KEY(localId))
  return typeof raw === 'string' && raw.length > 0 ? raw : null
}

function storeRecoveredPresetId(localId: string, presetId: string): void {
  memoryRecovered.set(RECOVERED_KEY(localId), presetId)
  try {
    localStorage.setItem(RECOVERED_KEY(localId), presetId)
  } catch {
    /* the recovered panel simply will not survive a reload */
  }
}

function clearRecoveredPresetId(localId: string): void {
  memoryRecovered.delete(RECOVERED_KEY(localId))
  try {
    localStorage.removeItem(RECOVERED_KEY(localId))
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

function requestName(req: FrozenCreateRequest): string {
  const rawName = req.payload['name']
  return typeof rawName === 'string' ? rawName.trim() : ''
}

export function usePresetCreation(localId: string) {
  const status = ref<CreationStatus>('idle')
  const error = ref<string | null>(null)
  /** A submission is frozen while it awaits its receipt (survives reload). */
  const pending = ref(loadCreateRequest(localId) !== null)
  /**
   * False when the frozen request lives in memory only: retry survives
   * this tab, but a reload before the receipt may duplicate. Views must
   * say so instead of offering a reload-safe retry.
   */
  const requestPersisted = ref(
    loadCreateRequest(localId) === null || !memoryOnlyRequests.has(localId)
  )
  /** Newer edits set aside while the frozen request replays. */
  const supersededEdits = ref<SupersededCreateEdits | null>(loadSupersededEdits(localId))
  /** Preset id recovered by a replay that set edits aside. */
  const recoveredId = ref<string | null>(loadRecoveredPresetId(localId))
  /** Whether the most recent submit replayed the frozen request. */
  const replayed = ref(false)

  async function send(req: FrozenCreateRequest): Promise<string | null> {
    let detail: PresetDetail
    try {
      detail = await createPreset(req.kind, requestName(req), req.payload, req.key)
    } catch (err) {
      status.value = 'failed'
      if (err instanceof ApiError && err.code === 'IDEMPOTENCY_CONFLICT') {
        error.value =
          'This creation key already recorded a different submission. ' +
          'Change nothing and retry to recover it, or start a fresh submission.'
      } else {
        error.value = err instanceof Error ? err.message : 'could not create the preset'
      }
      if (memoryOnlyRequests.has(localId)) {
        // The failure text alone would invite a reload-safe retry that
        // this slot cannot honor: say the memory-only part explicitly.
        error.value +=
          ' The creation request is in memory only (storage unavailable): ' +
          'retry works in this tab, but a reload before the receipt lands may create a duplicate.'
      }
      return null
    }
    clearCreateRequest(localId)
    clearCreateKey(localId)
    pending.value = false
    requestPersisted.value = true
    status.value = 'idle'
    return detail.id
  }

  /**
   * Submit the packed form for first creation (`payload` carries its
   * `name`). While a submission is unresolved, this ALWAYS replays the
   * frozen bytes under the frozen key — changed content is stashed as
   * superseded edits, never minted as a second preset. Resolves the
   * created preset id, or null when the request failed (error explains;
   * the frozen state is kept for retry) or when a recovered preset
   * already answers the submission (open it, or start fresh explicitly).
   * Concurrent calls collapse into one.
   */
  async function submit(kind: string, payload: Record<string, unknown>): Promise<string | null> {
    if (status.value === 'creating') return null
    const frozen = loadCreateRequest(localId)
    if (frozen) {
      if (!sameSubmission(frozen, kind, payload)) {
        // Newer edits are preserved separately; the replay below sends
        // only the original frozen bytes.
        const edits = { kind, payload }
        storeSupersededEdits(localId, edits)
        supersededEdits.value = edits
      }
      replayed.value = true
      status.value = 'creating'
      error.value = null
      if (!requestName(frozen)) {
        status.value = 'failed'
        error.value = 'Name this preset before creating it.'
        return null
      }
      const id = await send(frozen)
      if (id && supersededEdits.value) {
        // The receipt answers the original submission; the newer edits
        // stay available and are applied only through an explicit action.
        recoveredId.value = id
        storeRecoveredPresetId(localId, id)
      }
      return id
    }
    if (recoveredId.value) {
      // A replay already recovered this slot's preset: a plain submit
      // must not silently mint a second one. Open the recovered preset
      // to apply the edits, or start a separate preset explicitly.
      status.value = 'failed'
      error.value =
        `Preset ${recoveredId.value} was already created from this draft. ` +
        'Open it to apply these edits, or create a separate preset explicitly.'
      return null
    }
    const trimmed = typeof payload['name'] === 'string' ? payload['name'].trim() : ''
    if (!trimmed) {
      status.value = 'failed'
      error.value = 'Name this preset before creating it.'
      return null
    }
    status.value = 'creating'
    error.value = null
    recoveredId.value = null
    clearRecoveredPresetId(localId)
    clearSupersededEdits(localId)
    supersededEdits.value = null
    const req: FrozenCreateRequest = { key: stableCreateKey(localId), kind, payload }
    requestPersisted.value = storeCreateRequest(localId, req)
    if (!requestPersisted.value) {
      error.value =
        'The creation request is kept in memory only (storage unavailable): ' +
        'retry works in this tab, but a reload before the receipt lands may create a duplicate. ' +
        'Keep this tab open until creation succeeds.'
    }
    replayed.value = false
    pending.value = true
    return send(req)
  }

  /**
   * Explicit escape hatch: abandon the frozen identity and submit the
   * current form as a DISTINCT submission under a fresh key. Only call
   * this from an explicit "create a separate preset" action: when the
   * abandoned request had already committed unseen, its preset stands as
   * an orphan. Never called implicitly by `submit`.
   */
  async function submitFresh(
    kind: string,
    payload: Record<string, unknown>
  ): Promise<string | null> {
    if (status.value === 'creating') return null
    const trimmed = typeof payload['name'] === 'string' ? payload['name'].trim() : ''
    if (!trimmed) {
      status.value = 'failed'
      error.value = 'Name this preset before creating it.'
      return null
    }
    status.value = 'creating'
    error.value = null
    clearCreateRequest(localId)
    clearCreateKey(localId)
    clearSupersededEdits(localId)
    supersededEdits.value = null
    recoveredId.value = null
    clearRecoveredPresetId(localId)
    const req: FrozenCreateRequest = { key: stableCreateKey(localId), kind, payload }
    requestPersisted.value = storeCreateRequest(localId, req)
    replayed.value = false
    pending.value = true
    return send(req)
  }

  /** Dismiss the recovery notice; the live form is untouched. */
  function dismissRecovery(): void {
    clearSupersededEdits(localId)
    supersededEdits.value = null
    recoveredId.value = null
    clearRecoveredPresetId(localId)
    if (status.value === 'failed') {
      status.value = 'idle'
      error.value = null
    }
  }

  return {
    status,
    error,
    pending,
    requestPersisted,
    supersededEdits,
    recoveredId,
    replayed,
    submit,
    submitFresh,
    dismissRecovery
  }
}
