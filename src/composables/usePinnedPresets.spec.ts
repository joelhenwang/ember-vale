import { afterEach, describe, expect, it, vi } from 'vitest'
import { usePinnedPresets } from './usePinnedPresets'

let holdFirst: Array<() => void> = []
let failRevs = new Set<number>()

function worldDetail(id: string, rev: number): Record<string, unknown> {
  const places =
    id === 'wA' && rev === 1
      ? [{ key: 'old-hall', name: 'Old Hall' }]
      : id === 'wB'
        ? [{ key: 'b-yard', name: 'B Yard' }]
        : [{ key: 'hearth', name: 'Hearth' }]
  return {
    id,
    name: id === 'wA' ? 'Ember Vale' : 'B Vale',
    current_revision: id === 'wA' ? 2 : 1,
    revision: { locations: places, description: `${id} rev ${rev}` }
  }
}

function charDetail(id: string, rev: number): Record<string, unknown> {
  return {
    id,
    name: rev === 1 ? 'Wren-young' : 'Wren',
    current_revision: 3,
    revision: { appearance: '', tags: [], starting_location_key: 'hearth' }
  }
}

function installFetch(): void {
  holdFirst = []
  failRevs = new Set()
  vi.stubGlobal(
    'fetch',
    vi.fn(async (rawUrl: string, init: RequestInit = {}) => {
      const url = new URL(rawUrl, 'http://test')
      const segs = url.pathname.split('/')
      const rev = Number(url.searchParams.get('revision') ?? 0)
      if (holdFirst.length > 0) {
        await new Promise<void>((resolve) => holdFirst.push(resolve))
      }
      const id = segs[segs.length - 1] as string
      if (failRevs.has(rev)) {
        return new Response(JSON.stringify({ error: { code: 'HTTP_500', message: 'gone' } }), {
          status: 500
        })
      }
      void init
      const body = id.startsWith('w') ? worldDetail(id, rev) : charDetail(id, rev)
      return new Response(JSON.stringify(body), { status: 200 })
    })
  )
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('usePinnedPresets', () => {
  it('loads the exact pinned revision places', async () => {
    installFetch()
    const pinned = usePinnedPresets()
    await pinned.loadWorld('wA', 1)
    expect(pinned.world.value).toMatchObject({
      id: 'wA',
      revision: 1,
      places: [{ key: 'old-hall', name: 'Old Hall' }]
    })
    expect(pinned.worldError.value).toBeNull()
  })

  it('a slow A response never overwrites B', async () => {
    installFetch()
    holdFirst.push(() => undefined)
    const pinned = usePinnedPresets()
    const pendingA = pinned.loadWorld('wA', 1)
    // Release the gate only after B starts: A resolves second.
    const pendingB = pinned.loadWorld('wB', 1)
    holdFirst.forEach((release) => release())
    holdFirst = []
    await Promise.all([pendingA, pendingB])
    expect(pinned.world.value).toMatchObject({ id: 'wB', revision: 1 })
    expect(pinned.world.value?.places).toEqual([{ key: 'b-yard', name: 'B Yard' }])
  })

  it('a failed pinned revision is an explicit error, not a silent fallback', async () => {
    installFetch()
    failRevs.add(1)
    const pinned = usePinnedPresets()
    await pinned.loadWorld('wA', 1)
    expect(pinned.world.value).toBeNull()
    expect(pinned.worldError.value).toContain('1')
  })

  it('two presets sharing revision 1 keep their own places', async () => {
    installFetch()
    const pinned = usePinnedPresets()
    await pinned.loadWorld('wA', 1)
    const aPlaces = pinned.world.value?.places
    await pinned.loadWorld('wB', 1)
    expect(aPlaces).toEqual([{ key: 'old-hall', name: 'Old Hall' }])
    expect(pinned.world.value?.places).toEqual([{ key: 'b-yard', name: 'B Yard' }])
  })

  it('ignores responses for a deselected preset', async () => {
    installFetch()
    holdFirst.push(() => undefined)
    const pinned = usePinnedPresets()
    let current = true
    const pending = pinned.loadWorld('wA', 1, () => current)
    current = false
    holdFirst.forEach((release) => release())
    await pending
    expect(pinned.world.value).toBeNull()
    expect(pinned.worldError.value).toBeNull()
  })

  it('resolves an old selected-character revision without fetching latest', async () => {
    installFetch()
    const pinned = usePinnedPresets()
    await pinned.loadCharacter('c1', 1, 3)
    expect(pinned.characterName('c1', 1, 'Wren')).toBe('Wren-young')
    expect(pinned.characterName('c9', 1, 'Stored')).toBe('Stored')
  })

  it('a failed character revision falls back to the draft-stored name', async () => {
    installFetch()
    failRevs.add(1)
    const pinned = usePinnedPresets()
    await pinned.loadCharacter('c1', 1, 3)
    expect(pinned.characterName('c1', 1, 'Wren')).toBe('Wren')
  })
})
