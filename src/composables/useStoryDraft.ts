/**
 * Server story-draft lifecycle for the New Story wizard (C2/C3).
 *
 * Everything here is owned by draft identity. The controller instance is
 * shared across draft-query transitions, so pending submission receipts,
 * create errors, acknowledged versions, and operation lifecycles are all
 * keyed by draft ID: an unresolved receipt from draft A can never become
 * draft B's Begin action, a late completion from A never replaces B's
 * state, and queued saves carry the draft they were enqueued for (reading
 * that same draft's next acknowledged version at execution, never a frozen
 * obsolete version and never B's).
 *
 * Durability is explicit: `saveState` tracks clean/saving/unsaved/failed
 * against the last acknowledged snapshot, a failed save keeps a
 * per-draft local recovery snapshot, and creation is one guarded workflow
 * that replays a draft's own ambiguous receipt before any fresh
 * save/version/key.
 */

import { computed, ref } from 'vue'
import type { StoryDraftView } from '../../content/clients/worldsim'
import { ApiError } from '../api/http'
import { createDraft, createStory, getDraft, patchDraft, validateDraft } from '../api/worldsim'
import type { NewStorySelections } from '../game/drafting'
import { buildDraftPayload } from '../game/drafting'
import { newOperationKey } from '../api/http'

const DRAFT_ID_KEY = 'ember-vale.draft-id'
const RECEIPTS_KEY = 'ember-vale.receipts'

function recoveryKey(draftId: string): string {
  return `ember-vale.recovery.${draftId}`
}

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
  /** ISO timestamp of the snapshot (display/debug only, never a decision). */
  at: string
  /**
   * Canonical snapshot the save that produced this entry covered. A later
   * successful save clears the entry only when it covers this exact
   * snapshot — a delayed older save must never delete newer edits.
   */
  snapshot: string
  /**
   * Acknowledged server version the snapshot's edits build on. Wall-clock
   * timestamps cannot decide whether the server already holds newer user
   * input, so reopening arbitrates on versions: a server version past this
   * base with different content is a conflict to surface, never a reason to
   * silently drop the local edits.
   */
  baseVersion: number | null
}

/** Reopening decision for a stored recovery against the fetched server draft. */
export type RecoveryDecision = 'covered' | 'restore' | 'conflict'

/**
 * Decide whether a stored recovery is already on the server ('covered'),
 * restores cleanly onto an unchanged server ('restore'), or needs an
 * explicit conflict notice because the server moved past the snapshot's
 * base version with different content ('conflict').
 */
/**
 * Optional draft-payload leaves where the backend (`str | None`, default
 * `None`) and the payload builder (omits falsy) agree that representations
 * mean "no value". `EMPTY_EQUIVALENT` paths collapse null, omitted, and
 * `''` (the builder maps `''` to omitted there); `NULL_EQUIVALENT` paths
 * collapse null and omitted only (the builder never emits them, so a
 * stored `''` there is foreign data worth distinguishing). Every other
 * field — required fields like `story.title`, identity fields, unknown
 * fields, arrays, numbers, booleans — passes through exactly, so
 * empty/null/omitted stay distinguishable outside these paths.
 */
const EMPTY_EQUIVALENT: Record<string, readonly string[]> = {
  world: ['name'],
  'cast[]': ['location_key'],
  mode: ['controlled_cast_key'],
  story: ['tone']
}

const NULL_EQUIVALENT: Record<string, readonly string[]> = {
  world: ['description'],
  story: ['premise', 'pacing'],
  ai: ['profile_id', 'profile_revision', 'model', 'style_pack_revision']
}

export function normalizeRecoveryPayload(value: unknown): unknown {
  return normalizeAt(value, '')
}

function normalizeAt(value: unknown, path: string): unknown {
  if (typeof value !== 'object' || value === null) return value
  if (Array.isArray(value)) {
    return value.map((item) => normalizeAt(item, `${path}[]`))
  }
  const out: Record<string, unknown> = {}
  for (const [k, v] of Object.entries(value)) {
    // `undefined` is serialization-neutral (JSON drops it either way).
    if (v === undefined) continue
    const emptyOk = EMPTY_EQUIVALENT[path]?.includes(k) ?? false
    const nullOk = emptyOk || (NULL_EQUIVALENT[path]?.includes(k) ?? false)
    if (v === null && nullOk) continue
    if (typeof v === 'string' && v === '' && emptyOk) continue
    const child = path ? `${path}.${k}` : k
    out[k] = Array.isArray(v)
      ? v.map((item) => normalizeAt(item, `${child}[]`))
      : normalizeAt(v, child)
  }
  return out
}

export function resolveRecovery(
  serverPayload: unknown,
  serverVersion: number,
  recovery: RecoveryDraft
): RecoveryDecision {
  if (
    canonical(normalizeRecoveryPayload(serverPayload)) ===
    canonical(normalizeRecoveryPayload(buildDraftPayload(recovery.selections)))
  )
    return 'covered'
  if (recovery.baseVersion === null || recovery.baseVersion < serverVersion) return 'conflict'
  return 'restore'
}

export interface BootServerDraft {
  payload: unknown
  version: number
  step: string
}

/**
 * The wizard's reopening plan for one draft — the exact logic
 * NewStoryView boots with. Either there is nothing to do, the server
 * already holds the kept edits (clear the entry), or the outstanding
 * local edits apply; on conflict the independent server state is
 * preserved in the plan so the wizard can offer both versions.
 */
export type BootRecoveryPlan =
  | { kind: 'none' }
  | { kind: 'covered' }
  | {
      kind: 'restore'
      selections: NewStorySelections
      step: string
      /** Server moved past the snapshot's base with different content. */
      conflict: boolean
      /** The independent server state, kept for the recovery choice. */
      serverPayload: unknown
      serverStep: string
    }

export function planBootRecovery(
  server: BootServerDraft,
  recovery: RecoveryDraft | null
): BootRecoveryPlan {
  if (!recovery) return { kind: 'none' }
  const decision = resolveRecovery(server.payload, server.version, recovery)
  if (decision === 'covered') return { kind: 'covered' }
  return {
    kind: 'restore',
    selections: recovery.selections,
    step: recovery.step,
    conflict: decision === 'conflict',
    serverPayload: server.payload,
    serverStep: server.step
  }
}

export type SaveState = 'clean' | 'saving' | 'unsaved' | 'failed'

function snapshotOf(selections: NewStorySelections, step: string): string {
  return canonical({ payload: normalizeRecoveryPayload(buildDraftPayload(selections)), step })
}

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

/**
 * Unresolved creation receipts, keyed by owning draft ID. Module-level so
 * leaving and reopening the wizard (or a reload, via RECEIPTS_KEY) keeps
 * A's protection without ever leaking it into B's Begin action.
 */
const receipts = new Map<string, FrozenSubmission>()

function loadPersistedReceipts(): void {
  try {
    const raw = localStorage.getItem(RECEIPTS_KEY)
    if (!raw) return
    const parsed = JSON.parse(raw) as Partial<Record<string, FrozenSubmission>>
    for (const [id, receipt] of Object.entries(parsed ?? {})) {
      if (
        typeof id === 'string' &&
        receipt &&
        receipt.draftId === id &&
        typeof receipt.version === 'number' &&
        typeof receipt.key === 'string'
      ) {
        receipts.set(id, { draftId: id, version: receipt.version, key: receipt.key })
      }
    }
  } catch {
    /* memory map still holds this session's receipts */
  }
}

function persistReceipts(setStorageFailed: () => void): void {
  try {
    localStorage.setItem(RECEIPTS_KEY, JSON.stringify(Object.fromEntries(receipts)))
  } catch {
    setStorageFailed()
  }
}

loadPersistedReceipts()

/** Last acknowledged version per draft, for queued saves behind navigation. */
const ackedVersions = new Map<string, number>()

/** Local recovery snapshots when localStorage is unavailable (or in tests). */
const memoryRecovery = new Map<string, RecoveryDraft>()

/**
 * Most recently seen edit snapshot per draft, updated on every save()
 * enqueue and every storeRecovery() write. A delayed save's failure handler
 * stores its (older) snapshot only when it is still the latest — a newer
 * leave snapshot must win, just as on the success path.
 */
const latestSeen = new Map<string, string>()

/** Test hook: clear module-level draft memory between isolated cases. */
export function resetDraftMemoryForTests(): void {
  receipts.clear()
  ackedVersions.clear()
  memoryRecovery.clear()
  memoryKeys.clear()
  latestSeen.clear()
}

interface QueuedSave {
  draftId: string
  selections: NewStorySelections
  step: string
}

export function useStoryDraft() {
  // Merge receipts persisted by earlier mounts (or a pre-reload session):
  // a fresh controller recovers other mounts' protection from storage.
  loadPersistedReceipts()
  const draft = ref<StoryDraftView | null>(null)
  const busy = ref(false)
  const notice = ref<string | null>(null)
  const issues = ref<string[]>([])
  const creating = ref(false)
  /** Create errors scoped by owning draft ID. */
  const createErrors = ref<Record<string, string>>({})
  /** Last acknowledged server state, as JSON, for unsaved-change checks. */
  const acked = ref<string | null>(null)
  const saveState = ref<SaveState>('clean')
  /** localStorage unavailable: session-only durability, keep the tab open. */
  const storageOk = ref(true)
  /** Bumps whenever receipts change; drives the per-draft ambiguity view. */
  const receiptTick = ref(0)

  /** Controller-level generation: load/save/validate/create completions
   * apply only to the draft and lifecycle that started them. */
  let opCycle = 0

  /** Serializes overlapping saves: each call chains synchronously with the
   * draft identity captured at enqueue time, so rapid navigation cannot
   * redirect queued work into another draft. */
  let saveTail: Promise<boolean> = Promise.resolve(true)

  const createError = computed(() =>
    draft.value ? (createErrors.value[draft.value.id] ?? null) : null
  )
  const ambiguous = computed(() => {
    void receiptTick.value
    return draft.value ? receipts.has(draft.value.id) : false
  })

  function setCreateError(draftId: string, message: string | null): void {
    const next = { ...createErrors.value }
    if (message === null) delete next[draftId]
    else next[draftId] = message
    createErrors.value = next
  }

  function markStorageFailed(): void {
    storageOk.value = false
  }

  function rememberDraftId(id: string): void {
    try {
      localStorage.setItem(DRAFT_ID_KEY, id)
    } catch {
      markStorageFailed()
    }
  }

  function recalledDraftId(): string | null {
    try {
      return localStorage.getItem(DRAFT_ID_KEY)
    } catch {
      return null
    }
  }

  function storeRecovery(draftId: string, selections: NewStorySelections, step: string): boolean {
    const snapshot = snapshotOf(selections, step)
    latestSeen.set(draftId, snapshot)
    const recovery: RecoveryDraft = {
      draftId,
      selections,
      step,
      at: new Date().toISOString(),
      snapshot,
      baseVersion: ackedVersions.get(draftId) ?? null
    }
    memoryRecovery.set(draftId, recovery)
    try {
      localStorage.setItem(recoveryKey(draftId), JSON.stringify(recovery))
      return true
    } catch {
      markStorageFailed()
      return false
    }
  }

  function validRecovery(parsed: unknown): RecoveryDraft | null {
    if (typeof parsed !== 'object' || parsed === null) return null
    const r = parsed as Partial<RecoveryDraft>
    if (typeof r.draftId !== 'string' || !r.draftId) return null
    if (typeof r.step !== 'string' || !r.step) return null
    if (typeof r.at !== 'string' || Number.isNaN(Date.parse(r.at))) return null
    const s = r.selections as Partial<NewStorySelections> | undefined
    if (typeof s !== 'object' || s === null) return null
    if (typeof s.world?.presetId !== 'string' || typeof s.world?.presetRevision !== 'number') {
      return null
    }
    if (!Array.isArray(s.cast)) return null
    if (s.mode?.role !== 'watcher' && s.mode?.role !== 'player') return null
    if (typeof s.title !== 'string') return null
    if (typeof r.snapshot !== 'string') return null
    if (r.baseVersion === undefined) return { ...r, baseVersion: null } as RecoveryDraft
    if (typeof r.baseVersion !== 'number') return null
    return r as RecoveryDraft
  }

  function readRecovery(draftId: string): RecoveryDraft | null {
    try {
      const raw = localStorage.getItem(recoveryKey(draftId))
      if (!raw) return memoryRecovery.get(draftId) ?? null
      const validated = validRecovery(JSON.parse(raw))
      if (validated && validated.draftId === draftId) return validated
      return memoryRecovery.get(draftId) ?? null
    } catch {
      return memoryRecovery.get(draftId) ?? null
    }
  }

  function clearRecovery(draftId: string): void {
    // Only the owning draft's recovery is ever touched.
    memoryRecovery.delete(draftId)
    try {
      localStorage.removeItem(recoveryKey(draftId))
    } catch {
      /* best-effort */
    }
  }

  /**
   * Clear a recovery entry only when the successful save covered its exact
   * snapshot. A delayed older save resolving after newer edits were
   * snapshotted must retain the newer entry.
   */
  function clearRecoveryIfCovered(draftId: string, coveredSnapshot: string): void {
    const memory = memoryRecovery.get(draftId)
    if (memory && memory.snapshot === coveredSnapshot) memoryRecovery.delete(draftId)
    try {
      const raw = localStorage.getItem(recoveryKey(draftId))
      if (!raw) return
      const parsed = JSON.parse(raw) as Partial<RecoveryDraft>
      if (parsed.snapshot === coveredSnapshot || typeof parsed.snapshot !== 'string') {
        localStorage.removeItem(recoveryKey(draftId))
      }
    } catch {
      /* best-effort */
    }
  }

  function markAcked(draftId: string, selections: NewStorySelections, step: string): void {
    if (draft.value?.id !== draftId) return
    acked.value = snapshotOf(selections, step)
    saveState.value = 'clean'
  }

  /** True when the given editor state matches the acknowledged snapshot. */
  function isAcked(selections: NewStorySelections, step: string): boolean {
    return acked.value !== null && acked.value === snapshotOf(selections, step)
  }

  function setReceipt(receipt: FrozenSubmission): void {
    receipts.set(receipt.draftId, receipt)
    persistReceipts(markStorageFailed)
    receiptTick.value += 1
  }

  function deleteReceipt(draftId: string): void {
    receipts.delete(draftId)
    persistReceipts(markStorageFailed)
    receiptTick.value += 1
  }

  async function openNew(selections: NewStorySelections, step: string): Promise<void> {
    opCycle += 1
    const seen = opCycle
    busy.value = true
    notice.value = null
    issues.value = []
    try {
      const created = await createDraft(buildDraftPayload(selections), step)
      if (seen !== opCycle) return
      draft.value = created
      ackedVersions.set(created.id, created.version)
      rememberDraftId(created.id)
      markAcked(created.id, selections, step)
    } catch (err) {
      if (seen !== opCycle) return
      notice.value = err instanceof Error ? err.message : 'could not start a draft'
      throw err
    } finally {
      if (seen === opCycle) busy.value = false
    }
  }

  async function openExisting(id: string): Promise<void> {
    opCycle += 1
    const seen = opCycle
    busy.value = true
    notice.value = null
    issues.value = []
    try {
      const loaded = await getDraft(id)
      // A slow A load resolving after B took over must not replace B.
      if (seen !== opCycle) return
      draft.value = loaded
      ackedVersions.set(loaded.id, loaded.version)
      rememberDraftId(loaded.id)
      // Other drafts' receipts, errors, and recovery are preserved as-is:
      // only this draft's acknowledgment state is (re)established.
      // Normalized like snapshotOf so a pristine form reads acknowledged
      // instead of phantom-unsaved.
      acked.value = canonical({
        payload: normalizeRecoveryPayload(loaded.payload as Record<string, unknown>),
        step: loaded.current_step
      })
      saveState.value = 'clean'
    } catch (err) {
      if (seen !== opCycle) return
      notice.value = err instanceof Error ? err.message : 'could not load the draft'
      throw err
    } finally {
      if (seen === opCycle) busy.value = false
    }
  }

  async function currentVersionOf(draftId: string): Promise<number> {
    const known = ackedVersions.get(draftId)
    if (known !== undefined) return known
    const live = await getDraft(draftId)
    ackedVersions.set(draftId, live.version)
    return live.version
  }

  async function doSave(item: QueuedSave): Promise<boolean> {
    const { draftId, selections, step } = item
    if (!draftId) return false
    const isCurrent = (): boolean => draft.value?.id === draftId
    if (isCurrent()) {
      busy.value = true
      saveState.value = 'saving'
    } else {
      busy.value = true
    }
    notice.value = null
    try {
      // The next acknowledged version for THIS draft, read at execution —
      // never a frozen obsolete version, never another draft's.
      const version = isCurrent()
        ? (draft.value as StoryDraftView).version
        : await currentVersionOf(draftId)
      const updated = await patchDraft(draftId, buildDraftPayload(selections), step, version)
      ackedVersions.set(draftId, updated.version)
      if (!isCurrent()) {
        // A's queued save still persisted A behind B's navigation, but B's
        // mounted state, acknowledgment, and notices are untouched.
        // Recovery still clears only if this save covered its snapshot.
        clearRecoveryIfCovered(draftId, snapshotOf(selections, step))
        return true
      }
      draft.value = updated
      markAcked(draftId, selections, step)
      clearRecoveryIfCovered(draftId, snapshotOf(selections, step))
      return true
    } catch (err) {
      const current = draft.value
      if (!current || current.id !== draftId) return false
      // A leave snapshot taken after this save was enqueued is newer input:
      // only this save's own still-latest snapshot is stored, so a delayed
      // failure never overwrites newer recovery with older content.
      const ownSnapshot = snapshotOf(selections, step)
      const keepRecovery = latestSeen.get(draftId) === ownSnapshot
      if (err instanceof ApiError && err.code === 'VERSION_CONFLICT') {
        try {
          const reloaded = await getDraft(current.id)
          if (draft.value?.id !== draftId) return false
          draft.value = reloaded
          ackedVersions.set(draftId, reloaded.version)
          notice.value = 'The draft changed elsewhere — reloaded; your input is kept above.'
        } catch {
          if (draft.value?.id !== draftId) return false
          notice.value = 'The draft changed elsewhere — reload the page to reconcile.'
        }
        saveState.value = 'failed'
        if (keepRecovery) storeRecovery(draftId, selections, step)
        return false
      }
      notice.value = err instanceof Error ? err.message : 'could not save the draft'
      saveState.value = 'failed'
      if (keepRecovery) storeRecovery(draftId, selections, step)
      return false
    } finally {
      busy.value = false
    }
  }

  /**
   * Invalidate this controller's lifecycle on view departure or disposal.
   * Already-issued server operations still complete and reconcile their
   * owning draft's receipts, but late completions change no mounted state
   * and navigate nowhere. Receipts, errors, and recovery persist keyed by
   * draft for the next mount.
   */
  function dispose(): void {
    opCycle += 1
    creating.value = false
    busy.value = false
  }

  /** Persist selections; on a stale version, refresh and keep input. */
  function save(selections: NewStorySelections, step: string): Promise<boolean> {
    // Draft identity and the input snapshot are frozen at enqueue time.
    const item: QueuedSave = { draftId: draft.value?.id ?? '', selections, step }
    if (item.draftId) latestSeen.set(item.draftId, snapshotOf(selections, step))
    const run = saveTail.then(() => doSave(item))
    saveTail = run
    return run
  }

  async function validate(): Promise<boolean> {
    const targetId = draft.value?.id
    if (!targetId) return false
    try {
      const result = await validateDraft(targetId)
      if (draft.value?.id !== targetId) return false
      issues.value = result.issues ?? []
      return result.valid
    } catch (err) {
      if (draft.value?.id !== targetId) return false
      issues.value = [err instanceof Error ? err.message : 'validation failed']
      return false
    }
  }

  async function submitFrozen(frozen: FrozenSubmission): Promise<string | null> {
    const ownerId = frozen.draftId
    try {
      const result = await createStory(frozen.draftId, frozen.version, frozen.key)
      deleteReceipt(ownerId)
      clearRecovery(ownerId)
      try {
        if (localStorage.getItem(DRAFT_ID_KEY) === ownerId) {
          localStorage.removeItem(DRAFT_ID_KEY)
        }
      } catch {
        /* non-fatal */
      }
      setCreateError(ownerId, null)
      return result.world_id
    } catch (err) {
      if (err instanceof ApiError && err.code === 'REQUEST_TIMEOUT') {
        // The server may still have committed: retry with the SAME frozen
        // values and navigate to the existing story instead of failing.
        try {
          const replay = await createStory(frozen.draftId, frozen.version, frozen.key)
          deleteReceipt(ownerId)
          clearRecovery(ownerId)
          try {
            if (localStorage.getItem(DRAFT_ID_KEY) === ownerId) {
              localStorage.removeItem(DRAFT_ID_KEY)
            }
          } catch {
            /* non-fatal */
          }
          setCreateError(ownerId, null)
          return replay.world_id
        } catch (retryErr) {
          // Still ambiguous: keep the owning draft's frozen submission so
          // its next retry replays it instead of minting a fresh
          // save/version/key.
          setReceipt(frozen)
          setCreateError(
            ownerId,
            retryErr instanceof Error
              ? `${retryErr.message} — the story may have been created; retrying replays the same submission.`
              : 'creation timed out — the story may have been created; retrying replays the same submission.'
          )
          return null
        }
      }
      deleteReceipt(ownerId)
      setCreateError(ownerId, err instanceof Error ? err.message : 'could not create the story')
      return null
    }
  }

  /**
   * The single guarded create workflow, owned end to end by the draft that
   * was mounted when it started. A pending ambiguous receipt replays only
   * when it belongs to that same draft; otherwise the workflow persists the
   * intended selections, stops on failure, validates the acknowledged
   * draft, and submits frozen id/version/key values. Late completions after
   * a draft switch change nothing and navigate nowhere.
   */
  async function createWorkflow(
    selections: NewStorySelections,
    step: string
  ): Promise<string | null> {
    // Synchronous operation guard: a second workflow while one runs is a
    // no-op, so rapid double-clicks submit exactly once.
    if (creating.value) return null
    const target = draft.value
    if (!target) return null
    const targetId = target.id
    const seenCycle = opCycle
    const isCurrent = (): boolean => draft.value?.id === targetId && seenCycle === opCycle
    creating.value = true
    setCreateError(targetId, null)
    try {
      const receipt = receipts.get(targetId)
      if (receipt) {
        const replayed = await submitFrozen(receipt)
        return isCurrent() ? replayed : null
      }
      const saved = await save(selections, step)
      if (!isCurrent()) return null
      if (!saved || !draft.value) return null
      const valid = await validate()
      if (!isCurrent()) return null
      if (!valid) return null
      const frozen: FrozenSubmission = {
        draftId: targetId,
        version: draft.value.version,
        key: storedCreateKey(targetId, draft.value.version)
      }
      const created = await submitFrozen(frozen)
      return isCurrent() ? created : null
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
    storageOk,
    isAcked,
    recalledDraftId,
    readRecovery,
    clearRecovery,
    storeRecovery,
    openNew,
    openExisting,
    dispose,
    save,
    validate,
    createWorkflow
  }
}
