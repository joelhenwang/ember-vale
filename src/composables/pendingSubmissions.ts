/**
 * Durable pending player submissions for beat resume (C4 recovery).
 *
 * The server never persists a filed player action before it commits: an
 * interruption ahead of `_decide_all` leaves no record of the words. So
 * the room freezes every filed submission (world, index, actor payloads)
 * into durable storage at send time. Resume replays exactly that frozen
 * record — never the live composer, which the player may have edited or
 * which a reload has cleared. A record retires only when its beat (or a
 * later one) commits fresh; a duplicate reconciliation proves nothing
 * about this submission, so it never retires one.
 */

import type { Stage1AdvanceRequest } from '../../content/clients/worldsim'

export type PlayerIntents = Exclude<Stage1AdvanceRequest['player_intents'], undefined>

export interface PendingSubmission {
  worldId: string
  index: number
  intents: PlayerIntents
  savedAt: string
}

export interface SubmissionStorage {
  getItem(key: string): string | null
  setItem(key: string, value: string): void
  removeItem(key: string): void
}

const STORAGE_PREFIX = 'ember-vale.pending-submission.v1.'

export function pendingKey(worldId: string): string {
  return `${STORAGE_PREFIX}${worldId}`
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

function isIntents(value: unknown): value is PlayerIntents {
  if (typeof value !== 'object' || value === null) return false
  return Object.values(value).every((entry) => typeof entry === 'object' && entry !== null)
}

export function savePendingSubmission(store: SubmissionStorage, sub: PendingSubmission): void {
  try {
    store.setItem(pendingKey(sub.worldId), JSON.stringify(sub))
  } catch {
    /* durability is best-effort; the in-memory cache still holds this session */
  }
}

export function loadPendingSubmission(
  store: SubmissionStorage,
  worldId: string
): PendingSubmission | null {
  let raw: string | null
  try {
    raw = store.getItem(pendingKey(worldId))
  } catch {
    return null
  }
  if (!raw) return null
  let parsed: unknown
  try {
    parsed = JSON.parse(raw)
  } catch {
    return null
  }
  if (typeof parsed !== 'object' || parsed === null) return null
  const record = parsed as Partial<PendingSubmission>
  if (record.worldId !== worldId) return null
  if (typeof record.index !== 'number' || !Number.isInteger(record.index)) return null
  if (!isIntents(record.intents)) return null
  return {
    worldId: record.worldId,
    index: record.index,
    intents: record.intents,
    savedAt: typeof record.savedAt === 'string' ? record.savedAt : ''
  }
}

export function clearPendingSubmission(store: SubmissionStorage, worldId: string): void {
  try {
    store.removeItem(pendingKey(worldId))
  } catch {
    /* already gone is fine */
  }
}
