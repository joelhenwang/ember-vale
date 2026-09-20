/**
 * Server story-draft lifecycle for the New Story wizard (C2/C3).
 *
 * The server draft is the reloadable source of truth: the view rehydrates
 * from GET, persists via PATCH with the current expected version, and never
 * loses input on errors. Creation is one guarded workflow — persist the
 * intended selections, stop on failure, validate the acknowledged draft,
 * then submit frozen id/version/key values (timeout retries reuse the exact
 * same key from an in-memory store, so storage failure cannot mint a fresh
 * key mid-retry and strand a created story behind an error).
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

/** In-memory first: storage failure must not mint a fresh key mid-retry. */
const memoryKeys = new Map<string, string>()

function storedCreateKey(draftId: string, version: number): string {
  const name = createKeyName(draftId, version)
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
      /* best-effort persistence; the map still holds it */
    }
    memoryKeys.set(name, fresh)
    return fresh
  } catch {
    const fresh = newOperationKey()
    memoryKeys.set(name, fresh)
    return fresh
  }
}

export interface FrozenSubmission {
  draftId: string
  version: number
  key: string
}

export function useStoryDraft() {
  const draft = ref<StoryDraftView | null>(null)
  const busy = ref(false)
  const notice = ref<string | null>(null)
  const issues = ref<string[]>([])
  const creating = ref(false)
  const createError = ref<string | null>(null)

  /** Serializes overlapping saves: each call chains synchronously, so no
   * two PATCHes for the same draft are ever in flight at once. */
  let saveTail: Promise<boolean> = Promise.resolve(true)

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

  async function doSave(selections: NewStorySelections, step: string): Promise<boolean> {
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

  /** Persist selections; on a stale version, refresh and keep input. */
  function save(selections: NewStorySelections, step: string): Promise<boolean> {
    const run = saveTail.then(() => doSave(selections, step))
    saveTail = run
    return run
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

  async function submitFrozen(frozen: FrozenSubmission): Promise<string | null> {
    try {
      const result = await createStory(frozen.draftId, frozen.version, frozen.key)
      try {
        localStorage.removeItem(DRAFT_ID_KEY)
      } catch {
        /* non-fatal */
      }
      return result.world_id
    } catch (err) {
      if (err instanceof ApiError && err.code === 'REQUEST_TIMEOUT') {
        // The server may still have committed: retry with the SAME frozen
        // values and navigate to the existing story instead of failing.
        try {
          const replay = await createStory(frozen.draftId, frozen.version, frozen.key)
          try {
            localStorage.removeItem(DRAFT_ID_KEY)
          } catch {
            /* non-fatal */
          }
          return replay.world_id
        } catch (retryErr) {
          createError.value = retryErr instanceof Error ? retryErr.message : 'creation timed out'
          return null
        }
      }
      createError.value = err instanceof Error ? err.message : 'could not create the story'
      return null
    }
  }

  async function submit(): Promise<string | null> {
    if (!draft.value) return null
    creating.value = true
    createError.value = null
    try {
      return await submitFrozen({
        draftId: draft.value.id,
        version: draft.value.version,
        key: storedCreateKey(draft.value.id, draft.value.version)
      })
    } finally {
      creating.value = false
    }
  }

  /**
   * The single guarded create workflow: persist the intended selections and
   * step first; on failure stop with input preserved. Validate the
   * acknowledged saved draft; freeze id/version/key for the submission and
   * retry the same frozen values. Returns the world id only after the
   * server acknowledges creation — the caller navigates on non-null.
   */
  async function createWorkflow(
    selections: NewStorySelections,
    step: string
  ): Promise<string | null> {
    // Synchronous operation guard: a second workflow while one runs is a
    // no-op, so rapid double-clicks submit exactly once.
    if (creating.value) return null
    creating.value = true
    createError.value = null
    try {
      const saved = await save(selections, step)
      if (!saved || !draft.value) return null
      const valid = await validate()
      if (!valid) return null
      const frozen: FrozenSubmission = {
        draftId: draft.value.id,
        version: draft.value.version,
        key: storedCreateKey(draft.value.id, draft.value.version)
      }
      return await submitFrozen(frozen)
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
    submit,
    createWorkflow
  }
}
