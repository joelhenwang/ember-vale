/**
 * Durable pending player submissions for beat resume (C4 recovery).
 *
 * The server never persists a filed player action before it commits: an
 * interruption ahead of `_decide_all` leaves no record of the words. So
 * the room freezes every filed submission (filing id, world, index, actor
 * payloads) into durable storage at send time. Resume replays the
 * selected record — never the live composer, which the player may have
 * edited or which a reload has cleared.
 *
 * Two tabs share one storage, and a localStorage read-modify-write is
 * NOT atomic across tabs: the platform offers no locking, so a shared
 * primary slot can be claimed twice and the original lost. This module
 * therefore shares no mutable slot. Every filing writes only its own
 * unique key, which no other tab ever writes: same-value collisions are
 * impossible and removals are idempotent. Ownership is decided at read
 * time — the earliest unrefused filing for the stranded index wins — so
 * write order across tabs cannot displace the original. A filing the
 * server explicitly refuses for its index (409 already-executing) is
 * marked refused on its own key by its owning tab and can never become
 * the replay candidate. Retirement removes exactly the committed filing's
 * key, never another filing's. Pre-identity legacy records are adopted
 * read-only (never rewritten), so no migration write can race either.
 *
 * Durability is explicit, not assumed. Memory-backed storage reports
 * session-only preservation: its writes succeed locally but vanish with
 * the context, so `persisted` is false and the room must never claim
 * reload-safe preservation for it. Unreadable storage reports
 * `unavailable` — never `absent` — so inaccessible recovery data is not
 * mistaken for no recovery data.
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
  /** True only when the record survived a write to persistent storage. */
  durable: boolean
  /** True after the server refused this filing for its index. Never replayed. */
  refused?: boolean
}

export interface SubmissionStorage {
  getItem(key: string): string | null
  setItem(key: string, value: string): void
  removeItem(key: string): void
  /** Keys starting with the prefix; used to discover filings without a shared slot. */
  keys(prefix: string): string[]
  /**
   * Where writes land. Memory-backed stores report `session`: their
   * writes succeed locally but do not survive reload. Stores that
   * predate the flag (including the specs' shared fixtures, which model
   * one localStorage shared across tabs) are treated as `durable`.
   */
  persistence?: 'durable' | 'session'
}

const STORAGE_PREFIX = 'ember-vale.pending-submission.v1.'
const CONTENDERS_SUFFIX = '.contenders'
const FILING_INFIX = '.filing.'
const PROBE_KEY = `${STORAGE_PREFIX}probe`

export function pendingKey(worldId: string): string {
  return `${STORAGE_PREFIX}${worldId}`
}

export function contendersKey(worldId: string): string {
  return `${STORAGE_PREFIX}${worldId}${CONTENDERS_SUFFIX}`
}

function filingPrefix(worldId: string): string {
  return `${STORAGE_PREFIX}${worldId}${FILING_INFIX}`
}

export function filingKey(worldId: string, filingId: string): string {
  return `${filingPrefix(worldId)}${filingId}`
}

/**
 * Private per-context maps: their bytes die with the context, so records
 * read through them are session-only even when the bytes look durable.
 * A localStorage wrapper whose probe write fails is NOT listed here —
 * its readable bytes genuinely survive reload.
 */
const volatileStores = new WeakSet<object>()

function memoryStore(persistence: 'durable' | 'session'): SubmissionStorage {
  const memory = new Map<string, string>()
  const store: SubmissionStorage = {
    getItem: (key) => memory.get(key) ?? null,
    setItem: (key, value) => {
      memory.set(key, value)
    },
    removeItem: (key) => {
      memory.delete(key)
    },
    keys: (prefix) => [...memory.keys()].filter((key) => key.startsWith(prefix)),
    persistence
  }
  if (persistence === 'session') volatileStores.add(store)
  return store
}

/**
 * Browser storage when reachable. Read availability and write capability
 * are separated: a failed probe write flags the wrapper session-only but
 * keeps every readable durable record accessible — full storage must not
 * hide existing recovery data. Only a wholly unreachable localStorage
 * falls back to a private in-memory map, which is session-only and
 * starts empty for each fresh context.
 */
export function defaultSubmissionStorage(): SubmissionStorage {
  try {
    if (typeof localStorage !== 'undefined') {
      const backend = localStorage
      let writable = true
      try {
        backend.setItem(PROBE_KEY, '1')
        backend.removeItem(PROBE_KEY)
      } catch {
        writable = false
      }
      return {
        getItem: (key) => backend.getItem(key),
        setItem: (key, value) => {
          backend.setItem(key, value)
        },
        removeItem: (key) => {
          backend.removeItem(key)
        },
        keys: (prefix) => {
          const out: string[] = []
          for (let i = 0; i < backend.length; i += 1) {
            const key = backend.key(i)
            if (key !== null && key.startsWith(prefix)) out.push(key)
          }
          return out
        },
        persistence: writable ? 'durable' : 'session'
      }
    }
  } catch {
    /* unreachable storage: fall through to the session-only fallback */
  }
  return memoryStore('session')
}

let filingCounter = 0

function randomHex(bytes: number): string | null {
  try {
    if (typeof crypto !== 'undefined' && typeof crypto.getRandomValues === 'function') {
      const buf = new Uint8Array(bytes)
      crypto.getRandomValues(buf)
      return [...buf].map((b) => b.toString(16).padStart(2, '0')).join('')
    }
  } catch {
    /* no platform randomness: fall through to the weak fallback */
  }
  return null
}

/** Cross-context randomness for filing identity, when the platform has any. */
function hasStrongRandom(): boolean {
  try {
    if (typeof crypto === 'undefined') return false
    return typeof crypto.randomUUID === 'function' || typeof crypto.getRandomValues === 'function'
  } catch {
    return false
  }
}

/** Unique filing identity for one send. Test seeds override it explicitly. */
export function newFilingId(): string {
  try {
    if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
      return crypto.randomUUID()
    }
  } catch {
    /* non-secure context: fall through below */
  }
  return randomHex(16) ?? `filing-${Date.now().toString(36)}-${(filingCounter += 1)}`
}

/**
 * Mint an identity and say whether it is safe to share: the counter
 * fallback restarts at 1 in every fresh tab, so two tabs filing in the
 * same millisecond without platform randomness would share a key. Weak
 * identities stay memory-only — never written to shared storage.
 */
function mintFilingId(seed?: string): { id: string; shareable: boolean } {
  if (seed !== undefined) return { id: seed, shareable: true }
  if (hasStrongRandom()) return { id: newFilingId(), shareable: true }
  return { id: newFilingId(), shareable: false }
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
  if (typeof record['refused'] !== 'undefined' && typeof record['refused'] !== 'boolean') {
    return null
  }
  return {
    // Pre-identity record: adopt rather than strand an in-flight filing.
    id: id ?? newFilingId(),
    worldId,
    index: record['index'] as number,
    intents: record['intents'],
    savedAt: typeof record['savedAt'] === 'string' ? record['savedAt'] : '',
    durable: true,
    ...(record['refused'] === true ? { refused: true as const } : {})
  }
}

function parseJson(raw: string): { ok: true; value: unknown } | { ok: false } {
  try {
    return { ok: true, value: JSON.parse(raw) }
  } catch {
    return { ok: false }
  }
}

export type FilingsStatus = 'absent' | 'invalid' | 'valid' | 'unavailable'

export interface FilingsInspection {
  status: FilingsStatus
  /** Readable filings, oldest first; empty unless storage was readable. */
  filings: PendingSubmission[]
}

/**
 * Every filing for a world: unique filing keys plus read-only adoption
 * of pre-identity legacy records. Corrupt bytes are reported as
 * `invalid` while readable filings are still returned; thrown reads
 * report `unavailable`, never `absent`.
 */
export function inspectFilings(store: SubmissionStorage, worldId: string): FilingsInspection {
  let keyList: string[]
  let primaryRaw: string | null
  let contendersRaw: string | null
  try {
    keyList = store.keys(filingPrefix(worldId))
    primaryRaw = store.getItem(pendingKey(worldId))
    contendersRaw = store.getItem(contendersKey(worldId))
  } catch {
    return { status: 'unavailable', filings: [] }
  }
  const filings: PendingSubmission[] = []
  const seen = new Set<string>()
  let corrupt = 0
  // Private per-context maps never survive reload, so records read
  // through them are session-only — never laundered as durable. A
  // localStorage wrapper with failing writes keeps its readable records
  // durable: those bytes genuinely survive.
  const sessionOnly = volatileStores.has(store)
  const takeRaw = (raw: string | null): void => {
    if (!raw) return
    const parsed = parseJson(raw)
    if (!parsed.ok) {
      corrupt += 1
      return
    }
    const record = parseSubmissionRecord(worldId, parsed.value)
    if (!record || seen.has(record.id)) {
      // Unparseable shapes count; duplicate ids are harmless re-reads.
      if (!record) corrupt += 1
      return
    }
    seen.add(record.id)
    filings.push(sessionOnly ? { ...record, durable: false } : record)
  }
  for (const key of keyList) {
    let raw: string | null
    try {
      raw = store.getItem(key)
    } catch {
      return { status: 'unavailable', filings: [] }
    }
    takeRaw(raw)
  }
  // Legacy adoption: the single primary record, then the contender list.
  takeRaw(primaryRaw)
  if (contendersRaw) {
    const parsed = parseJson(contendersRaw)
    if (!parsed.ok || !Array.isArray(parsed.value)) {
      corrupt += 1
    } else {
      for (const entry of parsed.value) {
        if (typeof entry === 'undefined') {
          corrupt += 1
        } else {
          takeRaw(JSON.stringify(entry))
        }
      }
    }
  }
  filings.sort((a, b) =>
    a.savedAt < b.savedAt ? -1 : a.savedAt > b.savedAt ? 1 : a.id < b.id ? -1 : 1
  )
  if (filings.length === 0 && corrupt === 0) return { status: 'absent', filings }
  if (corrupt > 0) return { status: 'invalid', filings }
  return { status: 'valid', filings }
}

export function loadFilings(store: SubmissionStorage, worldId: string): PendingSubmission[] {
  return inspectFilings(store, worldId).filings
}

/**
 * The replay candidate for a stranded index: the earliest unrefused,
 * well-formed filing. Refused and shape-invalid filings are never
 * candidates; ties break on filing id, so election is deterministic
 * regardless of the order tabs wrote in.
 */
export function selectRecoveryCandidate(
  filings: PendingSubmission[],
  index: number
): PendingSubmission | null {
  const eligible = filings
    .filter(
      (filing) =>
        filing.index === index && filing.refused !== true && isSupportedIntents(filing.intents)
    )
    .sort((a, b) => (a.savedAt < b.savedAt ? -1 : a.savedAt > b.savedAt ? 1 : a.id < b.id ? -1 : 1))
  return eligible[0] ?? null
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
  /**
   * True only when the record survived a write to persistent storage.
   * Memory-backed writes report false: session-only, never reload-safe.
   */
  persisted: boolean
}

/**
 * File one submission under its own unique key: no shared slot is read,
 * so overlapping claims across tabs cannot overwrite each other — both
 * records survive and read-time election picks the earliest. Without
 * cross-context randomness the identity is unsafe to share, so the
 * filing stays memory-only rather than risking a key collision.
 * Returns persistence explicitly.
 */
export function filePendingSubmission(
  store: SubmissionStorage,
  draft: FilingDraft,
  seed?: { id?: string; savedAt?: string }
): FilingResult {
  const minted = mintFilingId(seed?.id)
  const record: PendingSubmission = {
    id: minted.id,
    worldId: draft.worldId,
    index: draft.index,
    intents: draft.intents,
    savedAt: seed?.savedAt ?? new Date().toISOString(),
    durable: false
  }
  if (!minted.shareable) return { record, persisted: false }
  const written = writeJson(store, filingKey(draft.worldId, record.id), record)
  const persisted = written && store.persistence !== 'session'
  return { record: { ...record, durable: persisted }, persisted }
}

/**
 * Mark one filing refused after the server rejects it for its index.
 * Only the owning tab marks its own filing, on its own key: no shared
 * state is read or removed. A refused filing stays listed but is never
 * a replay candidate.
 */
export function markSubmissionRefused(
  store: SubmissionStorage,
  worldId: string,
  filingId: string
): boolean {
  const key = filingKey(worldId, filingId)
  let raw: string | null
  try {
    raw = store.getItem(key)
  } catch {
    return false
  }
  if (!raw) return false
  const parsed = parseJson(raw)
  if (!parsed.ok) return false
  const record = parseSubmissionRecord(worldId, parsed.value)
  if (!record) return false
  return writeJson(store, key, { ...record, refused: true })
}

/**
 * Retire exactly one filing by id — the commit it belonged to is the only
 * proof its words landed. Removal targets the filing's own key (plus any
 * legacy copy), so concurrent retirements are idempotent and other
 * filings are untouched.
 */
export function retireSubmission(
  store: SubmissionStorage,
  worldId: string,
  filingId: string
): void {
  removeKey(store, filingKey(worldId, filingId))
  // Legacy copies, if any: same idempotent removal, best-effort rewrite.
  let primaryRaw: string | null = null
  let contendersRaw: string | null = null
  try {
    primaryRaw = store.getItem(pendingKey(worldId))
    contendersRaw = store.getItem(contendersKey(worldId))
  } catch {
    return
  }
  if (primaryRaw) {
    const parsed = parseJson(primaryRaw)
    if (parsed.ok) {
      const record = parseSubmissionRecord(worldId, parsed.value)
      if (record?.id === filingId) removeKey(store, pendingKey(worldId))
    }
  }
  if (contendersRaw) {
    const parsed = parseJson(contendersRaw)
    if (parsed.ok && Array.isArray(parsed.value)) {
      const kept = parsed.value.filter((entry) => {
        const record = parseSubmissionRecord(worldId, entry)
        return !record || record.id !== filingId
      })
      if (kept.length !== parsed.value.length) {
        writeJson(store, contendersKey(worldId), kept)
      }
    }
  }
}
