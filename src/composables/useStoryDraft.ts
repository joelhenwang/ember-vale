/**
 * Server story-draft lifecycle for the New Story wizard (C2/C3).
 *
 * The server draft is the reloadable source of truth: the view rehydrates
 * from GET, persists via PATCH with the current expected version, and never
 * loses input on errors. A stable idempotency key per draft version makes
 * creation retries safe; a fresh key is minted per new operation only.
 */

import { ref } from 'vue'
import type { StoryDraftView } from '../../content/clients/worldsim'
import { ApiError } from '../api/http'
import { createDraft, createStory, getDraft, patchDraft, validateDraft } from '../api/worldsim'
import type { NewStorySelections } from '../game/drafting'
import { buildDraftPayload } from '../game/drafting'
import { newOperationKey } from '../api/http'

const DRAFT_ID_KEY = 'ember-vale.draft-id'

function createKeyName(draftId: string, version: number): string {
  return `ember-vale.create-key.${draftId}.v${version}`
}

function storedCreateKey(draftId: string, version: number): string {
  try {
    const existing = localStorage.getItem(createKeyName(draftId, version))
    if (existing) return existing
    const fresh = newOperationKey()
    localStorage.setItem(createKeyName(draftId, version), fresh)
    return fresh
  } catch {
    return newOperationKey()
  }
}

export function useStoryDraft() {
  const draft = ref<StoryDraftView | null>(null)
  const busy = ref(false)
  const notice = ref<string | null>(null)
  const issues = ref<string[]>([])
  const creating = ref(false)
  const createError = ref<string | null>(null)

  function rememberDraftId(id: string): void {
    try {
      localStorage.setItem(DRAFT_ID_KEY, id)
    } catch {
      /* storage unavailable: the ?draft= query still carries the id */
    }
  }

  function recalledDraftId(): string | null {
    try {
      return localStorage.getItem(DRAFT_ID_KEY)
    } catch {
      return null
    }
  }

  async function openNew(selections: NewStorySelections, step: string): Promise<void> {
    busy.value = true
    notice.value = null
    try {
      draft.value = await createDraft(buildDraftPayload(selections), step)
      rememberDraftId(draft.value.id)
    } catch (err) {
      notice.value = err instanceof Error ? err.message : 'could not start a draft'
      throw err
    } finally {
      busy.value = false
    }
  }

  async function openExisting(id: string): Promise<void> {
    busy.value = true
    notice.value = null
    try {
      draft.value = await getDraft(id)
      rememberDraftId(draft.value.id)
    } catch (err) {
      notice.value = err instanceof Error ? err.message : 'could not load the draft'
      throw err
    } finally {
      busy.value = false
    }
  }

  /** Persist selections; on a stale version, refresh and keep input. */
  async function save(selections: NewStorySelections, step: string): Promise<boolean> {
    if (!draft.value) return false
    busy.value = true
    notice.value = null
    try {
      draft.value = await patchDraft(
        draft.value.id,
        buildDraftPayload(selections),
        step,
        draft.value.version
      )
      return true
    } catch (err) {
      if (err instanceof ApiError && err.code === 'VERSION_CONFLICT') {
        try {
          draft.value = await getDraft(draft.value.id)
          notice.value = 'The draft changed elsewhere — reloaded; your input is kept above.'
        } catch {
          notice.value = 'The draft changed elsewhere — reload the page to reconcile.'
        }
        return false
      }
      notice.value = err instanceof Error ? err.message : 'could not save the draft'
      return false
    } finally {
      busy.value = false
    }
  }

  async function validate(): Promise<boolean> {
    if (!draft.value) return false
    try {
      const result = await validateDraft(draft.value.id)
      issues.value = result.issues ?? []
      return result.valid
    } catch (err) {
      issues.value = [err instanceof Error ? err.message : 'validation failed']
      return false
    }
  }

  async function submit(): Promise<string | null> {
    if (!draft.value) return null
    creating.value = true
    createError.value = null
    try {
      const key = storedCreateKey(draft.value.id, draft.value.version)
      const result = await createStory(draft.value.id, draft.value.version, key)
      try {
        localStorage.removeItem(DRAFT_ID_KEY)
      } catch {
        /* non-fatal */
      }
      return result.world_id
    } catch (err) {
      if (err instanceof ApiError && err.code === 'REQUEST_TIMEOUT') {
        // The server may still have committed: retry with the SAME key and
        // navigate to the existing story instead of reporting failure.
        try {
          const key = storedCreateKey(draft.value.id, draft.value.version)
          const replay = await createStory(draft.value.id, draft.value.version, key)
          try {
            localStorage.removeItem(DRAFT_ID_KEY)
          } catch {
            /* non-fatal */
          }
          return replay.world_id
        } catch (retryErr) {
          createError.value =
            retryErr instanceof Error ? retryErr.message : 'creation timed out'
          return null
        }
      }
      createError.value = err instanceof Error ? err.message : 'could not create the story'
      return null
    } finally {
      creating.value = false
    }
  }

  return {
    draft,
    busy,
    notice,
    issues,
    creating,
    createError,
    recalledDraftId,
    openNew,
    openExisting,
    save,
    validate,
    submit
  }
}
