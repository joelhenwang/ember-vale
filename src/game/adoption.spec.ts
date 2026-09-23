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
  draftId: 'draft-a',
  created: false
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
    ).toEqual({
      kind: 'character',
      presetId: 'char-1',
      revision: 3,
      draftId: 'draft-a',
      created: false
    })
    expect(
      parseAdoptionOffer({
        adopt_kind: 'world',
        adopt_preset: 'world-9',
        adopt_revision: '1',
        adopt_draft: 'draft-a',
        adopt_created: '1'
      })
    ).toEqual({
      kind: 'world',
      presetId: 'world-9',
      revision: 1,
      draftId: 'draft-a',
      created: true
    })
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
      draftId: 'draft-a',
      created: false
    }
    expect(planAdoption(world, sel, 'draft-a', true)).toEqual({ kind: 'apply-world' })
    expect(planAdoption(world, sel, 'draft-a', false)).toEqual({ kind: 'unknown-target' })
    expect(planAdoption(world, sel, 'draft-b', true)).toEqual({ kind: 'stale-draft' })
  })

  it('plans a known-character add, a full cast, and unknown characters', () => {
    const sel = selections()
    const created: AdoptionOffer = {
      kind: 'character',
      presetId: 'char-9',
      revision: 1,
      draftId: 'draft-a',
      created: true
    }
    // A preset outside the cast and off the shelf is unknown.
    expect(planAdoption(created, sel, 'draft-a', true)).toEqual({ kind: 'unknown-target' })
    expect(planAdoption(created, sel, 'draft-a', true, false)).toEqual({
      kind: 'unknown-target'
    })
    // A known preset outside a non-full cast joins on explicit accept.
    expect(planAdoption(created, sel, 'draft-a', true, true)).toEqual({
      kind: 'apply-character-add'
    })
    expect(planAdoption(created, sel, 'draft-b', true, true)).toEqual({ kind: 'stale-draft' })
    // A full cast cannot take another member.
    const full = {
      ...sel,
      cast: [
        ...sel.cast,
        ...[3, 4, 5, 6].map((i) => ({
          key: `extra-${i}`,
          presetId: `char-extra-${i}`,
          presetRevision: 1,
          name: `Extra ${i}`,
          locationKey: 'hearth'
        }))
      ]
    }
    expect(full.cast).toHaveLength(6)
    expect(planAdoption(created, full, 'draft-a', true, true)).toEqual({ kind: 'cast-full' })
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
      draftId: 'draft-a',
      created: false
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
      controlledKey: undefined,
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
      controlledKey: undefined,
      cast: [
        { key: 'wren', presetRevision: 2, location: 'hearth' },
        { key: 'ash', presetRevision: 1, location: 'market' }
      ]
    })
  })

  it('carries the controlled selection through snapshot, compare, and restore', () => {
    const base = selections()
    const player: NewStorySelections = {
      ...base,
      mode: { role: 'player', controlledKey: 'wren' }
    }
    const snapshot = snapshotPins(player)
    expect(snapshot.controlledKey).toBe('wren')
    expect(pinsEqual(snapshot, player)).toBe(true)
    // A changed controlled selection breaks equality: the wizard treats
    // it as an intervening user edit and skips the restore.
    const reselected: NewStorySelections = {
      ...player,
      mode: { role: 'player', controlledKey: 'ash' }
    }
    expect(pinsEqual(snapshot, reselected)).toBe(false)
    // Restoring returns the original controlled selection.
    const live: RestorablePins = {
      worldId: player.world.presetId,
      worldRev: player.world.presetRevision,
      controlledKey: 'ash',
      cast: player.cast.map((m) => ({
        key: m.key,
        presetRevision: m.presetRevision,
        location: m.locationKey ?? ''
      }))
    }
    restoreSnapshot(live, snapshot)
    expect(live.controlledKey).toBe('wren')
  })

  it('restores no-control after a character add controlled the newcomer', () => {
    const base = selections()
    // Player mode with no controlled character and a lone Wren.
    const uncontrolled: NewStorySelections = {
      ...base,
      cast: [base.cast[0]!],
      mode: { role: 'player' }
    }
    const snapshot = snapshotPins(uncontrolled)
    expect(snapshot.controlledKey).toBeUndefined()
    // The failed accept added char-9 and controlled it.
    const attempted: NewStorySelections = {
      ...uncontrolled,
      cast: [
        ...uncontrolled.cast,
        {
          key: 'char-9',
          presetId: 'char-9',
          presetRevision: 1,
          name: 'Nova',
          locationKey: 'hearth'
        }
      ],
      mode: { role: 'player', controlledKey: 'char-9' }
    }
    expect(pinsEqual(snapshot, attempted)).toBe(false)
    // Dismissal drops the added member (absent from the rollback) and
    // restores the original uncontrolled selection — never a controlled
    // key pointing at a removed cast member.
    const live: RestorablePins = {
      worldId: attempted.world.presetId,
      worldRev: attempted.world.presetRevision,
      controlledKey: 'char-9',
      cast: attempted.cast.map((m) => ({
        key: m.key,
        presetRevision: m.presetRevision,
        location: m.locationKey ?? ''
      }))
    }
    const kept = live.cast.filter((m) => m.key in snapshot.castRevs)
    const restored: RestorablePins = { ...live, cast: kept }
    restoreSnapshot(restored, snapshot)
    expect(restored.cast.map((m) => m.key)).toEqual(['wren'])
    expect(restored.controlledKey).toBeUndefined()
  })

  it('tracks starting locations through adoption and rollback', () => {
    const before = selections()
    const snapshot = snapshotPins(before)
    // Reconciliation reset a member's starting location…
    const live: RestorablePins = {
      worldId: 'world-1',
      worldRev: 4,
      controlledKey: undefined,
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
