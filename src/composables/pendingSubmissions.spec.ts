import { describe, expect, it } from 'vitest'
import {
  clearPendingSubmission,
  defaultSubmissionStorage,
  loadPendingSubmission,
  pendingKey,
  savePendingSubmission,
  type PendingSubmission,
  type SubmissionStorage
} from './pendingSubmissions'

function memStore(): SubmissionStorage {
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

const SUB: PendingSubmission = {
  worldId: 'A',
  index: 2,
  intents: { 'char-wren': { topic: 'dawn patrol' } },
  savedAt: '2026-09-25T00:00:00.000Z'
}

describe('pendingSubmissions', () => {
  it('round-trips the frozen world, index and payloads', () => {
    const store = memStore()
    savePendingSubmission(store, SUB)
    expect(loadPendingSubmission(store, 'A')).toEqual(SUB)
  })

  it('keeps worlds separate and clears one without touching others', () => {
    const store = memStore()
    savePendingSubmission(store, SUB)
    savePendingSubmission(store, { ...SUB, worldId: 'B', index: 3 })
    clearPendingSubmission(store, 'A')
    expect(loadPendingSubmission(store, 'A')).toBeNull()
    expect(loadPendingSubmission(store, 'B')?.index).toBe(3)
  })

  it('rejects corrupt, cross-world and shapeless records', () => {
    const store = memStore()
    store.setItem(pendingKey('A'), '{not json')
    expect(loadPendingSubmission(store, 'A')).toBeNull()
    store.setItem(pendingKey('A'), JSON.stringify({ ...SUB, worldId: 'B' }))
    expect(loadPendingSubmission(store, 'A')).toBeNull()
    store.setItem(pendingKey('A'), JSON.stringify({ ...SUB, index: 'two' }))
    expect(loadPendingSubmission(store, 'A')).toBeNull()
    store.setItem(pendingKey('A'), JSON.stringify({ ...SUB, intents: { 'char-wren': 'words' } }))
    expect(loadPendingSubmission(store, 'A')).toBeNull()
  })

  it('falls back to memory without a DOM', () => {
    const store = defaultSubmissionStorage()
    savePendingSubmission(store, SUB)
    expect(loadPendingSubmission(store, 'A')).toEqual(SUB)
    clearPendingSubmission(store, 'A')
    expect(loadPendingSubmission(store, 'A')).toBeNull()
  })
})
