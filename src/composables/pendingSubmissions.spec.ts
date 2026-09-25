import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  contendersKey,
  defaultSubmissionStorage,
  filePendingSubmission,
  filingKey,
  inspectFilings,
  isSupportedIntents,
  loadFilings,
  markSubmissionRefused,
  newFilingId,
  pendingKey,
  retireSubmission,
  selectRecoveryCandidate,
  type FilingDraft,
  type PlayerIntents,
  type SubmissionStorage
} from './pendingSubmissions'

/** One localStorage shared across tabs: durable, enumerable. */
function memStore(): SubmissionStorage {
  const memory = new Map<string, string>()
  return {
    getItem: (key) => memory.get(key) ?? null,
    setItem: (key, value) => {
      memory.set(key, value)
    },
    removeItem: (key) => {
      memory.delete(key)
    },
    keys: (prefix) => [...memory.keys()].filter((key) => key.startsWith(prefix))
  }
}

/** Private per-context memory via the real factory: writes succeed locally, die with the page. */
function sessionStore(): SubmissionStorage {
  vi.stubGlobal('localStorage', undefined)
  return defaultSubmissionStorage()
}

function throwingStore(): SubmissionStorage {
  return {
    getItem: () => {
      throw new Error('denied')
    },
    setItem: () => {
      throw new Error('denied')
    },
    removeItem: () => undefined,
    keys: () => {
      throw new Error('denied')
    }
  }
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

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('pendingSubmissions', () => {
  it('files under a unique key and reports durable persistence', () => {
    const store = memStore()
    const filed = filePendingSubmission(store, Q1, {
      id: 'q1',
      savedAt: '2026-09-25T00:00:01.000Z'
    })
    expect(filed.persisted).toBe(true)
    expect(filed.record.durable).toBe(true)
    expect(loadFilings(store, 'A')).toEqual([filed.record])
  })

  it('lets overlapping claims coexist and elects the earliest regardless of write order', () => {
    const store = memStore()
    // Tab B wins the write race; Tab A's earlier filing still owns recovery.
    const b = filePendingSubmission(store, Q2, { id: 'q2', savedAt: '2026-09-25T00:00:02.000Z' })
    expect(b.persisted).toBe(true)
    const a = filePendingSubmission(store, Q1, { id: 'q1', savedAt: '2026-09-25T00:00:01.000Z' })
    expect(a.persisted).toBe(true)
    // Neither write destroyed the other: both keys survive.
    const filings = loadFilings(store, 'A')
    expect(filings.map((filing) => filing.id).sort()).toEqual(['q1', 'q2'])
    expect(selectRecoveryCandidate(filings, 2)?.id).toBe('q1')
    expect(selectRecoveryCandidate(filings, 2)?.intents).toEqual(Q1.intents)
  })

  it('survives simultaneous same-tick filings with no loss', () => {
    const store = memStore()
    const [a, b] = [
      filePendingSubmission(store, Q1, { id: 'q1', savedAt: '2026-09-25T00:00:01.000Z' }),
      filePendingSubmission(store, Q2, { id: 'q2', savedAt: '2026-09-25T00:00:01.000Z' })
    ]
    expect(a.persisted).toBe(true)
    expect(b.persisted).toBe(true)
    const filings = loadFilings(store, 'A')
    expect(filings).toHaveLength(2)
    // Identical timestamps break deterministically on filing id.
    expect(selectRecoveryCandidate(filings, 2)?.id).toBe('q1')
  })

  it('marks only the refused filing and never elects it', () => {
    const store = memStore()
    filePendingSubmission(store, Q1, { id: 'q1', savedAt: '2026-09-25T00:00:01.000Z' })
    filePendingSubmission(store, Q2, { id: 'q2', savedAt: '2026-09-25T00:00:02.000Z' })
    expect(markSubmissionRefused(store, 'A', 'q2')).toBe(true)
    const filings = loadFilings(store, 'A')
    expect(filings.find((filing) => filing.id === 'q2')?.refused).toBe(true)
    expect(filings.find((filing) => filing.id === 'q1')?.refused).not.toBe(true)
    expect(selectRecoveryCandidate(filings, 2)?.id).toBe('q1')
    expect(markSubmissionRefused(store, 'A', 'missing')).toBe(false)
  })

  it('a refused original yields election to the surviving contender', () => {
    const store = memStore()
    filePendingSubmission(store, Q1, { id: 'q1', savedAt: '2026-09-25T00:00:01.000Z' })
    filePendingSubmission(store, Q2, { id: 'q2', savedAt: '2026-09-25T00:00:02.000Z' })
    expect(markSubmissionRefused(store, 'A', 'q1')).toBe(true)
    const filings = loadFilings(store, 'A')
    // Both records survive; the refused one is simply unelectable.
    expect(filings).toHaveLength(2)
    expect(selectRecoveryCandidate(filings, 2)?.id).toBe('q2')
  })

  it('retires exactly the committed filing, idempotently', () => {
    const store = memStore()
    filePendingSubmission(store, Q1, { id: 'q1', savedAt: '2026-09-25T00:00:01.000Z' })
    filePendingSubmission(store, Q2, { id: 'q2', savedAt: '2026-09-25T00:00:02.000Z' })
    retireSubmission(store, 'A', 'q1')
    retireSubmission(store, 'A', 'q1')
    const filings = loadFilings(store, 'A')
    expect(filings.map((filing) => filing.id)).toEqual(['q2'])
    retireSubmission(store, 'A', 'q2')
    expect(inspectFilings(store, 'A').status).toBe('absent')
  })

  it('keeps worlds separate', () => {
    const store = memStore()
    filePendingSubmission(store, Q1, { id: 'q1' })
    filePendingSubmission(store, { ...Q2, worldId: 'B', index: 3 }, { id: 'qb' })
    retireSubmission(store, 'A', 'q1')
    expect(loadFilings(store, 'A')).toEqual([])
    expect(loadFilings(store, 'B').map((filing) => filing.id)).toEqual(['qb'])
  })

  it('adopts pre-identity legacy records read-only', () => {
    const store = memStore()
    store.setItem(
      pendingKey('A'),
      JSON.stringify({
        worldId: 'A',
        index: 2,
        intents: Q1.intents,
        savedAt: '2026-09-25T00:00:01.000Z'
      })
    )
    store.setItem(
      contendersKey('A'),
      JSON.stringify([
        {
          worldId: 'A',
          index: 2,
          intents: Q2.intents,
          id: 'q2',
          savedAt: '2026-09-25T00:00:02.000Z'
        },
        'garbage'
      ])
    )
    const inspected = inspectFilings(store, 'A')
    // Readable filings are returned even though one contender entry is corrupt.
    expect(inspected.status).toBe('invalid')
    expect(inspected.filings).toHaveLength(2)
    expect(selectRecoveryCandidate(inspected.filings, 2)?.intents).toEqual(Q1.intents)
    // No migration write raced: the legacy bytes are untouched.
    expect(store.getItem(pendingKey('A'))).toContain('What news from the mill?')
  })

  it('distinguishes invalid, absent, and unavailable storage', () => {
    const store = memStore()
    expect(inspectFilings(store, 'A').status).toBe('absent')
    store.setItem(filingKey('A', 'bad'), '{not json')
    const invalid = inspectFilings(store, 'A')
    expect(invalid.status).toBe('invalid')
    expect(invalid.filings).toEqual([])
    // A read failure over existing data is unavailable, never absent.
    const existing = memStore()
    filePendingSubmission(existing, Q1, { id: 'q1' })
    const failingReads: SubmissionStorage = {
      getItem: () => {
        throw new Error('denied')
      },
      setItem: (key, value) => {
        existing.setItem(key, value)
      },
      removeItem: (key) => {
        existing.removeItem(key)
      },
      keys: (prefix) => existing.keys(prefix)
    }
    const blocked = inspectFilings(failingReads, 'A')
    expect(blocked.status).toBe('unavailable')
    expect(blocked.filings).toEqual([])
    expect(inspectFilings(throwingStore(), 'A').status).toBe('unavailable')
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
        intents: { 'char-wren': { family: 'communicate', snapshot_id: 'y', topic: 'no actor' } }
      },
      {
        worldId: 'A',
        index: 2,
        intents: {
          'char-wren': { family: 'communicate', character_id: 'char-wren', topic: 'no snapshot' }
        }
      }
    ]
    bad.forEach((record, i) => {
      store.setItem(filingKey('A', `bad-${i}`), JSON.stringify(record))
    })
    const inspected = inspectFilings(store, 'A')
    expect(inspected.status).toBe('invalid')
    expect(inspected.filings).toEqual([])
    expect(selectRecoveryCandidate(inspected.filings, 2)).toBeNull()
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

  it('reports memory-backed writes as session-only, never durable', () => {
    const store = sessionStore()
    const filed = filePendingSubmission(store, Q1, { id: 'q1' })
    expect(filed.persisted).toBe(false)
    expect(filed.record.durable).toBe(false)
    // Same-context reads work but stay session-only: never laundered.
    const filings = loadFilings(store, 'A')
    expect(filings).toHaveLength(1)
    expect(filings[0]?.durable).toBe(false)
  })

  it('flags the inaccessible-localStorage fallback as session-only', () => {
    vi.stubGlobal('localStorage', {
      getItem: () => null,
      setItem: () => {
        throw new Error('denied')
      },
      removeItem: () => undefined,
      length: 0,
      key: () => null
    })
    const first = defaultSubmissionStorage()
    expect(first.persistence).toBe('session')
    const filed = filePendingSubmission(first, Q1, { id: 'q1' })
    expect(filed.persisted).toBe(false)
    // A fresh controller receives a new empty context: absent, not durable.
    const second = defaultSubmissionStorage()
    expect(second.persistence).toBe('session')
    expect(inspectFilings(second, 'A').status).toBe('absent')
  })

  it('wraps a working localStorage as durable and enumerable', () => {
    const backing = new Map<string, string>()
    vi.stubGlobal('localStorage', {
      getItem: (key: string) => backing.get(key) ?? null,
      setItem: (key: string, value: string) => {
        backing.set(key, value)
      },
      removeItem: (key: string) => {
        backing.delete(key)
      },
      get length() {
        return backing.size
      },
      key: (index: number) => [...backing.keys()][index] ?? null
    })
    const store = defaultSubmissionStorage()
    expect(store.persistence).toBe('durable')
    const filed = filePendingSubmission(store, Q1, { id: 'q1' })
    expect(filed.persisted).toBe(true)
    expect(loadFilings(store, 'A')).toHaveLength(1)
  })

  it('mints unique filing identities', () => {
    expect(newFilingId()).toBeTruthy()
    expect(newFilingId()).not.toBe(newFilingId())
  })

  it('keeps readable durable records when the probe write fails', () => {
    const backing = new Map<string, string>()
    const seeded = memStore()
    const { record } = filePendingSubmission(seeded, Q1, { id: 'q1' })
    backing.set(filingKey('A', 'q1'), JSON.stringify({ ...record, durable: true }))
    vi.stubGlobal('localStorage', {
      getItem: (key: string) => backing.get(key) ?? null,
      setItem: () => {
        throw new Error('full')
      },
      removeItem: (key: string) => {
        backing.delete(key)
      },
      get length() {
        return backing.size
      },
      key: (index: number) => [...backing.keys()][index] ?? null
    })
    // Read availability survives the failed probe; only writes are session-flagged.
    const store = defaultSubmissionStorage()
    expect(store.persistence).toBe('session')
    const found = loadFilings(store, 'A')
    expect(found).toHaveLength(1)
    expect(found[0]?.durable).toBe(true)
    expect(found[0]?.intents).toEqual(Q1.intents)
    const filed = filePendingSubmission(store, Q2, { id: 'q2' })
    expect(filed.persisted).toBe(false)
    expect(filed.record.durable).toBe(false)
  })

  it('refuses shared writes without cross-context randomness', async () => {
    vi.stubGlobal('crypto', undefined)
    const now = vi.spyOn(Date, 'now').mockReturnValue(1727740000000)
    try {
      // Two independent module contexts, same clock, fresh counters.
      vi.resetModules()
      const modA = await import('./pendingSubmissions')
      const fileA = modA.filePendingSubmission
      vi.resetModules()
      const modB = await import('./pendingSubmissions')
      const store = memStore()
      const a = fileA(store, Q1)
      const b = modB.filePendingSubmission(store, Q2)
      // Both contexts mint the same weak identity — so neither writes it.
      expect(a.record.id).toBe(b.record.id)
      expect(a.persisted).toBe(false)
      expect(b.persisted).toBe(false)
      expect(store.keys('ember-vale.pending-submission.v1.')).toEqual([])
    } finally {
      now.mockRestore()
      vi.unstubAllGlobals()
    }
  })
})
