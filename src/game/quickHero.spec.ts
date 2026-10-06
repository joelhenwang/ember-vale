import { describe, expect, it } from 'vitest'
import { checkHero, heroDraft, heroPreset } from './quickHero'

const cast = {
  world: { id: 'vale', revision: 2 },
  hero: { id: 'h1', revision: 1 },
  companions: [
    { name: 'Wren', ref: { id: 'w', revision: 1 }, at: 'hearth' },
    { name: 'Ash', ref: { id: 'a', revision: 1 }, at: 'market' }
  ]
}

describe('quick hero', () => {
  it('needs a name and trims what it keeps', () => {
    expect(checkHero({ name: '  ', about: '', pronouns: '' })).toEqual({
      problem: 'Give your hero a name.'
    })
    expect(checkHero({ name: ' Mira ', about: ' A tinker. ', pronouns: ' she/her ' })).toEqual({
      hero: { name: 'Mira', about: 'A tinker.', pronouns: 'she/her' }
    })
  })

  it('makes the description the hero’s appearance', () => {
    expect(
      heroPreset({ name: 'Mira', about: 'A tinker with soot on her cheek.', pronouns: '' })
    ).toMatchObject({
      kind: 'character',
      name: 'Mira',
      appearance: 'A tinker with soot on her cheek.',
      pronouns: null
    })
  })

  it('casts you as the player at the Hearth with the companions about', () => {
    const draft = heroDraft({ name: 'Mira', about: '', pronouns: '' }, cast)
    expect(draft?.mode).toEqual({ role: 'player', controlled_cast_key: 'hero' })
    expect(draft?.cast?.map((c) => [c.instance_key, c.location_key])).toEqual([
      ['hero', 'hearth'],
      ['wren', 'hearth'],
      ['ash', 'market']
    ])
    expect(draft?.story?.title).toBe("Mira's Tale")
  })

  it('never casts a companion twice under the hero’s own name', () => {
    const draft = heroDraft({ name: 'Wren', about: '', pronouns: '' }, cast)
    expect(draft?.cast?.map((c) => c.instance_key)).toEqual(['hero', 'ash'])
  })
})
