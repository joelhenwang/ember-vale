import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  advanceStory,
  createDraft,
  getRole,
  listActivities,
  publishEditorDraft,
  type CallOptions
} from './worldsim'

interface Seen {
  url: string
  method: string
  body: unknown
  headers: Record<string, string>
}

let seen: Seen[] = []
let responder: (url: string, init: RequestInit) => unknown = () => ({})

function installFetch(): void {
  seen = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init: RequestInit = {}) => {
      seen.push({
        url,
        method: init.method ?? 'GET',
        body: init.body === undefined ? undefined : JSON.parse(String(init.body)),
        headers: (init.headers ?? {}) as Record<string, string>
      })
      return new Response(JSON.stringify(responder(url, init)), { status: 200 })
    })
  )
}

afterEach(() => {
  vi.unstubAllGlobals()
})

const opts: CallOptions = { role: 'watcher' }

describe('worldsim adapter bodies', () => {
  it('omits player_intents when there are no intents', async () => {
    installFetch()
    await advanceStory('world-1', 2, undefined, opts)
    expect(seen).toHaveLength(1)
    expect(seen[0].body).toEqual({ world_id: 'world-1', absolute_index: 2 })
    expect(seen[0].body as Record<string, unknown>).not.toHaveProperty('player_intents')
  })

  it('sends an explicit intents dictionary unchanged', async () => {
    installFetch()
    const intents = { wren: { family: 'wait' } }
    await advanceStory('world-1', 2, intents, opts)
    expect(seen[0].body).toEqual({
      world_id: 'world-1',
      absolute_index: 2,
      player_intents: intents
    })
  })

  it('never sends a null draft payload', async () => {
    installFetch()
    const payload = { world: { preset_id: 'w', preset_revision: 2 } }
    await createDraft(payload as never, 'world', opts)
    expect(seen[0].body).toEqual({ payload, current_step: 'world' })
  })

  it('reads the activity members list, not a hand-written items field', async () => {
    installFetch()
    const members = [{ id: 'a1', status: 'active', character_id: 'c1' }]
    responder = () => ({ world_id: 'world-1', members })
    const list = await listActivities('world-1', opts)
    expect(list.members).toEqual(members)
    expect(list).not.toHaveProperty('items')
  })

  it('reads published_revision from the publish envelope, not the head', async () => {
    installFetch()
    const detail = {
      id: 'preset-1',
      kind: 'character',
      name: 'Wren',
      builtin: false,
      readonly: false,
      archived_at: null,
      current_revision: 3,
      version: 3,
      revision: { appearance: 'rev 2 text' }
    }
    responder = () => ({ published_revision: 2, detail })
    const view = await publishEditorDraft('preset-1', 'draft-1', 1, 2, opts)
    expect(view.published_revision).toBe(2)
    expect(view.detail).toEqual(detail)
    // Nested adoption must pin the replayed revision, never the head.
    expect(view.published_revision).not.toBe(view.detail.current_revision)
    expect(seen[0].body).toEqual({ expected_version: 1, preset_expected_version: 2 })
    expect(seen[0].url).toContain('/editor-drafts/draft-1/publish')
  })

  it('returns the persisted grant, including null', async () => {
    installFetch()
    responder = () => null
    await expect(getRole('world-1', opts)).resolves.toBeNull()
    expect(seen[0].url).toContain('/stage2/roles?world_id=world-1')
    const grant = {
      id: 'g1',
      world_id: 'world-1',
      role: 'player',
      character_id: 'char-wren',
      granted_absolute: 0,
      version: 1
    }
    responder = () => grant
    await expect(getRole('world-1', opts)).resolves.toEqual(grant)
  })
})
