/**
 * Server editor drafts for the preset studios (E3).
 *
 * One controller per studio mount. Every operation freezes its owning
 * draft id and versions at call time: a late save/publish response for
 * draft A can never overwrite draft B's state after navigation. Hydration
 * merges the exact base revision payload with the saved draft fields, so
 * fields the editor never exposes survive publish verbatim (the server
 * merges the same way).
 *
 * Local (not-yet-created) presets never touch the server here. They
 * persist to localStorage under `ember-vale.local-preset.*`, reload
 * across navigation, and carry one stable creation key each
 * (`ember-vale.preset-create-key.*`) reused across retries so a lost
 * first response cannot mint two presets. First publication is NOT
 * wired to `create_preset` yet: the server receipt that would make the
 * key effective is still pending, so new presets stay local-until-publish.
 */

import { computed, ref } from 'vue'
import type {
  EditorDraftView,
  PresetDetail,
  PresetPublishView
} from '../../content/clients/worldsim'
import { ApiError, newOperationKey } from '../api/http'
import {
  completeEditorDraft,
  discardEditorDraft,
  getPreset,
  openEditorDraft,
  publishEditorDraft,
  readEditorDraft,
  saveEditorDraft
} from '../api/worldsim'

export type EditorStatus =
  'idle' | 'loading' | 'editing' | 'saving' | 'saved' | 'failed' | 'publishing' | 'published'

/** Which operation failed last: retries are operation-specific, never a blind reopen. */
export type FailedOp = 'open' | 'save' | 'publish' | 'complete' | 'discard' | null

/**
 * A frozen publication attempt: retry replays exactly this, never a
 * fresh save. `formSnapshot` is the caller form's JSON at the moment it
 * was saved for this publication — the acknowledged content. A replay
 * may mark only that snapshot clean; anything newer stays dirty.
 */
export interface PendingPublication {
  draftId: string
  version: number
  presetVersion: number
  formSnapshot: string
}

const LOCAL_KEY = (kind: string, id: string): string => `ember-vale.local-preset.${kind}.${id}`
const CREATE_KEY_NAME = (localId: string): string => `ember-vale.preset-create-key.${localId}`

const memoryLocal = new Map<string, string>()
const memoryKeys = new Map<string, string>()

/** Test hook: clear module-level local memory between isolated cases. */
export function resetEditorDraftMemoryForTests(): void {
  memoryLocal.clear()
  memoryKeys.clear()
}

export function loadLocalPreset(kind: string, id: string): Record<string, unknown> | null {
  const key = LOCAL_KEY(kind, id)
  const raw = memoryLocal.get(key) ?? readStorage(key)
  if (!raw) return null
  try {
    const parsed = JSON.parse(raw) as unknown
    if (typeof parsed === 'object' && parsed !== null) return parsed as Record<string, unknown>
    return null
  } catch {
    return null
  }
}

function readStorage(key: string): string | null {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}

/** Persist unfinished new-preset work. False means storage failed. */
export function storeLocalPreset(
  kind: string,
  id: string,
  fields: Record<string, unknown>
): boolean {
  const key = LOCAL_KEY(kind, id)
  const raw = JSON.stringify(fields)
  memoryLocal.set(key, raw)
  try {
    localStorage.setItem(key, raw)
    return true
  } catch {
    return false
  }
}

export function clearLocalPreset(kind: string, id: string): void {
  const key = LOCAL_KEY(kind, id)
  memoryLocal.delete(key)
  try {
    localStorage.removeItem(key)
  } catch {
    /* best-effort */
  }
}

/**
 * One stable creation key per local draft, minted once and reused across
 * retries (memory first so a storage failure never mints a second key
 * mid-retry). The server receipt is pending; until it lands this key is
 * stored but never sent.
 */
export function stableCreateKey(localId: string): string {
  const name = CREATE_KEY_NAME(localId)
  const remembered = memoryKeys.get(name)
  if (remembered) return remembered
  try {
    const existing = localStorage.getItem(name)
    if (existing) {
      memoryKeys.set(name, existing)
      return existing
    }
    const fresh = newOperationKey()
    try {
      localStorage.setItem(name, fresh)
    } catch {
      /* memory map still holds it */
    }
    memoryKeys.set(name, fresh)
    return fresh
  } catch {
    const fresh = newOperationKey()
    memoryKeys.set(name, fresh)
    return fresh
  }
}

/** Merge the exact base payload with saved draft fields for display. */
export function hydrateFields(
  base: PresetDetail | null,
  draft: EditorDraftView | null
): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  const rev = (base?.revision ?? {}) as Record<string, unknown>
  for (const [k, v] of Object.entries(rev)) {
    if (k === 'kind') continue
    out[k] = v
  }
  for (const [k, v] of Object.entries(draft?.fields ?? {})) {
    if (k === 'kind') continue
    out[k] = v
  }
  return out
}

export function useEditorDraft() {
  const draft = ref<EditorDraftView | null>(null)
  const baseDetail = ref<PresetDetail | null>(null)
  const fields = ref<Record<string, unknown>>({})
  const status = ref<EditorStatus>('idle')
  const error = ref<string | null>(null)
  const publishedRevision = ref<number | null>(null)
  /** localStorage unavailable: session-only durability, keep the tab open. */
  const storageOk = ref(true)
  /** Last failed operation, so Retry replays exactly that — never a blind reopen. */
  const lastFailedOp = ref<FailedOp>(null)
  /**
   * Frozen publication identity. Set when a save is acknowledged for
   * publishing and cleared only when that exact publication resolves:
   * an ambiguous publish retries these frozen values without another
   * save (a fresh save would mint a new version and risk a duplicate
   * revision alongside the already-committed one).
   */
  const pendingPublication = ref<PendingPublication | null>(null)

  let cycle = 0

  const hydrated = computed(() => hydrateFields(baseDetail.value, draft.value))

  /**
   * Retire a draft left open on a superseded base (reload after a
   * publish) exactly when retirement is provably safe: complete()
   * succeeds only when the draft version still matches the published
   * receipt, so nothing unpublished is ever abandoned. Anything newer
   * stays a surfaced conflict for an explicit discard.
   */
  async function recoverSupersededDraft(
    presetId: string,
    baseRevision: number,
    signal?: AbortSignal
  ): Promise<boolean> {
    let current
    try {
      current = await readEditorDraft(presetId, { signal })
    } catch {
      return false
    }
    if (current.base_revision >= baseRevision) return false
    try {
      await completeEditorDraft(presetId, current.id, current.version, { signal })
    } catch {
      return false
    }
    return true
  }

  async function open(presetId: string, baseRevision: number, signal?: AbortSignal): Promise<void> {
    for (let attempt = 0; attempt < 2; attempt++) {
      cycle += 1
      const seen = cycle
      const wantPreset = presetId
      status.value = 'loading'
      error.value = null
      publishedRevision.value = null
      lastFailedOp.value = null
      pendingPublication.value = null
      try {
        const [detail, opened] = await Promise.all([
          getPreset(wantPreset, baseRevision, { signal }),
          openEditorDraft(wantPreset, baseRevision, { signal })
        ])
        if (seen !== cycle) return
        baseDetail.value = detail
        draft.value = opened
        fields.value = hydrateFields(detail, opened)
        status.value = 'editing'
        return
      } catch (err) {
        if (seen !== cycle) return
        if (err instanceof Error && (err as { cancelled?: boolean }).cancelled) return
        if (
          attempt === 0 &&
          err instanceof ApiError &&
          err.code === 'PRECONDITION_FAILED' &&
          (await recoverSupersededDraft(wantPreset, baseRevision, signal))
        ) {
          continue
        }
        status.value = 'failed'
        lastFailedOp.value = 'open'
        error.value = err instanceof Error ? err.message : 'could not open the draft'
        throw err
      }
    }
  }

  async function save(presetId: string): Promise<boolean> {
    const owned = draft.value
    if (!owned) return false
    cycle += 1
    const seen = cycle
    const wantDraft = owned.id
    const wantVersion = owned.version
    status.value = 'saving'
    error.value = null
    try {
      const updated = await saveEditorDraft(presetId, wantDraft, { ...fields.value }, wantVersion)
      if (seen !== cycle || draft.value?.id !== wantDraft) return false
      draft.value = updated
      fields.value = hydrateFields(baseDetail.value, updated)
      status.value = 'saved'
      lastFailedOp.value = null
      return true
    } catch (err) {
      if (seen !== cycle || draft.value?.id !== wantDraft) return false
      status.value = 'failed'
      lastFailedOp.value = 'save'
      error.value = err instanceof Error ? err.message : 'could not save the draft'
      return false
    }
  }

  async function publish(
    presetId: string,
    presetVersion: number
  ): Promise<PresetPublishView | null> {
    const owned = draft.value
    if (!owned) return null
    pendingPublication.value = {
      draftId: owned.id,
      version: owned.version,
      presetVersion,
      formSnapshot: ''
    }
    return runPublish(presetId)
  }

  /**
   * One guarded workflow: capture the form, save and acknowledge it, then
   * publish exactly that acknowledged version. Publishing the current
   * form without the intermediate save would publish the last
   * server-saved content instead of what the user sees.
   */
  async function saveAndPublish(
    presetId: string,
    nextFields: Record<string, unknown>,
    formSnapshot: string
  ): Promise<PresetPublishView | null> {
    const owned = draft.value
    if (!owned) return null
    cycle += 1
    const seen = cycle
    const wantDraft = owned.id
    const wantVersion = owned.version
    status.value = 'saving'
    error.value = null
    lastFailedOp.value = null
    let updated: EditorDraftView
    try {
      updated = await saveEditorDraft(presetId, wantDraft, nextFields, wantVersion)
    } catch (err) {
      if (seen !== cycle || draft.value?.id !== wantDraft) return null
      status.value = 'failed'
      lastFailedOp.value = 'save'
      error.value = err instanceof Error ? err.message : 'could not save the draft'
      return null
    }
    if (seen !== cycle || draft.value?.id !== wantDraft) return null
    draft.value = updated
    fields.value = hydrateFields(baseDetail.value, updated)
    status.value = 'saved'
    // Freeze the acknowledged version: the publication below — and any
    // retry of it — replays exactly this, never a fresh save.
    pendingPublication.value = {
      draftId: wantDraft,
      version: updated.version,
      presetVersion: baseDetail.value?.version ?? 0,
      formSnapshot
    }
    return runPublish(presetId)
  }

  /**
   * Retry the frozen publication without another save. Used after an
   * ambiguous publish (the request may have committed server-side: the
   * same draft and version replay the recorded revision instead of
   * duplicating it).
   */
  async function retryPublish(presetId: string): Promise<PresetPublishView | null> {
    const pending = pendingPublication.value
    if (!pending || draft.value?.id !== pending.draftId) return null
    return runPublish(presetId)
  }

  async function runPublish(presetId: string): Promise<PresetPublishView | null> {
    const pending = pendingPublication.value
    if (!pending) return null
    cycle += 1
    const seen = cycle
    status.value = 'publishing'
    error.value = null
    try {
      const view = await publishEditorDraft(
        presetId,
        pending.draftId,
        pending.version,
        pending.presetVersion
      )
      if (seen !== cycle || draft.value?.id !== pending.draftId) return null
      pendingPublication.value = null
      lastFailedOp.value = null
      // The publish bumped the preset version: refresh our copy so a
      // subsequent publication does not reuse an outdated version and
      // conflict spuriously. The revision payload stays the base one —
      // only head identity (version, current_revision) moves.
      if (baseDetail.value) {
        baseDetail.value = {
          ...baseDetail.value,
          version: view.detail.version,
          current_revision: view.detail.current_revision
        }
      }
      // Nested adoption pins the replayed revision, never the head.
      publishedRevision.value = view.published_revision
      status.value = 'published'
      return view
    } catch (err) {
      if (seen !== cycle || draft.value?.id !== pending.draftId) return null
      status.value = 'failed'
      lastFailedOp.value = 'publish'
      error.value = err instanceof Error ? err.message : 'could not publish the draft'
      return null
    }
  }

  async function complete(presetId: string): Promise<boolean> {
    const owned = draft.value
    if (!owned) return false
    const wantDraft = owned.id
    const wantVersion = owned.version
    try {
      await completeEditorDraft(presetId, wantDraft, wantVersion)
      if (draft.value?.id !== wantDraft) return false
      draft.value = null
      status.value = 'idle'
      lastFailedOp.value = null
      return true
    } catch (err) {
      if (draft.value?.id !== wantDraft) return false
      status.value = 'failed'
      lastFailedOp.value = 'complete'
      error.value = err instanceof Error ? err.message : 'could not complete the draft'
      return false
    }
  }

  async function discard(presetId: string): Promise<boolean> {
    const owned = draft.value
    if (!owned) return false
    const wantDraft = owned.id
    const wantVersion = owned.version
    try {
      await discardEditorDraft(presetId, wantDraft, wantVersion)
      if (draft.value?.id !== wantDraft) return false
      draft.value = null
      status.value = 'idle'
      lastFailedOp.value = null
      return true
    } catch (err) {
      if (draft.value?.id !== wantDraft) return false
      status.value = 'failed'
      lastFailedOp.value = 'discard'
      error.value = err instanceof Error ? err.message : 'could not discard the draft'
      return false
    }
  }

  function dispose(): void {
    cycle += 1
  }

  return {
    draft,
    baseDetail,
    fields,
    hydrated,
    status,
    error,
    publishedRevision,
    storageOk,
    lastFailedOp,
    pendingPublication,
    open,
    save,
    publish,
    saveAndPublish,
    retryPublish,
    complete,
    discard,
    dispose
  }
}
