import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  hydrateFields,
  loadLocalPreset,
  resetEditorDraftMemoryForTests,
  stableCreateKey,
  storeLocalPreset,
  useEditorDraft
} from './useEditorDraft'

interface DraftRow {
  id: string
  presetId: string
  baseRevision: number
  fields: Record<string, unknown>
  version: number
}

const drafts = new Map<string, DraftRow>()
let holdResponses = false
let held: Array<() => void> = []

function detailFor(presetId: string, revision: number): Record<string, unknown> {
  return {
    id: presetId,
    kind: 'character',
    name: 'Wren',
    builtin: false,
    readonly: false,
    archived_at: null,
    current_revision: 3,
    version: 3,
    revision: {
      appearance: `rev ${revision} appearance`,
      personality: 'dry humor',
      // The editor never shows this field; hydration and publish must keep it.
      portrait_asset_id: 'asset-9',
      tags: ['Human']
    }
  }
}

function installFetch(): void {
  drafts.clear()
  held = []
  holdResponses = false
  vi.stubGlobal(
    'fetch',
    vi.fn(async (rawUrl: string, init: RequestInit = {}) => {
      if (holdResponses) {
        await new Promise<void>((resolve) => held.push(resolve))
      }
      const url = new URL(rawUrl, 'http://test')
      const path = url.pathname
      const method = init.method ?? 'GET'
      const body =
        init.body === undefined
          ? undefined
          : (JSON.parse(String(init.body)) as Record<string, unknown>)

      const draftOpen = path.match(/\/library\/presets\/([^/]+)\/editor-drafts$/)
      if (draftOpen && method === 'POST') {
        const presetId = draftOpen[1] as string
        const base = Number((body as Record<string, unknown>)['base_revision'])
        const id = `draft-${presetId}-r${base}`
        const row: DraftRow = drafts.get(id) ?? {
          id,
          presetId,
          baseRevision: base,
          fields: {},
          version: 1
        }
        drafts.set(id, row)
        return new Response(
          JSON.stringify({
            id: row.id,
            preset_id: presetId,
            base_revision: base,
            fields: row.fields,
            version: row.version,
            updated_at: new Date().toISOString()
          }),
          { status: 200 }
        )
      }

      const save = path.match(/\/library\/presets\/([^/]+)\/editor-drafts\/([^/]+)$/)
      if (save && method === 'PATCH') {
        const row = drafts.get(save[2] as string)
        if (!row) {
          return new Response(
            JSON.stringify({ error: { code: 'NOT_FOUND', message: 'no draft' } }),
            { status: 404 }
          )
        }
        row.fields = (body as Record<string, unknown>)['fields'] as Record<string, unknown>
        row.version += 1
        return new Response(
          JSON.stringify({
            id: row.id,
            preset_id: row.presetId,
            base_revision: row.baseRevision,
            fields: row.fields,
            version: row.version,
            updated_at: new Date().toISOString()
          }),
          { status: 200 }
        )
      }

      const pub = path.match(/\/library\/presets\/([^/]+)\/editor-drafts\/([^/]+)\/publish$/)
      if (pub && method === 'POST') {
        const presetId = pub[1] as string
        const row = drafts.get(pub[2] as string)
        if (!row) {
          return new Response(
            JSON.stringify({ error: { code: 'NOT_FOUND', message: 'no draft' } }),
            { status: 404 }
          )
        }
        return new Response(
          JSON.stringify({
            published_revision: 2,
            detail: detailFor(presetId, 2)
          }),
          { status: 200 }
        )
      }

      const read = path.match(/\/library\/presets\/([^/]+)$/)
      if (read && method === 'GET') {
        const rev = Number(url.searchParams.get('revision') ?? 1)
        return new Response(JSON.stringify(detailFor(read[1] as string, rev)), {
          status: 200
        })
      }

      return new Response(JSON.stringify({}), { status: 200 })
    })
  )
}

afterEach(() => {
  vi.unstubAllGlobals()
  resetEditorDraftMemoryForTests()
})

describe('useEditorDraft', () => {
  it('hydrates the exact base revision plus saved fields, keeping unexposed ones', async () => {
    installFetch()
    const ctl = useEditorDraft()
    await ctl.open('preset-1', 2)
    expect(ctl.status.value).toBe('editing')
    expect(ctl.fields.value).toMatchObject({
      appearance: 'rev 2 appearance',
      portrait_asset_id: 'asset-9'
    })
    // A saved draft field overlays the base; unexposed fields survive.
    const merged = hydrateFields(ctl.baseDetail.value, {
      ...ctl.draft.value!,
      fields: { appearance: 'edited' }
    })
    expect(merged).toMatchObject({
      appearance: 'edited',
      portrait_asset_id: 'asset-9',
      personality: 'dry humor'
    })
    expect(merged).not.toHaveProperty('kind')
  })

  it('moves through saving/saved and publishing/published states', async () => {
    installFetch()
    const ctl = useEditorDraft()
    await ctl.open('preset-1', 2)
    ctl.fields.value = { ...ctl.fields.value, appearance: 'edited' }
    await ctl.save('preset-1')
    expect(ctl.status.value).toBe('saved')
    const view = await ctl.publish('preset-1', 3)
    expect(ctl.status.value).toBe('published')
    expect(view?.published_revision).toBe(2)
    // Adoption pins the replayed revision, not the head.
    expect(ctl.publishedRevision.value).toBe(2)
    expect(view?.detail.current_revision).toBe(3)
  })

  it('a late A response never alters B', async () => {
    installFetch()
    holdResponses = true
    const ctl = useEditorDraft()
    const pendingA = ctl.open('preset-a', 1)
    const pendingB = (async (): Promise<void> => {
      held.splice(0).forEach((release) => release())
      holdResponses = false
      await ctl.open('preset-b', 2)
    })()
    held.splice(0).forEach((release) => release())
    holdResponses = false
    await Promise.all([pendingA, pendingB])
    expect(ctl.draft.value?.preset_id).toBe('preset-b')
    expect(ctl.baseDetail.value?.id).toBe('preset-b')
  })

  it('a failed save reports failed without losing the draft', async () => {
    installFetch()
    const ctl = useEditorDraft()
    await ctl.open('preset-1', 2)
    ctl.fields.value = { ...ctl.fields.value, appearance: 'edited' }
    // Break the draft identity so the stub 404s.
    ctl.draft.value = { ...ctl.draft.value!, id: 'missing' }
    const ok = await ctl.save('preset-1')
    expect(ok).toBe(false)
    expect(ctl.status.value).toBe('failed')
    expect(ctl.error.value).toBeTruthy()
    expect(ctl.draft.value?.id).toBe('missing')
  })
})

describe('reload-persistent local drafts', () => {
  it('preserves unfinished work across mounts and labels storage failures', () => {
    resetEditorDraftMemoryForTests()
    expect(loadLocalPreset('character', 'fresh')).toBeNull()
    // Memory holds the work even where localStorage is unavailable; the
    // boolean labels whether this device will survive a reload.
    const persisted = storeLocalPreset('character', 'fresh', { appearance: 'half written' })
    expect(typeof persisted).toBe('boolean')
    expect(loadLocalPreset('character', 'fresh')).toEqual({ appearance: 'half written' })
  })

  it('reuses one stable creation key across retries', () => {
    resetEditorDraftMemoryForTests()
    const first = stableCreateKey('fresh')
    const second = stableCreateKey('fresh')
    expect(second).toBe(first)
    expect(first).toMatch(/^[0-9a-f-]{36}$/)
    expect(stableCreateKey('other')).not.toBe(first)
  })
})
