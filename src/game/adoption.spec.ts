import { describe, expect, it } from 'vitest'
import {
  applyAdoption,
  offerTargetsDraft,
  pinsEqual,
  planAdoption,
  parseAdoptionOffer,
  restoreSnapshot,
  snapshotPins,
  type AdoptionOffer,
  type RestorablePins
} from './adoption'
import type { NewStorySelections } from './drafting'

function selections(): NewStorySelections {
  return {
    world: { presetId: 'world-1', presetRevision: 2 },
    cast: [
      {
        key: 'wren',
        presetId: 'char-1',
        presetRevision: 2,
        name: 'Wren',
        locationKey: 'hearth'
      },
      {
        key: 'ash',
        presetId: 'char-2',
        presetRevision: 1,
        name: 'Ash',
        locationKey: 'market'
      }
    ],
    mode: { role: 'watcher' },
    title: 'A Morning in Ember Vale',
    tone: 'hopeful mystery'
  }
}

const offer: AdoptionOffer = {
  kind: 'character',
  presetId: 'char-1',
  revision: 3,
  draftId: 'draft-a'
}

describe('nested adoption', () => {
  it('parses a well-formed offer and rejects stray query content', () => {
    expect(
      parseAdoptionOffer({
        adopt_kind: 'character',
        adopt_preset: 'char-1',
        adopt_revision: '3',
        adopt_draft: 'draft-a'
      })
    ).toEqual({ kind: 'character', presetId: 'char-1', revision: 3, draftId: 'draft-a' })
    expect(parseAdoptionOffer({})).toBeNull()
    expect(parseAdoptionOffer({ adopt_kind: 'character', adopt_preset: 'char-1' })).toBeNull()
    expect(
      parseAdoptionOffer({
        adopt_kind: 'spell',
        adopt_preset: 'char-1',
        adopt_revision: '3',
        adopt_draft: 'draft-a'
      })
    ).toBeNull()
  })

  it('requires the originating story draft on every offer', () => {
    expect(
      parseAdoptionOffer({
        adopt_kind: 'world',
        adopt_preset: 'world-1',
        adopt_revision: '4'
      })
    ).toBeNull()
    expect(
      parseAdoptionOffer({
        adopt_kind: 'world',
        adopt_preset: 'world-1',
        adopt_revision: '4',
        adopt_draft: ''
      })
    ).toBeNull()
  })

  it('binds offers to their originating draft only', () => {
    expect(offerTargetsDraft(offer, 'draft-a')).toBe(true)
    expect(offerTargetsDraft(offer, 'draft-b')).toBe(false)
    expect(offerTargetsDraft(offer, null)).toBe(false)
  })

  it('plans application, staleness, and unknown targets without touching state', () => {
    const sel = selections()
    expect(planAdoption(offer, sel, 'draft-a', true)).toEqual({ kind: 'apply-character' })
    expect(planAdoption(offer, sel, 'draft-b', true)).toEqual({ kind: 'stale-draft' })
    expect(planAdoption({ ...offer, presetId: 'char-9' }, sel, 'draft-a', true)).toEqual({
      kind: 'unknown-target'
    })
    const world: AdoptionOffer = {
      kind: 'world',
      presetId: 'world-1',
      revision: 4,
      draftId: 'draft-a'
    }
    expect(planAdoption(world, sel, 'draft-a', true)).toEqual({ kind: 'apply-world' })
    expect(planAdoption(world, sel, 'draft-a', false)).toEqual({ kind: 'unknown-target' })
    expect(planAdoption(world, sel, 'draft-b', true)).toEqual({ kind: 'stale-draft' })
  })

  it('pins the published revision on the matching cast member only', () => {
    const before = selections()
    const after = applyAdoption(before, offer)
    expect(after.cast.find((m) => m.key === 'wren')?.presetRevision).toBe(3)
    expect(after.cast.find((m) => m.key === 'ash')?.presetRevision).toBe(1)
    expect(after.world).toEqual(before.world)
  })

  it('a character offer with no matching member changes nothing', () => {
    const before = selections()
    expect(applyAdoption(before, { ...offer, presetId: 'char-9' })).toEqual(before)
  })

  it('a world offer re-pins the world and leaves the cast alone', () => {
    const before = selections()
    const after = applyAdoption(before, {
      kind: 'world',
      presetId: 'world-1',
      revision: 4,
      draftId: 'draft-a'
    })
    expect(after.world).toEqual({ presetId: 'world-1', presetRevision: 4 })
    expect(after.cast).toEqual(before.cast)
  })

  it('snapshots pins so a failed accept can roll back on dismiss', () => {
    const before = selections()
    const snapshot = snapshotPins(before)
    expect(pinsEqual(snapshot, before)).toBe(true)
    const after = applyAdoption(before, offer)
    expect(pinsEqual(snapshot, after)).toBe(false)
    // Restoring the snapshot is exact: revisions and locations return.
    const live: RestorablePins = {
      worldId: after.world.presetId,
      worldRev: after.world.presetRevision,
      cast: after.cast.map((m) => ({
        key: m.key,
        presetRevision: m.presetRevision,
        location: m.locationKey ?? ''
      }))
    }
    restoreSnapshot(live, snapshot)
    expect(live).toEqual({
      worldId: 'world-1',
      worldRev: 2,
      cast: [
        { key: 'wren', presetRevision: 2, location: 'hearth' },
        { key: 'ash', presetRevision: 1, location: 'market' }
      ]
    })
  })

  it('tracks starting locations through adoption and rollback', () => {
    const before = selections()
    const snapshot = snapshotPins(before)
    // Reconciliation reset a member's starting location…
    const live: RestorablePins = {
      worldId: 'world-1',
      worldRev: 4,
      cast: [
        { key: 'wren', presetRevision: 3, location: 'market' },
        { key: 'ash', presetRevision: 1, location: 'market' }
      ]
    }
    const asSelections: NewStorySelections = {
      ...before,
      world: { presetId: live.worldId, presetRevision: live.worldRev },
      cast: before.cast.map((m) => {
        const peer = live.cast.find((c) => c.key === m.key)!
        return { ...m, presetRevision: peer.presetRevision, locationKey: peer.location }
      })
    }
    expect(pinsEqual(snapshot, asSelections)).toBe(false)
    // …and dismissal puts the original revision and location back.
    restoreSnapshot(live, snapshot)
    expect(live.cast[0]).toEqual({ key: 'wren', presetRevision: 2, location: 'hearth' })
  })

  it('leaves intervening user edits alone on dismiss', () => {
    const before = selections()
    const snapshot = snapshotPins(before)
    // The user re-pinned Wren themselves after the failed accept: the
    // live pins no longer match the attempted state, so the guard in
    // the wizard skips the restore and their choice stands.
    const edited: NewStorySelections = {
      ...before,
      cast: before.cast.map((m) => (m.key === 'wren' ? { ...m, presetRevision: 9 } : m))
    }
    expect(pinsEqual(snapshot, edited)).toBe(false)
  })

  it('journey proof: a new story uses the adopted revision while the original stays unchanged', () => {
    const original = selections()
    const snapshot = JSON.parse(JSON.stringify(original)) as NewStorySelections
    // Revision 3 of char-1 was just published; the new story adopts it.
    const next = applyAdoption(original, offer)
    expect(next.cast.find((m) => m.key === 'wren')?.presetRevision).toBe(3)
    // The original story draft is untouched: same pins, same everything.
    expect(original).toEqual(snapshot)
    expect(original.cast.find((m) => m.key === 'wren')?.presetRevision).toBe(2)
  })
})
