/**
 * Server story-draft lifecycle for the New Story wizard (C2/C3).
 *
 * The server draft is the reloadable source of truth: the view rehydrates
 * from GET, persists via PATCH with the current expected version, and never
 * loses input on errors. Durability is explicit: `saveState` tracks
 * clean/saving/unsaved/failed against the last acknowledged snapshot, a
 * failed save keeps a clearly identified local recovery draft, and creation
 * is one guarded workflow — persist the intended selections, stop on
 * failure, validate the acknowledged draft, then submit frozen
 * id/version/key values. An ambiguous create (timeout on every attempt)
 * keeps its frozen submission: the next user retry replays the same values
 * instead of starting a fresh save/version/key that could double-create.
 */

import { ref } from 'vue'
import type { StoryDraftView } from '../../content/clients/worldsim'
import { ApiError } from '../api/http'
import { createDraft, createStory, getDraft, patchDraft, validateDraft } from '../api/worldsim'
import type { NewStorySelections } from '../game/drafting'
import { buildDraftPayload } from '../game/drafting'
import { newOperationKey } from '../api/http'

const DRAFT_ID_KEY = 'ember-vale.draft-id'
const RECOVERY_KEY = 'ember-vale.recovery'

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

export interface RecoveryDraft {
  draftId: string
  selections: NewStorySelections
  step: string
  /** ISO timestamp of the failed save, for newer-than-server comparison. */
  at: string
}

export type SaveState = 'clean' | 'saving' | 'unsaved' | 'failed'

function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(',')}]`
  if (typeof value === 'object' && value !== null) {
    const entries = Object.entries(value as Record<string, unknown>)
      .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0))
      .map(([k, v]) => `${JSON.stringify(k)}:${canonical(v)}`)
    return `{${entries.join(',')}}`
  }
  return JSON.stringify(value) ?? 'null'
}

function snapshotOf(selections: NewStorySelections, step: string): string {
  return canonical({ payload: buildDraftPayload(selections), step })
}

export function useStoryDraft() {
  const draft = ref<StoryDraftView | null>(null)
  const busy = ref(false)
  const notice = ref<string | null>(null)
  const issues = ref<string[]>([])
  const creating = ref(false)
  const createError = ref<string | null>(null)
  /** Last acknowledged server state, as JSON, for unsaved-change checks. */
  const acked = ref<string | null>(null)
  const saveState = ref<SaveState>('clean')
  /** An ambiguous create keeps its frozen submission for replay retries. */
  const ambiguous = ref(false)
  let pendingFrozen: FrozenSubmission | null = null

  /** Serializes overlapping saves: each call chains synchronously, so no
   * two PATCHes for the same draft are ever in flight at once, and rapid
   * navigation cannot enqueue work before the busy flag is observable —
   * the chain link itself is the synchronous guard. */
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

  function storeRecovery(draftId: string, selections: NewStorySelections, step: string): void {
    try {
      const recovery: RecoveryDraft = {
        draftId,
        selections,
        step,
        at: new Date().toISOString()
      }
      localStorage.setItem(RECOVERY_KEY, JSON.stringify(recovery))
    } catch {
      /* without storage the mounted input is the only copy */
    }
  }

  function readRecovery(): RecoveryDraft | null {
    try {
      const raw = localStorage.getItem(RECOVERY_KEY)
      if (!raw) return null
      const parsed = JSON.parse(raw) as Partial<RecoveryDraft>
      if (
        typeof parsed.draftId !== 'string' ||
        typeof parsed.step !== 'string' ||
        typeof parsed.at !== 'string' ||
        typeof parsed.selections !== 'object' ||
        parsed.selections === null
      ) {
        return null
      }
      return parsed as RecoveryDraft
    } catch {
      return null
    }
  }

  function clearRecovery(draftId: string): void {
    try {
      const raw = localStorage.getItem(RECOVERY_KEY)
      if (!raw) return
      const parsed = JSON.parse(raw) as Partial<RecoveryDraft>
      if (parsed.draftId === draftId) localStorage.removeItem(RECOVERY_KEY)
    } catch {
      /* best-effort */
    }
  }

  function markAcked(selections: NewStorySelections, step: string): void {
    acked.value = snapshotOf(selections, step)
    saveState.value = 'clean'
  }

  /** True when the given editor state matches the acknowledged snapshot. */
  function isAcked(selections: NewStorySelections, step: string): boolean {
    return acked.value !== null && acked.value === snapshotOf(selections, step)
  }

  async function openNew(selections: NewStorySelections, step: string): Promise<void> {
    busy.value = true
    notice.value = null
    try {
      draft.value = await createDraft(buildDraftPayload(selections), step)
      rememberDraftId(draft.value.id)
      markAcked(selections, step)
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
      acked.value = canonical({
        payload: draft.value.payload as Record<string, unknown>,
        step: draft.value.current_step
      })
      saveState.value = 'clean'
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
    saveState.value = 'saving'
    notice.value = null
    try {
      draft.value = await patchDraft(
        draft.value.id,
        buildDraftPayload(selections),
        step,
        draft.value.version
      )
      markAcked(selections, step)
      clearRecovery(draft.value.id)
      return true
    } catch (err) {
      if (err instanceof ApiError && err.code === 'VERSION_CONFLICT') {
        try {
          draft.value = await getDraft(draft.value.id)
          notice.value = 'The draft changed elsewhere — reloaded; your input is kept above.'
        } catch {
          notice.value = 'The draft changed elsewhere — reload the page to reconcile.'
        }
        saveState.value = 'failed'
        if (draft.value) storeRecovery(draft.value.id, selections, step)
        return false
      }
      notice.value = err instanceof Error ? err.message : 'could not save the draft'
      saveState.value = 'failed'
      if (draft.value) storeRecovery(draft.value.id, selections, step)
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
      ambiguous.value = false
      pendingFrozen = null
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
          ambiguous.value = false
          pendingFrozen = null
          return replay.world_id
        } catch (retryErr) {
          // Still ambiguous: keep the frozen submission so the next user
          // retry replays it instead of minting a fresh save/version/key.
          ambiguous.value = true
          pendingFrozen = frozen
          createError.value =
            retryErr instanceof Error
              ? `${retryErr.message} — the story may have been created; retrying replays the same submission.`
              : 'creation timed out — the story may have been created; retrying replays the same submission.'
          return null
        }
      }
      ambiguous.value = false
      pendingFrozen = null
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
   * The single guarded create workflow: replay a pending ambiguous
   * submission first (never a blind fresh save after a possible commit);
   * otherwise persist the intended selections and step, stop on failure,
   * validate the acknowledged saved draft, then submit frozen id/version/key
   * values. Returns the world id only after the server acknowledges
   * creation — the caller navigates on non-null.
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
      if (pendingFrozen) {
        return await submitFrozen(pendingFrozen)
      }
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
    acked,
    saveState,
    ambiguous,
    isAcked,
    recalledDraftId,
    readRecovery,
    clearRecovery,
    openNew,
    openExisting,
    save,
    validate,
    submit,
    createWorkflow
  }
}
