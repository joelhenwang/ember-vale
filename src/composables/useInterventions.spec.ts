import { afterEach, describe, expect, it, vi } from 'vitest'
import { useInterventions } from './useInterventions'

interface Seen {
  method: string
  path: string
  body: unknown
}

let seen: Seen[] = []
/** Queued items by id, in server order. */
let items: Array<Record<string, unknown>> = []
/** Submit calls that fail with a transport error before responding. */
let dropSubmits = 0

function itemOf(id: string, status = 'queued', version = 0): Record<string, unknown> {
  return {
    id,
    world_id: 'w1',
    status,
    mode: 'influence',
    role: 'director',
    text: 'A peddler arrives at the Hearth.',
    steps: [],
    failure_reason: '',
    version
  }
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status })
}

function installFetch(): void {
  seen = []
  items = [itemOf('q-1')]
  dropSubmits = 0
  currentRole = 'director'
  currentWorld = 'w1'
  vi.stubGlobal(
    'fetch',
    vi.fn(async (rawUrl: string, init: RequestInit = {}) => {
      const url = new URL(rawUrl, 'http://test')
      const method = init.method ?? 'GET'
      const body = init.body === undefined ? undefined : JSON.parse(String(init.body))
      seen.push({ method, path: url.pathname, body })
      if (method === 'POST' && url.pathname === '/api/v1/interventions') {
        if (dropSubmits > 0) {
          dropSubmits -= 1
          throw new Error('socket hangup')
        }
        const key = (body as { client_request_id: string }).client_request_id
        const replay = items.find((entry) => entry['key'] === key)
        if (replay) return json(replay)
        const created = {
          ...itemOf(`q-${items.length + 1}`),
          text: (body as { text: string }).text,
          key
        }
        items.push(created)
        return json(created)
      }
      if (method === 'GET' && url.pathname === '/api/v1/interventions') {
        return json(items)
      }
      const one = url.pathname.match(/^\/api\/v1\/interventions\/(.+?)(\/cancel)?$/)
      if (one) {
        const found = items.find((entry) => entry['id'] === one[1])
        if (!found) return json({ error: { code: 'NOT_FOUND', message: 'gone' } }, 404)
        if (method === 'GET') return json(found)
        if (method === 'PATCH') {
          const expected = (body as { expected_version: number }).expected_version
          if (expected !== found['version']) {
            return json({ error: { code: 'VERSION_CONFLICT', message: 'stale' } }, 409)
          }
          found['text'] = (body as { text: string }).text
          found['version'] = (found['version'] as number) + 1
          found['status'] = 'needs_clarification'
          found['failure_reason'] = 'Which peddler did you mean?'
          return json(found)
        }
        if (one[2] === '/cancel') {
          found['status'] = 'cancelled'
          found['version'] = (found['version'] as number) + 1
          return json(found)
        }
      }
      return json({})
    })
  )
}

afterEach(() => {
  vi.unstubAllGlobals()
})

let currentRole = 'director'
let currentWorld = 'w1'
const header = () => ({ role: currentRole as 'director' | 'deity' | 'watcher' | 'player' })
const worldOf = () => currentWorld

describe('useInterventions queue', () => {
  it('submits with a fresh key and lists the queue', async () => {
    installFetch()
    const ctl = useInterventions(worldOf, header)
    const created = await ctl.submit('influence', 'A peddler arrives at the Hearth.')
    expect(created?.id).toBe('q-2')
    expect(ctl.active.value?.id).toBe('q-2')
    await ctl.refresh()
    expect(ctl.queue.value.map((entry) => entry.id)).toContain('q-2')
    const post = seen.find((s) => s.method === 'POST' && s.path === '/api/v1/interventions')
    expect((post?.body as { mode: string }).mode).toBe('influence')
    expect((post?.body as { client_request_id: string }).client_request_id).toBeTruthy()
  })

  it('retry reuses the failed submission key instead of duplicating', async () => {
    installFetch()
    dropSubmits = 1
    const ctl = useInterventions(worldOf, header)
    expect(await ctl.submit('influence', 'A peddler arrives.')).toBeNull()
    expect(ctl.pending.value).not.toBeNull()
    expect(ctl.notice.value?.kind).toBe('error')
    const firstKey = (seen[0].body as { client_request_id: string }).client_request_id
    const replayed = await ctl.retry()
    expect(replayed?.id).toBe('q-2')
    expect(ctl.pending.value).toBeNull()
    const posts = seen.filter((s) => s.method === 'POST' && s.path === '/api/v1/interventions')
    expect(posts).toHaveLength(2)
    expect(
      posts.every((p) => (p.body as { client_request_id: string }).client_request_id === firstKey)
    ).toBe(true)
    expect(items).toHaveLength(2)
  })

  it('surfaces clarification and edits with the active version', async () => {
    installFetch()
    const ctl = useInterventions(worldOf, header)
    await ctl.refresh()
    ctl.select('q-1')
    const edited = await ctl.editActive('A peddler arrives at the Market.')
    expect(edited?.status).toBe('needs_clarification')
    expect(edited?.version).toBe(1)
    expect(ctl.notice.value?.kind).toBe('info')
    expect(ctl.notice.value?.text).toContain('Which peddler')
    const patch = seen.find((s) => s.method === 'PATCH')
    expect((patch?.body as { expected_version: number }).expected_version).toBe(0)
  })

  it('a stale edit reloads instead of overwriting', async () => {
    installFetch()
    const ctl = useInterventions(worldOf, header)
    await ctl.refresh()
    ctl.select('q-1')
    // Another writer moves the item first.
    const stored = items.find((entry) => entry['id'] === 'q-1')
    if (stored) stored['version'] = 7
    expect(await ctl.editActive('Too late.')).toBeNull()
    expect(ctl.notice.value?.text).toContain('changed underneath')
    expect(ctl.active.value?.version).toBe(7)
  })

  it('cancels the active item and keeps its history', async () => {
    installFetch()
    const ctl = useInterventions(worldOf, header)
    await ctl.refresh()
    ctl.select('q-1')
    expect(await ctl.cancelActive()).toBe(true)
    expect(ctl.active.value?.status).toBe('cancelled')
    const cancel = seen.find((s) => s.path.endsWith('/cancel'))
    expect((cancel?.body as { expected_version: number }).expected_version).toBe(0)
  })

  it('a disposal mid-flight applies nothing late', async () => {
    installFetch()
    const ctl = useInterventions(worldOf, header)
    const pending = ctl.refresh()
    ctl.dispose()
    await pending
    expect(ctl.queue.value).toHaveLength(0)
  })

  it('a fresh key is refused while a filing is unresolved', async () => {
    installFetch()
    dropSubmits = 1
    const ctl = useInterventions(worldOf, header)
    expect(await ctl.submit('influence', 'A peddler arrives.')).toBeNull()
    expect(ctl.pending.value).not.toBeNull()
    // A second submit must reconcile or discard first — never mint a key.
    expect(await ctl.submit('influence', 'Something else.')).toBeNull()
    expect(ctl.notice.value?.text).toContain('still unresolved')
    const posts = seen.filter((s) => s.method === 'POST' && s.path === '/api/v1/interventions')
    expect(posts).toHaveLength(1)
    // Explicit discard clears the way for a fresh key.
    ctl.discardPending()
    expect(ctl.pending.value).toBeNull()
    expect(await ctl.submit('influence', 'Something else.')).not.toBeNull()
    expect(
      seen.filter((s) => s.method === 'POST' && s.path === '/api/v1/interventions')
    ).toHaveLength(2)
  })

  it('inspecting a filed item reconciles the ambiguous filing', async () => {
    installFetch()
    dropSubmits = 1
    const ctl = useInterventions(worldOf, header)
    expect(await ctl.submit('influence', 'A peddler arrives.')).toBeNull()
    await ctl.refresh()
    ctl.select('q-1')
    expect(ctl.pending.value).toBeNull()
    expect(await ctl.submit('influence', 'Something else.')).not.toBeNull()
  })

  it('a seat change blocks the retry instead of reinterpreting it', async () => {
    installFetch()
    dropSubmits = 1
    const ctl = useInterventions(worldOf, header)
    expect(await ctl.submit('influence', 'A peddler arrives.')).toBeNull()
    currentRole = 'deity'
    expect(await ctl.retry()).toBeNull()
    expect(ctl.notice.value?.text).toContain('seat changed')
    expect(ctl.pending.value).not.toBeNull()
    const posts = seen.filter((s) => s.method === 'POST' && s.path === '/api/v1/interventions')
    expect(posts).toHaveLength(1)
  })

  it('a world change blocks the retry instead of retargeting it', async () => {
    installFetch()
    dropSubmits = 1
    const ctl = useInterventions(worldOf, header)
    expect(await ctl.submit('influence', 'A peddler arrives.')).toBeNull()
    currentWorld = 'w2'
    expect(await ctl.retry()).toBeNull()
    expect(ctl.notice.value?.text).toContain('world or seat changed')
    expect(ctl.pending.value).not.toBeNull()
  })
})
