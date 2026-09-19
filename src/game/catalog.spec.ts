import { describe, expect, it } from 'vitest'
import { catalog, selectedCharacters, toggleCharacter, wizard } from './catalog'

describe('wizard cast selection', () => {
  it('toggleCharacter round-trips against the seeded selection', () => {
    const start = [...wizard.selected]
    expect(selectedCharacters.value.length).toBe(start.length)

    toggleCharacter('nessa')
    expect(wizard.selected).toContain('nessa')
    expect(selectedCharacters.value.some((c) => c.id === 'nessa')).toBe(true)

    toggleCharacter('nessa')
    expect(wizard.selected).not.toContain('nessa')
    expect(wizard.selected).toEqual(start)
  })

  it('selected characters all exist in the catalog', () => {
    for (const c of selectedCharacters.value) {
      expect(catalog.characters.map((x) => x.id)).toContain(c.id)
    }
  })
})
