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
  publishedVersion: number | null
  publishedRevision: number | null
}

const drafts = new Map<string, DraftRow>()
let holdResponses = false
let held: Array<() => void> = []
/** Ordered request log (method + path) and publish request bodies. */
let calls: string[] = []
let publishBodies: Record<string, unknown>[] = []
/** Fail the next publish call once with a transport error (ambiguous outcome). */
let failNextPublish = false
/** A draft left open on a superseded base (reload-after-publish setup). */
let staleDraft: DraftRow | null = null
/** Hold matching requests until released (lifecycle-race control). */
let holdWhen: ((method: string, path: string) => boolean) | null = null

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
  calls = []
  publishBodies = []
  failNextPublish = false
  staleDraft = null
  holdWhen = null
  vi.stubGlobal(
    'fetch',
    vi.fn(async (rawUrl: string, init: RequestInit = {}) => {
      if (holdResponses) {
        await new Promise<void>((resolve) => held.push(resolve))
      }
      const url = new URL(rawUrl, 'http://test')
      const path = url.pathname
      const method = init.method ?? 'GET'
      if (holdWhen?.(method, path)) {
        await new Promise<void>((resolve) => held.push(resolve))
      }
      calls.push(`${method} ${path}`)
      const body =
        init.body === undefined
          ? undefined
          : (JSON.parse(String(init.body)) as Record<string, unknown>)

      const draftOpen = path.match(/\/library\/presets\/([^/]+)\/editor-drafts$/)
      if (draftOpen && method === 'POST') {
        const presetId = draftOpen[1] as string
        const base = Number((body as Record<string, unknown>)['base_revision'])
        if (staleDraft && staleDraft.presetId === presetId && staleDraft.baseRevision !== base) {
          return new Response(
            JSON.stringify({
              error: { code: 'PRECONDITION_FAILED', message: 'draft already open' }
            }),
            { status: 409 }
          )
        }
        const id = `draft-${presetId}-r${base}`
        const row: DraftRow = drafts.get(id) ?? {
          id,
          presetId,
          baseRevision: base,
          fields: {},
          version: 1,
          publishedVersion: null,
          publishedRevision: null
        }
        drafts.set(id, row)
        return new Response(
          JSON.stringify({
            id: row.id,
            preset_id: presetId,
            base_revision: base,
            fields: row.fields,
            version: row.version,
            published_version: row.publishedVersion,
            published_revision: row.publishedRevision,
            updated_at: new Date().toISOString()
          }),
          { status: 200 }
        )
      }

      const current = path.match(/\/library\/presets\/([^/]+)\/editor-drafts\/current$/)
      if (current && method === 'GET') {
        const row = staleDraft?.presetId === current[1] ? staleDraft : null
        if (!row) {
          return new Response(
            JSON.stringify({ error: { code: 'NOT_FOUND', message: 'no draft' } }),
            { status: 404 }
          )
        }
        return new Response(
          JSON.stringify({
            id: row.id,
            preset_id: row.presetId,
            base_revision: row.baseRevision,
            fields: row.fields,
            version: row.version,
            published_version: row.publishedVersion,
            published_revision: row.publishedRevision,
            updated_at: new Date().toISOString()
          }),
          { status: 200 }
        )
      }

      const complete = path.match(/\/library\/presets\/([^/]+)\/editor-drafts\/([^/]+)\/complete$/)
      if (complete && method === 'POST') {
        const row = staleDraft?.id === complete[2] ? staleDraft : null
        // Mirrors the server: only a version matching the published
        // receipt may retire; anything newer is an explicit discard.
        if (
          row &&
          row.publishedVersion !== null &&
          row.publishedRevision !== null &&
          row.publishedVersion === row.version
        ) {
          staleDraft = null
          return new Response(JSON.stringify({ draft_id: row.id }), { status: 200 })
        }
        return new Response(
          JSON.stringify({
            error: { code: 'PRECONDITION_FAILED', message: 'draft has unpublished changes' }
          }),
          { status: 409 }
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
        if (failNextPublish) {
          failNextPublish = false
          // Transport failure: the request may still have committed.
          throw new Error('network failure: connection reset')
        }
        publishBodies.push({ ...(body as Record<string, unknown>) })
        // The publish bumps the preset version, like the real backend.
        const detail = {
          ...(detailFor(presetId, 2) as Record<string, unknown>),
          version: 4
        }
        return new Response(JSON.stringify({ published_revision: 2, detail }), { status: 200 })
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

  it('saveAndPublish saves the current form, then publishes the acked version', async () => {
    installFetch()
    const ctl = useEditorDraft()
    await ctl.open('preset-1', 2)
    const form = JSON.stringify({ appearance: 'edited without saving first' })
    const view = await ctl.saveAndPublish(
      'preset-1',
      {
        ...ctl.fields.value,
        appearance: 'edited without saving first'
      },
      form
    )
    // A resolved publication clears the frozen state entirely.
    expect(ctl.pendingPublication.value).toBeNull()
    expect(view?.published_revision).toBe(2)
    expect(ctl.status.value).toBe('published')
    // One save carrying the form, then one publish of the acknowledged
    // version (1 -> 2): the publish never runs ahead of the save.
    expect(calls.filter((c) => c.startsWith('PATCH'))).toHaveLength(1)
    expect(publishBodies).toHaveLength(1)
    expect(publishBodies[0]).toEqual({ expected_version: 2, preset_expected_version: 3 })
    // The published content is the edited form, not the last saved draft.
    const row = drafts.get('draft-preset-1-r2')
    expect((row?.fields as Record<string, unknown>)['appearance']).toBe(
      'edited without saving first'
    )
  })

  it('an ambiguous publish retries the frozen request without another save', async () => {
    installFetch()
    const ctl = useEditorDraft()
    await ctl.open('preset-1', 2)
    failNextPublish = true
    const olderForm = JSON.stringify({ appearance: 'ambiguous edits' })
    const lost = await ctl.saveAndPublish(
      'preset-1',
      {
        ...ctl.fields.value,
        appearance: 'ambiguous edits'
      },
      olderForm
    )
    expect(lost).toBeNull()
    expect(ctl.status.value).toBe('failed')
    expect(ctl.lastFailedOp.value).toBe('publish')
    // The frozen publication keeps the acknowledged form snapshot.
    expect(ctl.pendingPublication.value).toMatchObject({
      version: 2,
      presetVersion: 3,
      formSnapshot: olderForm
    })
    const patches = calls.filter((c) => c.startsWith('PATCH')).length
    // The retry replays the frozen draft version and preset version: no
    // second save, so no new version and no duplicate revision.
    const view = await ctl.retryPublish('preset-1')
    expect(view?.published_revision).toBe(2)
    expect(ctl.status.value).toBe('published')
    expect(calls.filter((c) => c.startsWith('PATCH'))).toHaveLength(patches)
    // Only the retry reached the server (the first attempt died in
    // transport), replaying the exact frozen identity.
    expect(publishBodies).toEqual([{ expected_version: 2, preset_expected_version: 3 }])
  })

  it('refreshes the preset version after publish so the next publish is current', async () => {
    installFetch()
    const ctl = useEditorDraft()
    await ctl.open('preset-1', 2)
    expect(ctl.baseDetail.value?.version).toBe(3)
    await ctl.saveAndPublish('preset-1', { ...ctl.fields.value }, JSON.stringify({ round: 1 }))
    // The publish bumped the preset: our copy moves with it.
    expect(ctl.baseDetail.value?.version).toBe(4)
    // A second edit publishes against the fresh version, not a stale one.
    await ctl.saveAndPublish(
      'preset-1',
      {
        ...ctl.fields.value,
        appearance: 'second round'
      },
      JSON.stringify({ round: 2 })
    )
    expect(publishBodies[1]).toMatchObject({ preset_expected_version: 4 })
    expect(ctl.status.value).toBe('published')
  })

  it('replays Older on retry after Newest saved: the revision holds Older', async () => {
    installFetch()
    const ctl = useEditorDraft()
    await ctl.open('preset-1', 2)
    // Publish Older; the response is lost in transport (ambiguous).
    failNextPublish = true
    const olderForm = JSON.stringify({ appearance: 'Older' })
    expect(
      await ctl.saveAndPublish('preset-1', { ...ctl.fields.value, appearance: 'Older' }, olderForm)
    ).toBeNull()
    expect(ctl.pendingPublication.value?.formSnapshot).toBe(olderForm)
    // The user edits Newest and saves it: version 3, acknowledged.
    const newerForm = JSON.stringify({ appearance: 'Newest' })
    ctl.fields.value = { ...ctl.fields.value, appearance: 'Newest' }
    expect(await ctl.save('preset-1')).toBe(true)
    expect(ctl.draft.value?.version).toBe(3)
    // Retry replays the frozen Older version — not the newer save.
    const view = await ctl.retryPublish('preset-1')
    expect(view?.published_revision).toBe(2)
    expect(publishBodies).toEqual([{ expected_version: 2, preset_expected_version: 3 }])
    // Success clears the frozen state; the caller still holds the Older
    // snapshot to decide what the replay may mark clean. Newest was
    // never published, so only a match with Older may go clean.
    expect(ctl.pendingPublication.value).toBeNull()
    expect(newerForm === olderForm).toBe(false)
  })

  it('tracks the failed operation and clears it on success', async () => {
    installFetch()
    const ctl = useEditorDraft()
    await ctl.open('preset-1', 2)
    expect(ctl.lastFailedOp.value).toBeNull()
    ctl.draft.value = { ...ctl.draft.value!, id: 'missing' }
    expect(await ctl.save('preset-1')).toBe(false)
    expect(ctl.lastFailedOp.value).toBe('save')
    // A retry with nothing frozen resolves nothing and changes nothing.
    expect(await ctl.retryPublish('preset-1')).toBeNull()
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

  it('retires a fully-published stale draft and reopens the new head', async () => {
    installFetch()
    // Reload after a publish: a base-1 draft lingers whose version
    // still matches its published receipt — retiring it abandons
    // nothing, since the revision preserves the content.
    staleDraft = {
      id: 'draft-stale',
      presetId: 'preset-1',
      baseRevision: 1,
      fields: {},
      version: 3,
      publishedVersion: 3,
      publishedRevision: 2
    }
    const ctl = useEditorDraft()
    await ctl.open('preset-1', 2)
    expect(ctl.status.value).toBe('editing')
    expect(ctl.draft.value?.base_revision).toBe(2)
    expect(ctl.lastFailedOp.value).toBeNull()
    // The stale draft retired through complete, then the head opened.
    expect(calls).toContain(
      'POST /api/v1/library/presets/preset-1/editor-drafts/draft-stale/complete'
    )
    expect(
      calls.filter((c) => c === 'POST /api/v1/library/presets/preset-1/editor-drafts')
    ).toHaveLength(2)
  })

  it('surfaces the conflict when the stale draft holds unpublished work', async () => {
    installFetch()
    // Saved after publishing: the version moved past the receipt, so
    // retiring it would abandon newer work — the open stays failed.
    staleDraft = {
      id: 'draft-stale',
      presetId: 'preset-1',
      baseRevision: 1,
      fields: { appearance: 'newer' },
      version: 4,
      publishedVersion: 3,
      publishedRevision: 2
    }
    const ctl = useEditorDraft()
    await expect(ctl.open('preset-1', 2)).rejects.toThrow()
    expect(ctl.status.value).toBe('failed')
    expect(ctl.lastFailedOp.value).toBe('open')
    // No second open attempted: the conflict stands for explicit discard.
    expect(
      calls.filter((c) => c === 'POST /api/v1/library/presets/preset-1/editor-drafts')
    ).toHaveLength(1)
  })

  it('a superseded recovery never disturbs the newer editor', async () => {
    installFetch()
    staleDraft = {
      id: 'draft-stale',
      presetId: 'preset-a',
      baseRevision: 1,
      fields: {},
      version: 3,
      publishedVersion: 3,
      publishedRevision: 2
    }
    // Hold A's recovery read so B opens while A is still recovering.
    holdWhen = (method, path) => method === 'GET' && path.endsWith('/editor-drafts/current')
    const ctl = useEditorDraft()
    const pendingA = ctl.open('preset-a', 2)
    await vi.waitFor(() => {
      if (held.length === 0) throw new Error('recovery read not held yet')
    })
    await ctl.open('preset-b', 1)
    expect(ctl.draft.value?.preset_id).toBe('preset-b')
    expect(ctl.status.value).toBe('editing')
    // Release A: it must stop without reopening, without issuing the
    // completion it no longer owns, and without throwing onto B.
    holdWhen = null
    held.splice(0).forEach((release) => release())
    await pendingA
    expect(ctl.draft.value?.preset_id).toBe('preset-b')
    expect(ctl.baseDetail.value?.id).toBe('preset-b')
    expect(ctl.status.value).toBe('editing')
    expect(ctl.error.value).toBeNull()
    expect(ctl.lastFailedOp.value).toBeNull()
    expect(
      calls.filter((c) => c === 'POST /api/v1/library/presets/preset-a/editor-drafts')
    ).toHaveLength(1)
    expect(calls.some((c) => c.includes('draft-stale/complete'))).toBe(false)
  })

  it('disposal during recovery prevents reopening', async () => {
    installFetch()
    staleDraft = {
      id: 'draft-stale',
      presetId: 'preset-a',
      baseRevision: 1,
      fields: {},
      version: 3,
      publishedVersion: 3,
      publishedRevision: 2
    }
    holdWhen = (method, path) => method === 'GET' && path.endsWith('/editor-drafts/current')
    const ctl = useEditorDraft()
    const pendingA = ctl.open('preset-a', 2)
    await vi.waitFor(() => {
      if (held.length === 0) throw new Error('recovery read not held yet')
    })
    ctl.dispose()
    holdWhen = null
    held.splice(0).forEach((release) => release())
    await pendingA
    // Nothing assigned, nothing reopened, nothing completed, no throw.
    expect(ctl.draft.value).toBeNull()
    expect(ctl.baseDetail.value).toBeNull()
    expect(
      calls.filter((c) => c === 'POST /api/v1/library/presets/preset-a/editor-drafts')
    ).toHaveLength(1)
    expect(calls.some((c) => c.includes('draft-stale/complete'))).toBe(false)
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
