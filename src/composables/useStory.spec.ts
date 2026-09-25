import { afterEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'
import { useStory } from './useStory'
import {
  filePendingSubmission,
  inspectFilings,
  loadFilings,
  pendingKey,
  type SubmissionStorage
} from './pendingSubmissions'
import type { Role } from '../api/http'

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

interface Seen {
  method: string
  path: string
  query: Record<string, string>
  body: unknown
  headers: Record<string, string>
}

let seen: Seen[] = []
/** Gates: story-id-scoped detail requests hang until released (lifecycle test). */
let gatedStories = new Set<string>()
let releaseGates: Array<() => void> = []
/** One-shot fetch failures keyed by `METHOD path`. */
let failures = new Map<string, { status: number; code: string; message: string }>()
/** One-shot fetch rejections keyed by `METHOD path`. */
let rejections = new Map<string, Error>()
/** Activity members returned per story. */
let membersByStory = new Map<string, unknown[]>()
/** Stranded open runs reported per story; an entry without an index mimics an older API. */
let statusByStory = new Map<string, { id: string; index?: number; state: string }>()
/** Committed beat index per story (advance commits move it). */
let indexByStory = new Map<string, number>()
/** Held advance POSTs, released manually with a chosen outcome. */
let heldAdvances: Array<{
  resolve: (res: Response) => void
  reject: (err: Error) => void
}> = []
/** Held activity-list GETs for reconcile-scoping tests. */
let heldActivityLists: Array<() => void> = []
/** When true, new advance POSTs / activity-list GETs are held. */
let advanceHold = false
let activityListHold = false
/** When true, advance POSTs report an already-committed beat. */
let advanceDuplicate = false
type TimelineMode = 'small' | 'big' | 'empty-advance' | 'stuck'
let timelineMode: TimelineMode = 'small'

function detailOf(id: string, index?: number): Record<string, unknown> {
  return {
    story_id: id,
    world_id: id,
    title: `Tale ${id}`,
    world_name: 'Ember Vale',
    mode: 'player',
    day: 1,
    phase: 'morning',
    absolute_index: index ?? indexByStory.get(id) ?? 1,
    status: 'in_progress',
    metadata_version: 1
  }
}

function setupOf(id: string): Record<string, unknown> {
  return {
    story_id: id,
    world_id: id,
    provenance: 'created',
    content_hash: 'abc',
    created_at: '2026-01-01T00:00:00Z',
    payload: {
      mode: {
        role: 'player',
        controlled_cast_key: 'wren',
        controlled_character_id: 'char-wren'
      },
      cast: [{ instance_key: 'wren', name: 'Wren', runtime_character_id: 'char-wren' }]
    }
  }
}

function grantOf(id: string): Record<string, unknown> {
  return {
    id: 'grant-1',
    world_id: id,
    role: 'player',
    character_id: 'char-wren',
    granted_absolute: 0,
    version: 1
  }
}

/** Ash sorts first alphabetically; the controlled Wren must still win. */
function mapOf(id: string): Record<string, unknown> {
  return {
    world_id: id,
    places: [
      {
        id: 'loc-hearth',
        name: 'Hearth',
        region: 'vale',
        discovered: true,
        occupant_ids: ['char-ash', 'char-wren'],
        occupants: ['Ash', 'Wren'],
        routes: [{ to_location_id: 'loc-market' }]
      },
      {
        id: 'loc-market',
        name: 'Market',
        region: 'vale',
        discovered: true,
        occupant_ids: [],
        occupants: [],
        routes: []
      }
    ]
  }
}

function timelinePage(
  id: string,
  entries: Array<Record<string, unknown>>,
  nextAfter: number,
  hasMore: boolean
): Record<string, unknown> {
  return { world_id: id, entries, total: entries.length, next_after: nextAfter, has_more: hasMore }
}

const E1 = { sequence: 1, event_id: 'e1', event_type: 'beat_opened', absolute_index: 1 }
const E2 = { sequence: 2, event_id: 'e2', event_type: 'action_resolved', absolute_index: 1 }

function installFetch(): void {
  seen = []
  gatedStories = new Set()
  releaseGates = []
  failures = new Map()
  rejections = new Map()
  membersByStory = new Map()
  statusByStory = new Map()
  indexByStory = new Map()
  heldAdvances = []
  heldActivityLists = []
  timelineMode = 'small'
  advanceHold = false
  activityListHold = false
  advanceDuplicate = false
  vi.stubGlobal(
    'fetch',
    vi.fn(async (rawUrl: string, init: RequestInit = {}) => {
      const url = new URL(rawUrl, 'http://test')
      const method = init.method ?? 'GET'
      const key = `${method} ${url.pathname}`
      const body = init.body === undefined ? undefined : JSON.parse(String(init.body))
      seen.push({
        method,
        path: url.pathname,
        query: Object.fromEntries(url.searchParams.entries()),
        body,
        headers: (init.headers ?? {}) as Record<string, string>
      })
      const rejected = rejections.get(key)
      if (rejected) {
        rejections.delete(key)
        throw rejected
      }
      const failed = failures.get(key)
      if (failed) {
        failures.delete(key)
        return new Response(
          JSON.stringify({ error: { code: failed.code, message: failed.message } }),
          { status: failed.status }
        )
      }
      const segs = url.pathname.split('/')
      const id =
        url.searchParams.get('world_id') ??
        (segs[3] === 'stories' && segs[4] ? segs[4] : undefined) ??
        'A'
      if (gatedStories.has(id) && url.pathname.endsWith(`/stories/${id}`) && method === 'GET') {
        await new Promise<void>((resolve) => releaseGates.push(resolve))
      }
      if (method === 'POST' && url.pathname.endsWith('/open')) {
        return json(detailOf(id))
      }
      if (method === 'POST' && url.pathname === '/api/v1/stage1/advance') {
        if (advanceHold) {
          return new Promise<Response>((resolve, reject) => {
            heldAdvances.push({ resolve, reject })
          })
        }
        const sent = (body ?? {}) as Record<string, unknown>
        const target = sent['absolute_index']
        const wid = sent['world_id']
        if (typeof target === 'number' && typeof wid === 'string') {
          indexByStory.set(wid, target)
        }
        return json({
          world_id: id,
          absolute_index: target ?? 2,
          duplicate: advanceDuplicate
        })
      }
      if (method === 'POST' && url.pathname === '/api/v1/stage2/activities') {
        return json({ id: 'act-1', status: 'active' })
      }
      if (method === 'GET' && url.pathname === '/api/v1/stage2/activities') {
        if (activityListHold) {
          await new Promise<void>((resolve) => heldActivityLists.push(resolve))
        }
        return json({ world_id: id, members: membersByStory.get(id) ?? [] })
      }
      if (method === 'GET' && url.pathname === '/api/v1/stage2/timeline') {
        const after = Number(url.searchParams.get('after') ?? 0)
        if (timelineMode === 'big') {
          const end = Math.min(after + 50, 1300)
          const batch = []
          for (let i = after + 1; i <= end; i += 1) {
            batch.push({
              sequence: i,
              event_id: `be${i}`,
              event_type: 'beat_opened',
              absolute_index: 1
            })
          }
          return json({
            world_id: id,
            entries: batch,
            total: 1300,
            next_after: end,
            has_more: end < 1300
          })
        }
        if (timelineMode === 'stuck') {
          return json({ world_id: id, entries: [], total: 9, next_after: after, has_more: true })
        }
        if (timelineMode === 'empty-advance') {
          if (after < 3) return json(timelinePage(id, [], 3, true))
          if (after < 5) return json(timelinePage(id, [E1], 5, true))
        }
        if (after === 0) return json(timelinePage(id, [E1], 5, true))
        return json(timelinePage(id, [E2], 9, false))
      }
      if (method === 'GET' && url.pathname === '/api/v1/stage2/map') return json(mapOf(id))
      if (method === 'GET' && url.pathname === '/api/v1/simulation/status') {
        const open = statusByStory.get(id)
        if (!open) return json({ world_id: id, absolute_index: 2 })
        return json({
          world_id: id,
          absolute_index: 2,
          open_run_id: open.id,
          ...(open.index === undefined ? {} : { open_run_index: open.index }),
          open_run_state: open.state
        })
      }
      if (method === 'GET' && url.pathname.endsWith('/setup')) return json(setupOf(id))
      if (method === 'GET' && url.pathname === '/api/v1/stage2/roles') return json(grantOf(id))
      if (method === 'GET' && url.pathname.startsWith('/api/v1/stories/')) {
        return json(detailOf(id))
      }
      return json({})
    })
  )
}

function json(body: unknown): Response {
  return new Response(JSON.stringify(body), { status: 200 })
}

afterEach(() => {
  vi.unstubAllGlobals()
})

function opensFor(id: string): Seen[] {
  return seen.filter((s) => s.method === 'POST' && s.path === `/api/v1/stories/${id}/open`)
}

describe('useStory room', () => {
  it('pages through the server cursor instead of re-reading page one', async () => {
    installFetch()
    const story = useStory('A', 'watcher')
    await story.load()
    expect(story.loadError.value).toBeNull()
    expect(story.entries.value.map((e) => e.event_id)).toEqual(['e1', 'e2'])
    const afters = seen
      .filter((s) => s.path === '/api/v1/stage2/timeline')
      .map((s) => s.query['after'])
    expect(afters[0]).toBe('0')
    expect(afters).toContain('5')
    expect(story.hasMore.value).toBe(false)
  })

  it('resolves the controlled actor from the grant, not alphabetical order', async () => {
    installFetch()
    const story = useStory('A', 'watcher')
    await story.load()
    expect(story.effectiveRole.value).toBe('player')
    expect(story.controlledRuntimeId.value).toBe('char-wren')
    expect(story.grantLoaded.value).toBe(true)
  })

  it('sends the grant role and controlled id on mutation headers', async () => {
    installFetch()
    // Mirror the room wiring: headers follow the grant-derived effective
    // role and controlled runtime id, never an alphabetical map pick.
    const roleIn = ref<Role>('watcher')
    const charIn = ref<string | undefined>(undefined)
    const story = useStory('A', roleIn, charIn)
    await story.load()
    roleIn.value = story.effectiveRole.value
    charIn.value = story.controlledRuntimeId.value ?? undefined
    await story.advance()
    const advance = seen.find((s) => s.path === '/api/v1/stage1/advance')
    expect(advance?.headers['X-Worldsim-Role']).toBe('player')
    expect(advance?.headers['X-Worldsim-Character']).toBe('char-wren')
    expect(advance?.body as Record<string, unknown>).not.toHaveProperty('player_intents')
  })

  it('files a player attempt with the beat when one is given', async () => {
    installFetch()
    const story = useStory('A', 'watcher')
    await story.load()
    const intents = {
      'char-wren': {
        family: 'communicate',
        character_id: 'char-wren',
        snapshot_id: '00000000-0000-0000-0000-000000000000',
        target_character_id: 'char-ash',
        topic: 'What news from the mill?'
      }
    }
    await story.advance(intents)
    const advance = seen.find((s) => s.path === '/api/v1/stage1/advance')
    expect((advance?.body as Record<string, unknown>)['player_intents']).toEqual(intents)
  })

  it('records the room open exactly once without advancing gameplay', async () => {
    installFetch()
    const story = useStory('A', 'watcher')
    await story.load()
    await story.load()
    expect(opensFor('A')).toHaveLength(1)
    expect(seen.filter((s) => s.path === '/api/v1/stage1/advance')).toHaveLength(0)
  })

  it('treats a matching active member as an underway journey', async () => {
    installFetch()
    membersByStory.set('A', [
      {
        id: 'act-9',
        character_id: 'char-wren',
        kind: 'travel',
        status: 'active',
        to_location_id: 'loc-market'
      }
    ])
    failures.set('POST /api/v1/stage2/activities', {
      status: 409,
      code: 'PRECONDITION_FAILED',
      message: 'already running'
    })
    const story = useStory('A', 'watcher')
    await story.load()
    const ok = await story.travel('char-wren', 'loc-market')
    expect(ok).toBe(false)
    expect(story.notice.value?.kind).toBe('info')
    expect(story.notice.value?.text).toContain('already underway')
  })

  it('preserves the genuine failure message when no activity matches', async () => {
    installFetch()
    membersByStory.set('A', [])
    failures.set('POST /api/v1/stage2/activities', {
      status: 409,
      code: 'PRECONDITION_FAILED',
      message: 'no route from Hearth to Deepwood'
    })
    const story = useStory('A', 'watcher')
    await story.load()
    await story.travel('char-wren', 'loc-deepwood')
    expect(story.notice.value?.kind).toBe('error')
    expect(story.notice.value?.text).toContain('no route')
  })

  it('reconciles a timed-out start instead of retrying blindly', async () => {
    installFetch()
    membersByStory.set('A', [
      {
        id: 'act-9',
        character_id: 'char-wren',
        kind: 'travel',
        status: 'active',
        to_location_id: 'loc-market'
      }
    ])
    rejections.set('POST /api/v1/stage2/activities', new Error('REQUEST_TIMEOUT'))
    const story = useStory('A', 'watcher')
    await story.load()
    await story.travel('char-wren', 'loc-market')
    const starts = seen.filter((s) => s.path === '/api/v1/stage2/activities' && s.method === 'POST')
    expect(starts).toHaveLength(1)
    expect(story.notice.value?.text).toContain('already underway')
  })

  it('ignores a late previous-story response after a route switch', async () => {
    installFetch()
    gatedStories.add('A')
    const id = ref('A')
    const story = useStory(id, 'watcher')
    const pendingA = story.load()
    id.value = 'B'
    await story.load()
    expect(story.detail.value?.world_id).toBe('B')
    releaseGates.forEach((release) => release())
    await pendingA
    expect(story.detail.value?.world_id).toBe('B')
    await story.advance()
    const advance = seen.filter((s) => s.path === '/api/v1/stage1/advance').at(-1)
    expect((advance?.body as Record<string, unknown>)['world_id']).toBe('B')
    expect(opensFor('A')).toHaveLength(0)
    expect(opensFor('B')).toHaveLength(1)
  })

  function advancePosts(): Seen[] {
    return seen.filter((s) => s.path === '/api/v1/stage1/advance')
  }

  function advanceBody(post: Seen): Record<string, unknown> {
    return post.body as Record<string, unknown>
  }

  it('a timed-out A advance never retries into B after navigation', async () => {
    installFetch()
    advanceHold = true
    const id = ref('A')
    const story = useStory(id, 'watcher')
    await story.load()
    const pending = story.advance()
    await vi.waitFor(() => expect(heldAdvances).toHaveLength(1))
    id.value = 'B'
    await story.load()
    heldAdvances[0].reject(new Error('REQUEST_TIMEOUT'))
    await expect(pending).resolves.toBe(false)
    const posts = advancePosts()
    expect(posts).toHaveLength(1)
    expect(advanceBody(posts[0])['world_id']).toBe('A')
    expect(advanceBody(posts[0])['absolute_index']).toBe(2)
    expect(story.advancing.value).toBe(false)
  })

  it('a timed-out advance never retries after disposal', async () => {
    installFetch()
    advanceHold = true
    const story = useStory('A', 'watcher')
    await story.load()
    const pending = story.advance()
    await vi.waitFor(() => expect(heldAdvances).toHaveLength(1))
    story.cancel()
    heldAdvances[0].reject(new Error('REQUEST_TIMEOUT'))
    await expect(pending).resolves.toBe(false)
    expect(advancePosts()).toHaveLength(1)
    expect(story.advancing.value).toBe(false)
  })

  it('a same-story timeout retries the frozen world, index, role and actor', async () => {
    installFetch()
    const roleIn = ref<Role>('player')
    const charIn = ref<string | undefined>('char-wren')
    const story = useStory('A', roleIn, charIn)
    await story.load()
    advanceHold = true
    const pending = story.advance()
    await vi.waitFor(() => expect(heldAdvances).toHaveLength(1))
    advanceHold = false
    heldAdvances[0].reject(new Error('REQUEST_TIMEOUT'))
    await expect(pending).resolves.toBe(true)
    const posts = advancePosts()
    expect(posts).toHaveLength(2)
    for (const post of posts) {
      expect(advanceBody(post)['world_id']).toBe('A')
      expect(advanceBody(post)['absolute_index']).toBe(2)
      expect(post.headers['X-Worldsim-Role']).toBe('player')
      expect(post.headers['X-Worldsim-Character']).toBe('char-wren')
    }
  })

  it('a retry landing mid-execution reports committing, not a raw 409', async () => {
    installFetch()
    const story = useStory('A', 'watcher')
    await story.load()
    advanceHold = true
    const pending = story.advance()
    await vi.waitFor(() => expect(heldAdvances).toHaveLength(1))
    advanceHold = false
    failures.set('POST /api/v1/stage1/advance', {
      status: 409,
      code: 'PRECONDITION_FAILED',
      message: 'phase:2 is already executing'
    })
    heldAdvances[0].reject(new Error('REQUEST_TIMEOUT'))
    await expect(pending).resolves.toBe(false)
    expect(advancePosts()).toHaveLength(2)
    expect(story.notice.value).toEqual({
      kind: 'info',
      text: 'That beat is already committing — its result is not in yet.'
    })
  })

  it('a retry with words landing mid-execution names the filed attempt', async () => {
    installFetch()
    const story = useStory('A', 'watcher', undefined, memStore())
    await story.load()
    advanceHold = true
    const pending = story.advance({
      'char-wren': {
        family: 'communicate',
        character_id: 'char-wren',
        snapshot_id: '00000000-0000-0000-0000-000000000000',
        target_character_id: 'char-ash',
        topic: 'What news from the mill?'
      }
    })
    await vi.waitFor(() => expect(heldAdvances).toHaveLength(1))
    advanceHold = false
    failures.set('POST /api/v1/stage1/advance', {
      status: 409,
      code: 'PRECONDITION_FAILED',
      message: 'phase:2 is already executing'
    })
    heldAdvances[0].reject(new Error('REQUEST_TIMEOUT'))
    await expect(pending).resolves.toBe(false)
    expect(story.notice.value).toEqual({
      kind: 'info',
      text: 'That beat is already committing — acceptance is unconfirmed, so your question is kept. If it does not appear, ask again with the next beat.'
    })
    expect(story.notice.value?.text ?? '').not.toContain('already filed')
  })

  it('a duplicate reconciliation is not a fresh commit', async () => {
    installFetch()
    advanceDuplicate = true
    const story = useStory('A', 'watcher')
    await story.load()
    await expect(story.advance()).resolves.toBe(false)
    expect(story.notice.value?.kind).toBe('info')
  })

  it('a version conflict refreshes without a fresh commit', async () => {
    installFetch()
    failures.set('POST /api/v1/stage1/advance', {
      status: 409,
      code: 'VERSION_CONFLICT',
      message: 'world changed underfoot'
    })
    const story = useStory('A', 'watcher')
    await story.load()
    await expect(story.advance()).resolves.toBe(false)
    expect(story.notice.value?.kind).toBe('info')
  })

  it('travel reconciliation after navigation reads A, never B', async () => {
    installFetch()
    activityListHold = true
    failures.set('POST /api/v1/stage2/activities', {
      status: 409,
      code: 'PRECONDITION_FAILED',
      message: 'busy'
    })
    const id = ref('A')
    const story = useStory(id, 'watcher')
    await story.load()
    const pending = story.travel('char-wren', 'loc-market')
    await vi.waitFor(() => expect(heldActivityLists).toHaveLength(1))
    id.value = 'B'
    await story.load()
    membersByStory.set('A', [
      {
        id: 'act-9',
        character_id: 'char-wren',
        kind: 'travel',
        status: 'active',
        to_location_id: 'loc-market'
      }
    ])
    activityListHold = false
    heldActivityLists.forEach((release) => release())
    await pending
    const lists = seen.filter((s) => s.method === 'GET' && s.path === '/api/v1/stage2/activities')
    expect(lists.length).toBeGreaterThan(0)
    expect(lists.every((s) => s.query['world_id'] === 'A')).toBe(true)
    expect(story.notice.value).toBeNull()
    expect(story.traveling.value).toBe(false)
  })

  it('re-entering A after an ambiguous timeout continues without duplication', async () => {
    installFetch()
    advanceHold = true
    const id = ref('A')
    const story = useStory(id, 'watcher')
    await story.load()
    const pending = story.advance()
    await vi.waitFor(() => expect(heldAdvances).toHaveLength(1))
    id.value = 'B'
    await story.load()
    // The server committed A's beat behind the timeout.
    indexByStory.set('A', 2)
    heldAdvances[0].reject(new Error('REQUEST_TIMEOUT'))
    await expect(pending).resolves.toBe(false)
    id.value = 'A'
    await story.load()
    expect(story.detail.value?.absolute_index).toBe(2)
    advanceHold = false
    await story.advance()
    const posts = advancePosts()
    expect(posts).toHaveLength(2)
    const last = posts.at(-1) as Seen
    expect(advanceBody(last)['world_id']).toBe('A')
    expect(advanceBody(last)['absolute_index']).toBe(3)
  })

  it('reaches events beyond the page cap through Load more', async () => {
    installFetch()
    timelineMode = 'big'
    const story = useStory('A', 'watcher')
    await story.load()
    expect(story.entries.value).toHaveLength(1250)
    expect(story.hasMore.value).toBe(true)
    expect(story.cursor.value).toBe(1250)
    await story.loadMore()
    expect(story.entries.value).toHaveLength(1300)
    expect(story.hasMore.value).toBe(false)
    expect(story.loadingMore.value).toBe(false)
  })

  it('follows an empty filtered page via its advancing cursor', async () => {
    installFetch()
    timelineMode = 'empty-advance'
    const story = useStory('A', 'watcher')
    await story.load()
    expect(story.entries.value.map((e) => e.event_id)).toEqual(['e1', 'e2'])
    const afters = seen
      .filter((s) => s.path === '/api/v1/stage2/timeline')
      .map((s) => s.query['after'])
    expect(afters).toContain('3')
  })

  it('a no-progress cursor terminates instead of looping', async () => {
    installFetch()
    timelineMode = 'stuck'
    const story = useStory('A', 'watcher')
    await story.load()
    const calls = seen.filter((s) => s.path === '/api/v1/stage2/timeline')
    expect(calls).toHaveLength(2)
    expect(story.entries.value).toHaveLength(0)
    expect(story.hasMore.value).toBe(true)
  })

  it('names a stranded beat from the simulation status on load', async () => {
    installFetch()
    statusByStory.set('A', { id: 'run-9', index: 2, state: 'scenes_assembled' })
    const story = useStory('A', 'watcher')
    await story.load()
    expect(story.recoveryState.value).toBe('open')
    expect(story.openRun.value).toEqual({
      id: 'run-9',
      worldId: 'A',
      index: 2,
      state: 'scenes_assembled'
    })
    // Read-only: learning the state starts no beat.
    expect(seen.filter((s) => s.path === '/api/v1/stage1/advance')).toHaveLength(0)
  })

  it('a failed status read is unresolved, never clear', async () => {
    installFetch()
    failures.set('GET /api/v1/simulation/status', {
      status: 500,
      code: 'INTERNAL',
      message: 'status unavailable'
    })
    const story = useStory('A', 'watcher')
    await story.load()
    expect(story.recoveryState.value).toBe('unknown')
    expect(story.openRun.value).toBeNull()
    // The room still loads: an unknown room is usable for reads, not beats.
    expect(story.loadError.value).toBeNull()
    expect(story.entries.value).toHaveLength(2)
  })

  it('an open run without an index stays unresolved', async () => {
    installFetch()
    statusByStory.set('A', { id: 'run-9', state: 'scenes_assembled' })
    const story = useStory('A', 'watcher')
    await story.load()
    expect(story.recoveryState.value).toBe('unknown')
    expect(story.openRun.value).toBeNull()
  })

  it('resumeBeat without a stranded beat starts nothing', async () => {
    installFetch()
    const story = useStory('A', 'watcher')
    await story.load()
    expect(story.openRun.value).toBeNull()
    await expect(story.resumeBeat()).resolves.toBe(false)
    expect(seen.filter((s) => s.path === '/api/v1/stage1/advance')).toHaveLength(0)
  })

  it('resumeBeat replays the stranded index, never clock-plus-one', async () => {
    installFetch()
    indexByStory.set('A', 3)
    statusByStory.set('A', { id: 'run-9', index: 2, state: 'scenes_assembled' })
    const store = memStore()
    const story = useStory('A', 'watcher', undefined, store)
    await story.load()
    // The beat lands while resuming: the stranded state clears.
    const pending = story.resumeBeat()
    statusByStory.delete('A')
    await expect(pending).resolves.toBe(true)
    const posts = advancePosts()
    expect(posts).toHaveLength(1)
    expect(advanceBody(posts[0])['absolute_index']).toBe(2)
    expect(story.openRun.value).toBeNull()
  })

  it('an interrupted filing survives a fresh controller and resumes verbatim', async () => {
    installFetch()
    const store = memStore()
    const original = {
      'char-wren': {
        family: 'communicate',
        character_id: 'char-wren',
        snapshot_id: '00000000-0000-0000-0000-000000000000',
        target_character_id: 'char-ash',
        topic: 'What news from the mill?'
      }
    }
    // First controller: the filing fails before the server persists it.
    const first = useStory('A', 'watcher', undefined, store)
    await first.load()
    advanceHold = true
    const filing = first.advance(original)
    await vi.waitFor(() => expect(heldAdvances).toHaveLength(1))
    advanceHold = false
    heldAdvances[0].resolve(
      new Response(JSON.stringify({ error: { code: 'INTERNAL', message: 'died mid-beat' } }), {
        status: 500
      })
    )
    await expect(filing).resolves.toBe(false)
    expect(advanceBody(advancePosts()[0])['player_intents']).toEqual(original)
    expect(loadFilings(store, 'A')).toHaveLength(1)
    expect(loadFilings(store, 'A')[0]?.intents).toEqual(original)

    // A reload-equivalent fresh controller sees the stranded beat and the
    // frozen words, even though its composer starts empty.
    statusByStory.set('A', { id: 'run-9', index: 2, state: 'scenes_assembled' })
    const second = useStory('A', 'watcher', undefined, store)
    await second.load()
    expect(second.recoveryState.value).toBe('open')
    expect(second.preservedSubmission.value?.intents).toEqual(original)

    // Newer composer drafts never leak into the resume: the request
    // carries the frozen original, and the newer words are never posted.
    const newer = {
      'char-wren': {
        family: 'communicate',
        character_id: 'char-wren',
        snapshot_id: '00000000-0000-0000-0000-000000000000',
        target_character_id: 'char-ash',
        topic: 'Actually, what news from the market?'
      }
    }
    const resumed = second.resumeBeat()
    statusByStory.delete('A')
    await expect(resumed).resolves.toBe(true)
    const posts = advancePosts()
    expect(posts).toHaveLength(2)
    const last = posts.at(-1) as Seen
    expect(advanceBody(last)['absolute_index']).toBe(2)
    expect(advanceBody(last)['player_intents']).toEqual(original)
    for (const post of posts) {
      expect(advanceBody(post)['player_intents']).not.toEqual(newer)
    }
    // The confirmed filing retires the frozen record.
    expect(loadFilings(store, 'A')).toEqual([])
    expect(second.openRun.value).toBeNull()
  })

  it('a duplicate reconciliation retires no frozen submission', async () => {
    installFetch()
    advanceDuplicate = true
    const store = memStore()
    const story = useStory('A', 'watcher', undefined, store)
    await story.load()
    const intents = {
      'char-wren': {
        family: 'communicate',
        character_id: 'char-wren',
        snapshot_id: '00000000-0000-0000-0000-000000000000',
        target_character_id: 'char-ash',
        topic: 'What news from the mill?'
      }
    }
    await expect(story.advance(intents)).resolves.toBe(false)
    expect(loadFilings(store, 'A')).toHaveLength(1)
    expect(loadFilings(store, 'A')[0]?.intents).toEqual(intents)
  })

  it('a still-open refusal names the stranded beat instead of a raw 412', async () => {
    installFetch()
    statusByStory.set('A', { id: 'run-9', index: 2, state: 'world_ticked' })
    failures.set('POST /api/v1/stage1/advance', {
      status: 412,
      code: 'PRECONDITION_FAILED',
      message:
        'phase run run-9 is still open; reconcile or resume it before advancing another index'
    })
    const story = useStory('A', 'watcher')
    await story.load()
    await expect(story.advance()).resolves.toBe(false)
    expect(advancePosts()).toHaveLength(1)
    expect(story.notice.value).toEqual({
      kind: 'info',
      text: 'Beat 2 is still open (world ticked) — resume it instead of starting a new beat.'
    })
  })

  it('a blocked run refusal explains without starting another beat', async () => {
    installFetch()
    failures.set('POST /api/v1/stage1/advance', {
      status: 412,
      code: 'PRECONDITION_FAILED',
      message: 'phase run is terminal_failed; resume before advancing'
    })
    const story = useStory('A', 'watcher')
    await story.load()
    await expect(story.advance()).resolves.toBe(false)
    expect(advancePosts()).toHaveLength(1)
    expect(story.notice.value?.kind).toBe('error')
    expect(story.notice.value?.text).toContain('resume before advancing')
  })

  function question(topic: string): Record<string, Record<string, unknown>> {
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

  it('a refused contender never displaces the original filing across reload', async () => {
    installFetch()
    // Two controllers, one shared store: two tabs on the same beat.
    const store = memStore()
    const original = question('What news from the mill?')
    const rival = question('What news from the market?')

    // Tab A files Q1; the send stays in flight.
    const first = useStory('A', 'watcher', undefined, store)
    await first.load()
    advanceHold = true
    const filingA = first.advance(original)
    await vi.waitFor(() => expect(heldAdvances).toHaveLength(1))

    // Tab B files Q2 for the same beat and is refused before admission.
    const second = useStory('A', 'watcher', undefined, store)
    await second.load()
    const filingB = second.advance(rival)
    await vi.waitFor(() => expect(heldAdvances).toHaveLength(2))
    // Both tabs in flight at once: both claims coexist, neither overwrote.
    expect(loadFilings(store, 'A')).toHaveLength(2)
    heldAdvances[1].resolve(
      new Response(
        JSON.stringify({
          error: { code: 'PRECONDITION_FAILED', message: 'phase:2 is already executing' }
        }),
        { status: 409 }
      )
    )
    await expect(filingB).resolves.toBe(false)
    expect(second.notice.value?.text).toContain('acceptance is unconfirmed')
    expect(second.notice.value?.text ?? '').not.toContain('session only')

    // Tab A's send is interrupted before any commit.
    failures.set('POST /api/v1/stage1/advance', {
      status: 500,
      code: 'INTERNAL',
      message: 'died mid-beat'
    })
    advanceHold = false
    heldAdvances[0].reject(new Error('REQUEST_TIMEOUT'))
    await expect(filingA).resolves.toBe(false)

    // A fresh page sees the stranded beat, recovers exactly Q1, and keeps
    // Q2 listed separately — never as the replay candidate.
    statusByStory.set('A', { id: 'run-9', index: 2, state: 'scenes_assembled' })
    const third = useStory('A', 'watcher', undefined, store)
    await third.load()
    expect(third.recoveryState.value).toBe('open')
    expect(third.preservedSubmission.value?.intents).toEqual(original)
    expect(third.preservedSubmission.value?.durable).toBe(true)
    expect(third.contenderSubmissions.value).toHaveLength(1)
    expect(third.contenderSubmissions.value[0]?.intents).toEqual(rival)

    const resumed = third.resumeBeat()
    statusByStory.delete('A')
    await expect(resumed).resolves.toBe(true)
    const posts = advancePosts()
    const last = posts.at(-1) as Seen
    expect(advanceBody(last)['absolute_index']).toBe(2)
    expect(advanceBody(last)['player_intents']).toEqual(original)
    // The committed original retires; the refused contender survives it.
    const remaining = loadFilings(store, 'A')
    expect(remaining).toHaveLength(1)
    expect(remaining[0]?.intents).toEqual(rival)
    expect(remaining[0]?.refused).toBe(true)
    expect(inspectFilings(store, 'A').status).toBe('valid')
  })

  it('a failed recovery write degrades to session-only without reload claims', async () => {
    installFetch()
    const backing = new Map<string, string>()
    const throwing: SubmissionStorage = {
      getItem: (key) => backing.get(key) ?? null,
      setItem: () => {
        throw new Error('quota exceeded')
      },
      removeItem: (key) => {
        backing.delete(key)
      },
      keys: (prefix) => [...backing.keys()].filter((key) => key.startsWith(prefix))
    }
    const original = question('What news from the mill?')
    const story = useStory('A', 'watcher', undefined, throwing)
    await story.load()
    // The send stays in flight with nowhere durable to freeze it.
    advanceHold = true
    const filing = story.advance(original)
    await vi.waitFor(() => expect(heldAdvances).toHaveLength(1))
    statusByStory.set('A', { id: 'run-9', index: 2, state: 'scenes_assembled' })
    await story.refreshStatus()
    // This session still offers the question — flagged honestly.
    expect(story.preservedSubmission.value?.intents).toEqual(original)
    expect(story.preservedSubmission.value?.durable).toBe(false)
    advanceHold = false
    heldAdvances[0].resolve(
      new Response(JSON.stringify({ error: { code: 'INTERNAL', message: 'died mid-beat' } }), {
        status: 500
      })
    )
    await expect(filing).resolves.toBe(false)

    // A fresh controller finds no record: absent, not corrupt, no claims.
    const reloaded = useStory('A', 'watcher', undefined, throwing)
    await reloaded.load()
    expect(reloaded.recoveryState.value).toBe('open')
    expect(reloaded.preservedSubmission.value).toBeNull()
    expect(inspectFilings(throwing, 'A').status).toBe('absent')
    const resumed = reloaded.resumeBeat()
    statusByStory.delete('A')
    await expect(resumed).resolves.toBe(true)
    const posts = advancePosts()
    const last = posts.at(-1) as Seen
    expect(advanceBody(last)['absolute_index']).toBe(2)
    expect(advanceBody(last)).not.toHaveProperty('player_intents')
  })

  it('a refused filing on a throwing store is reported as session-only', async () => {
    installFetch()
    const throwing: SubmissionStorage = {
      getItem: () => null,
      setItem: () => {
        throw new Error('quota exceeded')
      },
      removeItem: () => undefined,
      keys: () => []
    }
    failures.set('POST /api/v1/stage1/advance', {
      status: 409,
      code: 'PRECONDITION_FAILED',
      message: 'phase:2 is already executing'
    })
    const story = useStory('A', 'watcher', undefined, throwing)
    await story.load()
    await expect(story.advance(question('What news from the mill?'))).resolves.toBe(false)
    expect(story.notice.value?.text).toContain('session only')
  })

  it('a corrupt recovery record is reported, never mistaken for absent', async () => {
    installFetch()
    const store = memStore()
    store.setItem(pendingKey('A'), '{not json')
    const story = useStory('A', 'watcher', undefined, store)
    await story.load()
    expect(story.preservedSubmission.value).toBeNull()
    expect(story.notice.value?.text).toContain('unreadable')
    // A world with no record stays silent.
    const clean = useStory('B', 'watcher', undefined, store)
    await clean.load()
    expect(clean.notice.value).toBeNull()
  })

  it('a tab that never saw the send resumes another tab\u2019s filing after discovery', async () => {
    installFetch()
    const store = memStore()
    const original = question('What news from the mill?')
    const a = useStory('A', 'watcher', undefined, store)
    const b = useStory('A', 'watcher', undefined, store)
    await a.load()
    await b.load()
    // Tab A files Q1 after both controllers loaded; the send strands.
    advanceHold = true
    const filingA = a.advance(original)
    await vi.waitFor(() => expect(heldAdvances).toHaveLength(1))
    statusByStory.set('A', { id: 'run-9', index: 2, state: 'scenes_assembled' })
    // Tab B discovers the stranded run without reloading and already holds Q1.
    await b.refreshStatus()
    expect(b.recoveryState.value).toBe('open')
    expect(b.preservedSubmission.value?.intents).toEqual(original)
    advanceHold = false
    const resumed = b.resumeBeat()
    statusByStory.delete('A')
    await expect(resumed).resolves.toBe(true)
    const posts = advancePosts()
    expect(posts).toHaveLength(2)
    expect(advanceBody(posts[1])['absolute_index']).toBe(2)
    expect(advanceBody(posts[1])['player_intents']).toEqual(original)
    // Settle Tab A's interrupted send behind the completed resume.
    failures.set('POST /api/v1/stage1/advance', {
      status: 500,
      code: 'INTERNAL',
      message: 'died mid-beat'
    })
    heldAdvances[0].reject(new Error('REQUEST_TIMEOUT'))
    await expect(filingA).resolves.toBe(false)
  })

  it('unreadable storage is reported as unavailable, never absent', async () => {
    installFetch()
    // A filing exists, but this controller cannot read it.
    const existing = memStore()
    filePendingSubmission(
      existing,
      { worldId: 'A', index: 2, intents: question('What news from the mill?') },
      { id: 'q1' }
    )
    const unreadable: SubmissionStorage = {
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
    statusByStory.set('A', { id: 'run-9', index: 2, state: 'scenes_assembled' })
    const story = useStory('A', 'watcher', undefined, unreadable)
    await story.load()
    expect(story.recoveryState.value).toBe('open')
    expect(story.preservedSubmission.value).toBeNull()
    expect(story.notice.value?.text).toContain('unavailable')
  })
})
