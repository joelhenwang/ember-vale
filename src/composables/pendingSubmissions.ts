/**
 * Durable pending player submissions for beat resume (C4 recovery).
 *
 * The server never persists a filed player action before it commits: an
 * interruption ahead of `_decide_all` leaves no record of the words. So
 * the room freezes every filed submission (filing id, world, index, actor
 * payloads) into durable storage at send time. Resume replays exactly the
 * selected record — never the live composer, which the player may have
 * edited or which a reload has cleared.
 *
 * Two tabs share one storage. Every filing step below runs synchronously
 * with no awaits, so for a synchronous store (localStorage) each step is
 * indivisible across tabs: no second tab can interleave between the read
 * and the write. On that basis the first filing for a (world, index)
 * owns the primary slot; a later contender for an occupied slot is kept
 * separately under the contenders key and never overwrites the original.
 * A filing the server explicitly refuses for its index (409
 * already-executing) is marked refused and demoted out of the primary
 * slot, so recovery never replays words the server rejected. Retirement
 * removes only the exact filing that committed fresh — never a whole
 * world or index range, so one filing's commit cannot retire another's.
 *
 * Persistence is reported, not assumed: filing returns whether the write
 * succeeded. A failed write still files into composable memory for this
 * session, flagged memory-only, and the room must never claim
 * reload-safe preservation for it.
 */

import type { Stage1AdvanceRequest } from '../../content/clients/worldsim'

export type PlayerIntents = Exclude<Stage1AdvanceRequest['player_intents'], undefined>

export interface PendingSubmission {
  /** Unique filing identity: distinguishes the original from contenders. */
  id: string
  worldId: string
  index: number
  intents: PlayerIntents
  savedAt: string
  /** True once the record survived a storage write (reload-safe). */
  durable: boolean
  /** True after the server refused this filing for its index. Never replayed. */
  refused?: boolean
}

export interface SubmissionStorage {
  getItem(key: string): string | null
  setItem(key: string, value: string): void
  removeItem(key: string): void
}

const STORAGE_PREFIX = 'ember-vale.pending-submission.v1.'
const CONTENDERS_SUFFIX = '.contenders'

export function pendingKey(worldId: string): string {
  return `${STORAGE_PREFIX}${worldId}`
}

export function contendersKey(worldId: string): string {
  return `${STORAGE_PREFIX}${worldId}${CONTENDERS_SUFFIX}`
}

/** Browser storage when available, otherwise a private in-memory fallback. */
export function defaultSubmissionStorage(): SubmissionStorage {
  try {
    if (typeof localStorage !== 'undefined') return localStorage
  } catch {
    /* private mode or no DOM: fall through to memory */
  }
  const memory = new Map<string, string>()
  return {
    getItem: (key) => memory.get(key) ?? null,
    setItem: (key, value) => {
      memory.set(key, value)
    },
    removeItem: (key) => {
      memory.delete(key)
    }
  }
}

let filingCounter = 0

/** Unique filing identity for one send. Test seeds override it explicitly. */
export function newFilingId(): string {
  try {
    if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
      return crypto.randomUUID()
    }
  } catch {
    /* non-secure context: fall through to the counter fallback */
  }
  filingCounter += 1
  return `filing-${Date.now().toString(36)}-${filingCounter}`
}

/** Families the stage-1 advance route can validate (ActionIntent union). */
const SUPPORTED_FAMILIES = new Set([
  'wait',
  'rest',
  'observe',
  'move',
  'communicate',
  'spar',
  'appeal',
  'transfer'
])

function isPlainObject(value: unknown): value is Record<string, unknown> {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) return false
  const proto = Object.getPrototypeOf(value)
  return proto === Object.prototype || proto === null
}

function isIntentEntry(value: unknown): boolean {
  if (!isPlainObject(value)) return false
  if (typeof value['family'] !== 'string' || !SUPPORTED_FAMILIES.has(value['family'])) {
    return false
  }
  if (typeof value['character_id'] !== 'string' || value['character_id'].length === 0) {
    return false
  }
  if (typeof value['snapshot_id'] !== 'string' || value['snapshot_id'].length === 0) {
    return false
  }
  return true
}

/**
 * Supported intent structure for replay: a non-empty map of actor ids to
 * well-formed action intents. Arrays, empty maps, unknown families, and
 * entries without an actor and snapshot identity are invalid — the server
 * remains the deep validator, but shape-invalid data is never replayed.
 */
export function isSupportedIntents(value: unknown): value is PlayerIntents {
  if (!isPlainObject(value)) return false
  const keys = Object.keys(value)
  if (keys.length === 0) return false
  return keys.every((key) => key.length > 0 && isIntentEntry(value[key]))
}

/** Strict record check; id-less legacy records are adopted with a fresh id. */
function parseSubmissionRecord(worldId: string, parsed: unknown): PendingSubmission | null {
  if (!isPlainObject(parsed)) return null
  const record = parsed as Record<string, unknown>
  if (record['worldId'] !== worldId) return null
  if (typeof record['index'] !== 'number' || !Number.isInteger(record['index'])) return null
  if (!isSupportedIntents(record['intents'])) return null
  const id = typeof record['id'] === 'string' && record['id'].length > 0 ? record['id'] : null
  if (!id) {
    // Pre-identity record: adopt rather than strand an in-flight filing.
    return {
      id: newFilingId(),
      worldId,
      index: record['index'] as number,
      intents: record['intents'],
      savedAt: typeof record['savedAt'] === 'string' ? record['savedAt'] : '',
      durable: true
    }
  }
  if (typeof record['refused'] !== 'undefined' && typeof record['refused'] !== 'boolean') {
    return null
  }
  return {
    id,
    worldId,
    index: record['index'] as number,
    intents: record['intents'],
    savedAt: typeof record['savedAt'] === 'string' ? record['savedAt'] : '',
    durable: true,
    ...(record['refused'] === true ? { refused: true as const } : {})
  }
}

function parseStoredRecord(worldId: string, raw: string | null): PendingSubmission | null {
  if (!raw) return null
  let parsed: unknown
  try {
    parsed = JSON.parse(raw)
  } catch {
    return null
  }
  return parseSubmissionRecord(worldId, parsed)
}

export type StoredStatus = 'absent' | 'invalid' | 'valid'

/** Primary-slot read that distinguishes corrupt data from no data. */
export function inspectPrimarySubmission(
  store: SubmissionStorage,
  worldId: string
): { status: StoredStatus; submission: PendingSubmission | null } {
  let raw: string | null
  try {
    raw = store.getItem(pendingKey(worldId))
  } catch {
    return { status: 'absent', submission: null }
  }
  if (!raw) return { status: 'absent', submission: null }
  let parsed: unknown
  try {
    parsed = JSON.parse(raw)
  } catch {
    return { status: 'invalid', submission: null }
  }
  const submission = parseSubmissionRecord(worldId, parsed)
  if (!submission) return { status: 'invalid', submission: null }
  return { status: 'valid', submission }
}

export function loadPendingSubmission(
  store: SubmissionStorage,
  worldId: string
): PendingSubmission | null {
  return inspectPrimarySubmission(store, worldId).submission
}

function parseContenders(worldId: string, raw: string | null): PendingSubmission[] | null {
  if (!raw) return []
  let parsed: unknown
  try {
    parsed = JSON.parse(raw)
  } catch {
    return null
  }
  if (!Array.isArray(parsed)) return null
  const out: PendingSubmission[] = []
  for (const entry of parsed) {
    const record = parseSubmissionRecord(worldId, entry)
    if (record && !out.some((kept) => kept.id === record.id)) out.push(record)
  }
  return out
}

/** Contender-list read; individually corrupt entries are skipped. */
export function inspectContenderSubmissions(
  store: SubmissionStorage,
  worldId: string
): { status: StoredStatus; list: PendingSubmission[] } {
  let raw: string | null
  try {
    raw = store.getItem(contendersKey(worldId))
  } catch {
    return { status: 'absent', list: [] }
  }
  if (!raw) return { status: 'absent', list: [] }
  const list = parseContenders(worldId, raw)
  if (!list) return { status: 'invalid', list: [] }
  return { status: 'valid', list }
}

export function loadContenderSubmissions(
  store: SubmissionStorage,
  worldId: string
): PendingSubmission[] {
  return inspectContenderSubmissions(store, worldId).list
}

function writeJson(store: SubmissionStorage, key: string, value: unknown): boolean {
  try {
    store.setItem(key, JSON.stringify(value))
    return true
  } catch {
    return false
  }
}

function removeKey(store: SubmissionStorage, key: string): boolean {
  try {
    store.removeItem(key)
    return true
  } catch {
    return false
  }
}

export interface FilingDraft {
  worldId: string
  index: number
  intents: PlayerIntents
}

export interface FilingResult {
  record: PendingSubmission
  /** `primary` owns the slot; `contender` is kept separately, never overwriting. */
  role: 'primary' | 'contender'
  /** False when no write survived: the record is session memory only. */
  persisted: boolean
}

/**
 * File one submission synchronously: first filing for a free slot owns
 * the primary; anything else becomes a contender. A refused primary is
 * moved aside to the contender list before the newcomer claims the slot,
 * so no filing is silently lost. Returns persistence explicitly.
 */
export function filePendingSubmission(
  store: SubmissionStorage,
  draft: FilingDraft,
  seed?: { id?: string; savedAt?: string }
): FilingResult {
  const record: PendingSubmission = {
    id: seed?.id ?? newFilingId(),
    worldId: draft.worldId,
    index: draft.index,
    intents: draft.intents,
    savedAt: seed?.savedAt ?? new Date().toISOString(),
    durable: false
  }
  const key = pendingKey(draft.worldId)
  let existing: PendingSubmission | null = null
  try {
    existing = parseStoredRecord(draft.worldId, store.getItem(key))
  } catch {
    existing = null
  }
  if (!existing) {
    const persisted = writeJson(store, key, record)
    return { record: { ...record, durable: persisted }, role: 'primary', persisted }
  }
  // The slot is taken: keep the original, stash this filing separately.
  // A refused occupant steps aside first so its slot frees without loss.
  let carried: PendingSubmission[] = []
  if (existing.refused === true) {
    carried = [existing]
    removeKey(store, key)
  }
  const stored = parseContenders(draft.worldId, readRaw(store, contendersKey(draft.worldId)))
  const list = [...carried, ...(stored ?? [])]
  if (!list.some((kept) => kept.id === record.id)) list.push(record)
  const persisted = writeJson(store, contendersKey(draft.worldId), list)
  return { record: { ...record, durable: persisted }, role: 'contender', persisted }
}

function readRaw(store: SubmissionStorage, key: string): string | null {
  try {
    return store.getItem(key)
  } catch {
    return null
  }
}

/**
 * Mark one filing refused after the server rejects it for its index.
 * A refused primary is demoted to the contender list (slot freed);
 * a refused contender stays listed but is never a replay candidate.
 */
export function markSubmissionRefused(
  store: SubmissionStorage,
  worldId: string,
  filingId: string
): boolean {
  const key = pendingKey(worldId)
  const primary = parseStoredRecord(worldId, readRaw(store, key))
  if (primary && primary.id === filingId) {
    const demoted: PendingSubmission = { ...primary, refused: true }
    const stored = parseContenders(worldId, readRaw(store, contendersKey(worldId))) ?? []
    const list = stored.some((kept) => kept.id === filingId)
      ? stored.map((kept) => (kept.id === filingId ? demoted : kept))
      : [...stored, demoted]
    const kept = writeJson(store, contendersKey(worldId), list)
    const cleared = removeKey(store, key)
    return kept && cleared
  }
  const stored = parseContenders(worldId, readRaw(store, contendersKey(worldId)))
  if (!stored || !stored.some((kept) => kept.id === filingId)) return false
  const list = stored.map((kept) => (kept.id === filingId ? { ...kept, refused: true } : kept))
  return writeJson(store, contendersKey(worldId), list)
}

/**
 * Retire exactly one filing by id — the commit it belonged to is the only
 * proof its words landed. Other filings for any index are untouched.
 */
export function retireSubmission(
  store: SubmissionStorage,
  worldId: string,
  filingId: string
): void {
  const key = pendingKey(worldId)
  const primary = parseStoredRecord(worldId, readRaw(store, key))
  if (primary && primary.id === filingId) removeKey(store, key)
  const stored = parseContenders(worldId, readRaw(store, contendersKey(worldId)))
  if (stored && stored.some((kept) => kept.id === filingId)) {
    writeJson(
      store,
      contendersKey(worldId),
      stored.filter((kept) => kept.id !== filingId)
    )
  }
}
