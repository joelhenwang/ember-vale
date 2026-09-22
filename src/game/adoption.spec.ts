import { describe, expect, it } from 'vitest'
import { applyAdoption, parseAdoptionOffer } from './adoption'
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

describe('nested adoption', () => {
  it('parses a well-formed offer and rejects stray query content', () => {
    expect(
      parseAdoptionOffer({
        adopt_kind: 'character',
        adopt_preset: 'char-1',
        adopt_revision: '3'
      })
    ).toEqual({ kind: 'character', presetId: 'char-1', revision: 3 })
    expect(parseAdoptionOffer({})).toBeNull()
    expect(parseAdoptionOffer({ adopt_kind: 'character', adopt_preset: 'char-1' })).toBeNull()
    expect(
      parseAdoptionOffer({
        adopt_kind: 'spell',
        adopt_preset: 'char-1',
        adopt_revision: '3'
      })
    ).toBeNull()
  })

  it('pins the published revision on the matching cast member only', () => {
    const before = selections()
    const after = applyAdoption(before, {
      kind: 'character',
      presetId: 'char-1',
      revision: 3
    })
    expect(after.cast.find((m) => m.key === 'wren')?.presetRevision).toBe(3)
    expect(after.cast.find((m) => m.key === 'ash')?.presetRevision).toBe(1)
    expect(after.world).toEqual(before.world)
  })

  it('a character offer with no matching member changes nothing', () => {
    const before = selections()
    expect(applyAdoption(before, { kind: 'character', presetId: 'char-9', revision: 5 })).toEqual(
      before
    )
  })

  it('a world offer re-pins the world and leaves the cast alone', () => {
    const before = selections()
    const after = applyAdoption(before, {
      kind: 'world',
      presetId: 'world-1',
      revision: 4
    })
    expect(after.world).toEqual({ presetId: 'world-1', presetRevision: 4 })
    expect(after.cast).toEqual(before.cast)
  })

  it('journey proof: a new story uses the adopted revision while the original stays unchanged', () => {
    const original = selections()
    const snapshot = JSON.parse(JSON.stringify(original)) as NewStorySelections
    // Revision 3 of char-1 was just published; the new story adopts it.
    const next = applyAdoption(original, {
      kind: 'character',
      presetId: 'char-1',
      revision: 3
    })
    expect(next.cast.find((m) => m.key === 'wren')?.presetRevision).toBe(3)
    // The original story draft is untouched: same pins, same everything.
    expect(original).toEqual(snapshot)
    expect(original.cast.find((m) => m.key === 'wren')?.presetRevision).toBe(2)
  })
})
