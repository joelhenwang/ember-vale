import { afterEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'
import { useStory } from './useStory'
import type { Role } from '../api/http'

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

function detailOf(id: string, index = 1): Record<string, unknown> {
  return {
    story_id: id,
    world_id: id,
    title: `Tale ${id}`,
    world_name: 'Ember Vale',
    mode: 'player',
    day: 1,
    phase: 'morning',
    absolute_index: index,
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
  vi.stubGlobal(
    'fetch',
    vi.fn(async (rawUrl: string, init: RequestInit = {}) => {
      const url = new URL(rawUrl, 'http://test')
      const method = init.method ?? 'GET'
      const key = `${method} ${url.pathname}`
      seen.push({
        method,
        path: url.pathname,
        query: Object.fromEntries(url.searchParams.entries()),
        body: init.body === undefined ? undefined : JSON.parse(String(init.body)),
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
        return json(detailOf(id, 9))
      }
      if (method === 'POST' && url.pathname === '/api/v1/stage1/advance') {
        return json({ world_id: id, absolute_index: 2, duplicate: false })
      }
      if (method === 'POST' && url.pathname === '/api/v1/stage2/activities') {
        return json({ id: 'act-1', status: 'active' })
      }
      if (method === 'GET' && url.pathname === '/api/v1/stage2/activities') {
        return json({ world_id: id, members: membersByStory.get(id) ?? [] })
      }
      if (method === 'GET' && url.pathname === '/api/v1/stage2/timeline') {
        const after = Number(url.searchParams.get('after') ?? 0)
        if (after === 0) return json(timelinePage(id, [E1], 5, true))
        return json(timelinePage(id, [E2], 9, false))
      }
      if (method === 'GET' && url.pathname === '/api/v1/stage2/map') return json(mapOf(id))
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
})
