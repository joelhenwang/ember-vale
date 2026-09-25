import { describe, expect, it } from 'vitest'
import {
  contendersKey,
  defaultSubmissionStorage,
  filePendingSubmission,
  inspectContenderSubmissions,
  inspectPrimarySubmission,
  isSupportedIntents,
  loadContenderSubmissions,
  loadPendingSubmission,
  markSubmissionRefused,
  newFilingId,
  pendingKey,
  retireSubmission,
  type FilingDraft,
  type PlayerIntents,
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

function throwingStore(): { store: SubmissionStorage; backing: Map<string, string> } {
  const backing = new Map<string, string>()
  const store: SubmissionStorage = {
    getItem: (key) => backing.get(key) ?? null,
    setItem: () => {
      throw new Error('quota exceeded')
    },
    removeItem: (key) => {
      backing.delete(key)
    }
  }
  return { store, backing }
}

function communicate(topic: string): PlayerIntents {
  return {
    'char-wren': {
      family: 'communicate',
      character_id: 'char-wren',
      snapshot_id: '00000000-0000-0000-0000-000000000000',
      target_character_id: 'char-ash',
      topic
    }
  }
}

const Q1: FilingDraft = { worldId: 'A', index: 2, intents: communicate('What news from the mill?') }
const Q2: FilingDraft = {
  worldId: 'A',
  index: 2,
  intents: communicate('What news from the market?')
}

describe('pendingSubmissions', () => {
  it('files the first submission as a durable primary', () => {
    const store = memStore()
    const filed = filePendingSubmission(store, Q1, {
      id: 'q1',
      savedAt: '2026-09-25T00:00:00.000Z'
    })
    expect(filed.role).toBe('primary')
    expect(filed.persisted).toBe(true)
    expect(filed.record.durable).toBe(true)
    expect(loadPendingSubmission(store, 'A')).toEqual(filed.record)
  })

  it('keeps a refused contender separate without touching the original', () => {
    const store = memStore()
    const first = filePendingSubmission(store, Q1, { id: 'q1' })
    const second = filePendingSubmission(store, Q2, { id: 'q2' })
    expect(first.role).toBe('primary')
    expect(second.role).toBe('contender')
    // The original still owns the slot.
    expect(loadPendingSubmission(store, 'A')?.id).toBe('q1')
    expect(loadPendingSubmission(store, 'A')?.intents).toEqual(Q1.intents)
    expect(loadContenderSubmissions(store, 'A').map((c) => c.id)).toEqual(['q2'])
  })

  it('stashes a different-index filing as a contender while the slot is taken', () => {
    const store = memStore()
    filePendingSubmission(store, Q1, { id: 'q1' })
    const later = filePendingSubmission(
      store,
      { worldId: 'A', index: 3, intents: Q2.intents },
      { id: 'q3' }
    )
    expect(later.role).toBe('contender')
    expect(loadPendingSubmission(store, 'A')?.id).toBe('q1')
  })

  it('demotes a refused primary aside and frees its slot without loss', () => {
    const store = memStore()
    filePendingSubmission(store, Q1, { id: 'q1' })
    filePendingSubmission(store, Q2, { id: 'q2' })
    // The server refuses the original filing (it lost the slot race).
    expect(markSubmissionRefused(store, 'A', 'q1')).toBe(true)
    expect(loadPendingSubmission(store, 'A')).toBeNull()
    const kept = loadContenderSubmissions(store, 'A')
    expect(kept.find((c) => c.id === 'q1')?.refused).toBe(true)
    expect(kept.find((c) => c.id === 'q2')?.refused).not.toBe(true)
    // A newcomer can now claim the freed slot; both filings survive.
    const third = filePendingSubmission(store, Q1, { id: 'q1-retry' })
    expect(third.role).toBe('primary')
    expect(
      loadContenderSubmissions(store, 'A')
        .map((c) => c.id)
        .sort()
    ).toEqual(['q1', 'q2'])
  })

  it('marks a refused contender without disturbing the primary', () => {
    const store = memStore()
    filePendingSubmission(store, Q1, { id: 'q1' })
    filePendingSubmission(store, Q2, { id: 'q2' })
    expect(markSubmissionRefused(store, 'A', 'q2')).toBe(true)
    expect(loadPendingSubmission(store, 'A')?.id).toBe('q1')
    expect(loadContenderSubmissions(store, 'A')).toHaveLength(1)
    expect(loadContenderSubmissions(store, 'A')[0]?.refused).toBe(true)
  })

  it('retires exactly the committed filing and nothing else', () => {
    const store = memStore()
    filePendingSubmission(store, Q1, { id: 'q1' })
    filePendingSubmission(store, Q2, { id: 'q2' })
    retireSubmission(store, 'A', 'q1')
    expect(loadPendingSubmission(store, 'A')).toBeNull()
    // The other filing survives another filing's commit.
    expect(loadContenderSubmissions(store, 'A').map((c) => c.id)).toEqual(['q2'])
    retireSubmission(store, 'A', 'q2')
    expect(loadContenderSubmissions(store, 'A')).toEqual([])
  })

  it('keeps worlds separate', () => {
    const store = memStore()
    filePendingSubmission(store, Q1, { id: 'q1' })
    filePendingSubmission(store, { ...Q2, worldId: 'B', index: 3 }, { id: 'qb' })
    retireSubmission(store, 'A', 'q1')
    expect(loadPendingSubmission(store, 'A')).toBeNull()
    expect(loadPendingSubmission(store, 'B')?.id).toBe('qb')
  })

  it('reports a failed write instead of claiming durability', () => {
    const { store } = throwingStore()
    const filed = filePendingSubmission(store, Q1, { id: 'q1' })
    expect(filed.persisted).toBe(false)
    expect(filed.record.durable).toBe(false)
    // Nothing survived for a fresh controller: absent, not corrupt.
    expect(loadPendingSubmission(store, 'A')).toBeNull()
    expect(inspectPrimarySubmission(store, 'A').status).toBe('absent')
    expect(loadContenderSubmissions(store, 'A')).toEqual([])
  })

  it('distinguishes invalid recovery data from an absent submission', () => {
    const store = memStore()
    expect(inspectPrimarySubmission(store, 'A').status).toBe('absent')
    store.setItem(pendingKey('A'), '{not json')
    expect(inspectPrimarySubmission(store, 'A').status).toBe('invalid')
    expect(loadPendingSubmission(store, 'A')).toBeNull()
    store.setItem(pendingKey('A'), JSON.stringify({ worldId: 'B', index: 2 }))
    expect(inspectPrimarySubmission(store, 'A').status).toBe('invalid')
    const inspected = inspectPrimarySubmission(store, 'missing')
    expect(inspected).toEqual({ status: 'absent', submission: null })
  })

  it('rejects shapeless records: arrays, unknown families, missing identity', () => {
    const store = memStore()
    const bad = [
      { worldId: 'A', index: 2, intents: ['words'] },
      { worldId: 'A', index: 2, intents: {} },
      { worldId: 'A', index: 2, intents: { 'char-wren': { topic: 'no family' } } },
      {
        worldId: 'A',
        index: 2,
        intents: { 'char-wren': { family: 'teleport', character_id: 'x', snapshot_id: 'y' } }
      },
      {
        worldId: 'A',
        index: 2,
        intents: { 'char-wren': [{ family: 'wait', character_id: 'x', snapshot_id: 'y' }] }
      },
      {
        worldId: 'A',
        index: 2,
        intents: {
          'char-wren': { family: 'communicate', snapshot_id: 'y', topic: 'no actor' }
        }
      },
      {
        worldId: 'A',
        index: 2,
        intents: {
          'char-wren': { family: 'communicate', character_id: 'char-wren', topic: 'no snapshot' }
        }
      }
    ]
    for (const record of bad) {
      store.setItem(pendingKey('A'), JSON.stringify(record))
      expect(loadPendingSubmission(store, 'A')).toBeNull()
      expect(inspectPrimarySubmission(store, 'A').status).toBe('invalid')
    }
    expect(
      isSupportedIntents({
        'char-wren': {
          family: 'wait',
          character_id: 'char-wren',
          snapshot_id: '00000000-0000-0000-0000-000000000000'
        }
      })
    ).toBe(true)
    expect(isSupportedIntents([{ family: 'wait' }])).toBe(false)
  })

  it('adopts id-less legacy records instead of stranding them', () => {
    const store = memStore()
    store.setItem(
      pendingKey('A'),
      JSON.stringify({ worldId: 'A', index: 2, intents: Q1.intents, savedAt: 'old' })
    )
    const loaded = loadPendingSubmission(store, 'A')
    expect(loaded?.id).toBeTruthy()
    expect(loaded?.intents).toEqual(Q1.intents)
  })

  it('skips corrupt contender entries while keeping the readable ones', () => {
    const store = memStore()
    filePendingSubmission(store, Q1, { id: 'q1' })
    store.setItem(
      contendersKey('A'),
      JSON.stringify([{ worldId: 'A', index: 2, intents: Q2.intents, id: 'q2' }, 'garbage'])
    )
    const inspected = inspectContenderSubmissions(store, 'A')
    expect(inspected.status).toBe('valid')
    expect(inspected.list.map((c) => c.id)).toEqual(['q2'])
    store.setItem(contendersKey('A'), '{not json')
    expect(inspectContenderSubmissions(store, 'A').status).toBe('invalid')
  })

  it('mints unique filing identities', () => {
    expect(newFilingId()).toBeTruthy()
    expect(newFilingId()).not.toBe(newFilingId())
  })

  it('falls back to memory without a DOM', () => {
    const store = defaultSubmissionStorage()
    const filed = filePendingSubmission(store, Q1, { id: 'q1' })
    expect(filed.persisted).toBe(true)
    expect(loadPendingSubmission(store, 'A')?.id).toBe('q1')
    retireSubmission(store, 'A', 'q1')
    expect(loadPendingSubmission(store, 'A')).toBeNull()
  })
})
