import { afterEach, describe, expect, it, vi } from 'vitest'
import { resetDraftMemoryForTests, useStoryDraft } from './useStoryDraft'
import type { NewStorySelections } from '../game/drafting'

interface Seen {
  method: string
  path: string
  body: unknown
  headers: Record<string, string>
}

let seen: Seen[] = []
let versions = new Map<string, number>()
let nextDraft = 0
let storyPosts: Array<{ body: unknown; key: string | null }> = []
let storyFailures: Error[] = []
let validOverride: boolean | null = null
/** When true, PATCH requests are held until released. */
let patchHold = false
let heldPatches: Array<() => void> = []
/** Draft ids whose GET load hangs until released. */
let heldGets = new Map<string, Array<() => void>>()

const SEL: NewStorySelections = {
  world: { presetId: 'w', presetRevision: 2 },
  cast: [],
  mode: { role: 'watcher' },
  title: 'T'
}

function draftOf(id: string): Record<string, unknown> {
  return {
    id,
    payload: {},
    current_step: 'review',
    version: versions.get(id) ?? 1,
    created_world_id: null,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z'
  }
}

function installFetch(): void {
  seen = []
  versions = new Map()
  nextDraft = 0
  storyPosts = []
  storyFailures = []
  validOverride = null
  patchHold = false
  heldPatches = []
  heldGets = new Map()
  resetDraftMemoryForTests()
  vi.stubGlobal(
    'fetch',
    vi.fn(async (rawUrl: string, init: RequestInit = {}) => {
      const url = new URL(rawUrl, 'http://test')
      const method = init.method ?? 'GET'
      const headers = (init.headers ?? {}) as Record<string, string>
      const body = init.body === undefined ? undefined : JSON.parse(String(init.body))
      seen.push({ method, path: url.pathname, body, headers })
      if (method === 'POST' && url.pathname === '/api/v1/story-drafts') {
        nextDraft += 1
        const id = `d-${nextDraft}`
        versions.set(id, 1)
        return json(draftOf(id))
      }
      if (method === 'PATCH' && url.pathname.startsWith('/api/v1/story-drafts/')) {
        if (patchHold) {
          await new Promise<void>((resolve) => heldPatches.push(resolve))
        }
        const id = url.pathname.split('/').at(-1) as string
        const next = (versions.get(id) ?? 1) + 1
        versions.set(id, next)
        return json(draftOf(id))
      }
      if (method === 'GET' && url.pathname.startsWith('/api/v1/story-drafts/')) {
        const id = url.pathname.split('/').at(-1) as string
        const gate = heldGets.get(id)
        if (gate) {
          await new Promise<void>((resolve) => gate.push(resolve))
        }
        return json(draftOf(id))
      }
      if (method === 'POST' && url.pathname.endsWith('/validate')) {
        return json({ valid: validOverride ?? true, issues: [] })
      }
      if (method === 'POST' && url.pathname === '/api/v1/stories') {
        const failure = storyFailures.shift()
        if (failure) throw failure
        storyPosts.push({ body, key: headers['Idempotency-Key'] ?? null })
        return json({ world_id: 'w1', replayed: false })
      }
      return json({})
    })
  )
}

function json(body: unknown): Response {
  return new Response(JSON.stringify(body), { status: 200 })
}

function fail(status: number, code: string, message: string): Response {
  return new Response(JSON.stringify({ error: { code, message } }), { status })
}

afterEach(() => {
  vi.unstubAllGlobals()
})

function storiesPosts(): Seen[] {
  return seen.filter((s) => s.method === 'POST' && s.path === '/api/v1/stories')
}

describe('useStoryDraft guarded workflow', () => {
  it('persists, validates, then creates with the acknowledged version', async () => {
    installFetch()
    const ctl = useStoryDraft()
    await ctl.openNew(SEL, 'world')
    const worldId = await ctl.createWorkflow(SEL, 'review')
    expect(worldId).toBe('w1')
    expect(storiesPosts()).toHaveLength(1)
    expect(storiesPosts()[0].body).toMatchObject({ draft_id: expect.any(String) })
    expect((storiesPosts()[0].body as Record<string, unknown>)['expected_draft_version']).toBe(2)
    expect(storiesPosts()[0].headers['Idempotency-Key']).toBeTruthy()
  })

  it('failed save means zero create requests and kept input', async () => {
    installFetch()
    const ctl = useStoryDraft()
    await ctl.openNew(SEL, 'world')
    vi.stubGlobal(
      'fetch',
      vi.fn(async (rawUrl: string, init: RequestInit = {}) => {
        const url = new URL(rawUrl, 'http://test')
        const method = init.method ?? 'GET'
        seen.push({
          method,
          path: url.pathname,
          body: init.body === undefined ? undefined : JSON.parse(String(init.body)),
          headers: (init.headers ?? {}) as Record<string, string>
        })
        if (method === 'PATCH') return fail(500, 'HTTP_500', 'boom')
        return json(draftOf('d-x'))
      })
    )
    const worldId = await ctl.createWorkflow(SEL, 'review')
    expect(worldId).toBeNull()
    expect(storiesPosts()).toHaveLength(0)
    expect(ctl.notice.value).toBeTruthy()
    expect(ctl.saveState.value).toBe('failed')
  })

  it('stale draft never auto-creates from server state', async () => {
    installFetch()
    const ctl = useStoryDraft()
    await ctl.openNew(SEL, 'world')
    vi.stubGlobal(
      'fetch',
      vi.fn(async (rawUrl: string, init: RequestInit = {}) => {
        const url = new URL(rawUrl, 'http://test')
        const method = init.method ?? 'GET'
        seen.push({
          method,
          path: url.pathname,
          body: init.body === undefined ? undefined : JSON.parse(String(init.body)),
          headers: (init.headers ?? {}) as Record<string, string>
        })
        if (method === 'PATCH') return fail(409, 'VERSION_CONFLICT', 'stale')
        if (method === 'GET' && url.pathname.startsWith('/api/v1/story-drafts/')) {
          return json(draftOf('d-server'))
        }
        return json({})
      })
    )
    const worldId = await ctl.createWorkflow(SEL, 'review')
    expect(worldId).toBeNull()
    expect(storiesPosts()).toHaveLength(0)
    expect(ctl.notice.value).toContain('changed elsewhere')
  })

  it('invalid acknowledged draft stops before creation', async () => {
    installFetch()
    validOverride = false
    const ctl = useStoryDraft()
    await ctl.openNew(SEL, 'world')
    const worldId = await ctl.createWorkflow(SEL, 'review')
    expect(worldId).toBeNull()
    expect(storiesPosts()).toHaveLength(0)
  })

  it('rapid double-click submits exactly once', async () => {
    installFetch()
    const ctl = useStoryDraft()
    await ctl.openNew(SEL, 'world')
    const [first, second] = await Promise.all([
      ctl.createWorkflow(SEL, 'review'),
      ctl.createWorkflow(SEL, 'review')
    ])
    expect([first, second].filter(Boolean)).toHaveLength(1)
    expect(storiesPosts()).toHaveLength(1)
  })

  it('an ambiguous create replays the frozen submission instead of a fresh save', async () => {
    installFetch()
    storyFailures = [new Error('REQUEST_TIMEOUT'), new Error('REQUEST_TIMEOUT')]
    const ctl = useStoryDraft()
    await ctl.openNew(SEL, 'world')
    const first = await ctl.createWorkflow(SEL, 'review')
    expect(first).toBeNull()
    expect(ctl.ambiguous.value).toBe(true)
    expect(ctl.createError.value).toContain('replays')
    const patchesAfterFirst = seen.filter((s) => s.method === 'PATCH').length
    const second = await ctl.createWorkflow(SEL, 'review')
    expect(second).toBe('w1')
    expect(ctl.ambiguous.value).toBe(false)
    // No fresh save happened for the retry: same version, same key.
    expect(seen.filter((s) => s.method === 'PATCH')).toHaveLength(patchesAfterFirst)
    const keys = seen
      .filter((s) => s.method === 'POST' && s.path === '/api/v1/stories')
      .map((s) => s.headers['Idempotency-Key'])
    expect(keys).toHaveLength(3)
    expect(new Set(keys).size).toBe(1)
  })

  it('a definitive create failure clears the ambiguity', async () => {
    installFetch()
    const ctl = useStoryDraft()
    await ctl.openNew(SEL, 'world')
    vi.stubGlobal(
      'fetch',
      vi.fn(async (rawUrl: string, init: RequestInit = {}) => {
        const url = new URL(rawUrl, 'http://test')
        const method = init.method ?? 'GET'
        seen.push({
          method,
          path: url.pathname,
          body: init.body === undefined ? undefined : JSON.parse(String(init.body)),
          headers: (init.headers ?? {}) as Record<string, string>
        })
        if (method === 'PATCH') {
          const id = url.pathname.split('/').at(-1) as string
          versions.set(id, (versions.get(id) ?? 1) + 1)
          return json(draftOf(id))
        }
        if (method === 'POST' && url.pathname.endsWith('/validate')) {
          return json({ valid: true, issues: [] })
        }
        if (method === 'POST' && url.pathname === '/api/v1/stories') {
          return fail(500, 'HTTP_500', 'boom')
        }
        return json(draftOf('d-x'))
      })
    )
    const worldId = await ctl.createWorkflow(SEL, 'review')
    expect(worldId).toBeNull()
    expect(ctl.ambiguous.value).toBe(false)
  })

  it('tracks acknowledged state across saves and failures', async () => {
    installFetch()
    const ctl = useStoryDraft()
    await ctl.openNew(SEL, 'world')
    expect(ctl.saveState.value).toBe('clean')
    expect(ctl.isAcked(SEL, 'world')).toBe(true)
    expect(ctl.isAcked({ ...SEL, title: 'Changed' }, 'world')).toBe(false)
    const ok = await ctl.save(SEL, 'review')
    expect(ok).toBe(true)
    expect(ctl.saveState.value).toBe('clean')
    expect(ctl.isAcked(SEL, 'review')).toBe(true)
  })

  it('timeout retry reuses the exact idempotency key', async () => {
    installFetch()
    storyFailures = [new Error('REQUEST_TIMEOUT')]
    const ctl = useStoryDraft()
    await ctl.openNew(SEL, 'world')
    const worldId = await ctl.createWorkflow(SEL, 'review')
    expect(worldId).toBe('w1')
    expect(storyPosts).toHaveLength(1)
    const keys = seen
      .filter((s) => s.method === 'POST' && s.path === '/api/v1/stories')
      .map((s) => s.headers['Idempotency-Key'])
    expect(keys).toHaveLength(2)
    expect(keys[0]).toBeTruthy()
    expect(keys[0]).toBe(keys[1])
  })

  it('overlapping saves serialize with chained versions', async () => {
    installFetch()
    const ctl = useStoryDraft()
    await ctl.openNew(SEL, 'world')
    const draftId = ctl.draft.value?.id as string
    versions.set(draftId, 1)
    const [a, b] = await Promise.all([ctl.save(SEL, 'world'), ctl.save(SEL, 'characters')])
    expect(a).toBe(true)
    expect(b).toBe(true)
    const patches = seen.filter((s) => s.method === 'PATCH')
    expect(patches).toHaveLength(2)
    expect((patches[0].body as Record<string, unknown>)['expected_version']).toBe(1)
    expect((patches[1].body as Record<string, unknown>)['expected_version']).toBe(2)
  })

  function storyTargets(): Array<Record<string, unknown>> {
    return storiesPosts().map((s) => s.body as Record<string, unknown>)
  }

  it("ambiguous A, then B: Begin B never sends A's receipt", async () => {
    installFetch()
    storyFailures = [new Error('REQUEST_TIMEOUT'), new Error('REQUEST_TIMEOUT')]
    const ctl = useStoryDraft()
    await ctl.openNew(SEL, 'world')
    expect(await ctl.createWorkflow(SEL, 'review')).toBeNull()
    expect(ctl.ambiguous.value).toBe(true)

    await ctl.openExisting('d-B')
    expect(ctl.draft.value?.id).toBe('d-B')
    expect(ctl.ambiguous.value).toBe(false)
    expect(await ctl.createWorkflow(SEL, 'review')).toBe('w1')

    // A, A, then B — B's Begin carries only B's identity.
    expect(storyTargets().map((b) => b['draft_id'])).toEqual(['d-1', 'd-1', 'd-B'])
    const bTarget = storyTargets()[2]
    expect(bTarget['expected_draft_version']).toBe(2)
    expect(ctl.createError.value).toBeNull()
  })

  it('returning to ambiguous A replays exactly the original receipt', async () => {
    installFetch()
    storyFailures = [new Error('REQUEST_TIMEOUT'), new Error('REQUEST_TIMEOUT')]
    const ctl = useStoryDraft()
    await ctl.openNew(SEL, 'world')
    expect(await ctl.createWorkflow(SEL, 'review')).toBeNull()
    const firstKeys = storiesPosts().map((s) => s.headers['Idempotency-Key'])

    await ctl.openExisting('d-B')
    await ctl.openExisting('d-1')
    expect(ctl.ambiguous.value).toBe(true)
    const patchesBefore = seen.filter((s) => s.method === 'PATCH').length
    expect(await ctl.createWorkflow(SEL, 'review')).toBe('w1')
    expect(ctl.ambiguous.value).toBe(false)
    // No fresh save: replay carries A's original version and key.
    expect(seen.filter((s) => s.method === 'PATCH')).toHaveLength(patchesBefore)
    const replay = storyTargets().at(-1) as Record<string, unknown>
    expect(replay['draft_id']).toBe('d-1')
    expect(replay['expected_draft_version']).toBe(2)
    expect(storiesPosts().at(-1)?.headers['Idempotency-Key']).toBe(firstKeys[0])
  })

  it('a reopened wizard replays the receipt without fresh identity', async () => {
    installFetch()
    storyFailures = [new Error('REQUEST_TIMEOUT'), new Error('REQUEST_TIMEOUT')]
    const first = useStoryDraft()
    await first.openNew(SEL, 'world')
    expect(await first.createWorkflow(SEL, 'review')).toBeNull()
    const originalKey = storiesPosts()[0].headers['Idempotency-Key']
    const patchesBefore = seen.filter((s) => s.method === 'PATCH').length

    // Leaving and reopening the wizard: a new controller instance, same
    // module-level receipt. Begin must replay, not re-save/re-key.
    const second = useStoryDraft()
    await second.openExisting('d-1')
    expect(second.ambiguous.value).toBe(true)
    expect(await second.createWorkflow(SEL, 'review')).toBe('w1')
    expect(seen.filter((s) => s.method === 'PATCH')).toHaveLength(patchesBefore)
    const replay = storyTargets().at(-1) as Record<string, unknown>
    expect(replay['draft_id']).toBe('d-1')
    expect(storiesPosts().at(-1)?.headers['Idempotency-Key']).toBe(originalKey)
  })

  it("queued A saves behind B's navigation never touch B", async () => {
    installFetch()
    patchHold = true
    const ctl = useStoryDraft()
    await ctl.openNew(SEL, 'world')
    const pendingA = Promise.all([ctl.save(SEL, 'world'), ctl.save(SEL, 'characters')])
    await vi.waitFor(() => expect(heldPatches.length).toBeGreaterThan(0))
    await ctl.openExisting('d-B')
    patchHold = false
    heldPatches.forEach((release) => release())
    const [a, b] = await pendingA
    expect(a).toBe(true)
    expect(b).toBe(true)
    // Both PATCHes targeted A with A's input; B was never patched and its
    // mounted state was never replaced by A's responses.
    const patches = seen.filter((s) => s.method === 'PATCH')
    expect(patches).toHaveLength(2)
    expect(patches.every((p) => p.path.endsWith('/d-1'))).toBe(true)
    expect(ctl.draft.value?.id).toBe('d-B')
    expect(ctl.draft.value?.version).toBe(1)
  })

  it('a slow A load resolving after B leaves B active', async () => {
    installFetch()
    heldGets.set('d-A', [])
    const ctl = useStoryDraft()
    const pendingA = ctl.openExisting('d-A')
    await ctl.openExisting('d-B')
    expect(ctl.draft.value?.id).toBe('d-B')
    heldGets.get('d-A')?.forEach((release) => release())
    await pendingA
    expect(ctl.draft.value?.id).toBe('d-B')
    expect(ctl.draft.value?.version).toBe(1)
  })
})
