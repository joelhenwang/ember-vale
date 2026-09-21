import { describe, expect, it } from 'vitest'
import {
  buildDraftPayload,
  controlledAfterCastChange,
  localDraftIssues,
  rehomeInvalidLocations,
  type NewStorySelections
} from './drafting'

const BASE: NewStorySelections = {
  world: { presetId: 'world-id', presetRevision: 2 },
  cast: [
    { key: 'wren', presetId: 'wren-id', presetRevision: 1, name: 'Wren', locationKey: 'hearth' },
    { key: 'ash', presetId: 'ash-id', presetRevision: 1, name: 'Ash', locationKey: 'market' }
  ],
  mode: { role: 'watcher' },
  title: 'A Morning in Ember Vale',
  tone: 'hopeful mystery'
}

describe('draft payload', () => {
  it('pins exact preset revisions and instance keys', () => {
    const payload = buildDraftPayload(BASE)
    expect(payload['world']).toMatchObject({ preset_id: 'world-id', preset_revision: 2 })
    const cast = payload['cast'] as Record<string, unknown>[]
    expect(cast.map((c) => c['instance_key'])).toEqual(['wren', 'ash'])
    expect(cast[0]).toMatchObject({ preset_revision: 1, location_key: 'hearth' })
    expect(payload['mode']).toEqual({ role: 'watcher' })
    expect(payload['ai']).toEqual({ art_source: 'curated' })
  })

  it('carries the controlled key only for player mode', () => {
    const payload = buildDraftPayload({
      ...BASE,
      mode: { role: 'player', controlledKey: 'wren' }
    })
    expect(payload['mode']).toEqual({ role: 'player', controlled_cast_key: 'wren' })
  })

  it('flags empty cast, missing title and bad controlled selection', () => {
    expect(localDraftIssues({ ...BASE, cast: [] })).toContain('select at least one character')
    expect(localDraftIssues({ ...BASE, title: '  ' })).toContain('give the story a title')
    expect(localDraftIssues({ ...BASE, mode: { role: 'player' } })).toContain(
      'player mode needs a controlled character'
    )
    expect(
      localDraftIssues({ ...BASE, mode: { role: 'player', controlledKey: 'nope' } })
    ).toContain('controlled character is not in the cast')
    expect(localDraftIssues(BASE)).toEqual([])
  })

  it('clears the controlled selection when its cast member leaves', () => {
    expect(controlledAfterCastChange(['wren', 'ash'], 'wren')).toBe('wren')
    expect(controlledAfterCastChange(['ash'], 'wren')).toBeUndefined()
    expect(controlledAfterCastChange(['ash'], undefined)).toBeUndefined()
  })

  it('re-homes only locations absent from the new world', () => {
    const members = [
      { presetId: 'wren-id', location: 'hearth' },
      { presetId: 'ash-id', location: 'deepwood' },
      { presetId: 'birch-id', location: '' }
    ]
    const reset = rehomeInvalidLocations(
      members,
      new Set(['hearth', 'market']),
      (presetId) => `${presetId}-fallback`
    )
    expect(reset).toBe(1)
    expect(members.map((m) => m.location)).toEqual(['hearth', 'ash-id-fallback', ''])
  })
})
