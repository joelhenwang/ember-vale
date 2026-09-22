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
import { newOperationKey } from '../api/http'
import {
  completeEditorDraft,
  discardEditorDraft,
  getPreset,
  openEditorDraft,
  publishEditorDraft,
  saveEditorDraft
} from '../api/worldsim'

export type EditorStatus =
  'idle' | 'loading' | 'editing' | 'saving' | 'saved' | 'failed' | 'publishing' | 'published'

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

  let cycle = 0

  const hydrated = computed(() => hydrateFields(baseDetail.value, draft.value))

  async function open(presetId: string, baseRevision: number, signal?: AbortSignal): Promise<void> {
    cycle += 1
    const seen = cycle
    const wantPreset = presetId
    status.value = 'loading'
    error.value = null
    publishedRevision.value = null
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
    } catch (err) {
      if (seen !== cycle) return
      if (err instanceof Error && (err as { cancelled?: boolean }).cancelled) return
      status.value = 'failed'
      error.value = err instanceof Error ? err.message : 'could not open the draft'
      throw err
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
      return true
    } catch (err) {
      if (seen !== cycle || draft.value?.id !== wantDraft) return false
      status.value = 'failed'
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
    cycle += 1
    const seen = cycle
    const wantDraft = owned.id
    const wantVersion = owned.version
    status.value = 'publishing'
    error.value = null
    try {
      const view = await publishEditorDraft(presetId, wantDraft, wantVersion, presetVersion)
      if (seen !== cycle || draft.value?.id !== wantDraft) return null
      // Nested adoption pins the replayed revision, never the head.
      publishedRevision.value = view.published_revision
      status.value = 'published'
      return view
    } catch (err) {
      if (seen !== cycle || draft.value?.id !== wantDraft) return null
      status.value = 'failed'
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
      return true
    } catch (err) {
      if (draft.value?.id !== wantDraft) return false
      status.value = 'failed'
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
      return true
    } catch (err) {
      if (draft.value?.id !== wantDraft) return false
      status.value = 'failed'
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
    open,
    save,
    publish,
    complete,
    discard,
    dispose
  }
}
