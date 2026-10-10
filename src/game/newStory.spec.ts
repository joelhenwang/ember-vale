import { describe, expect, it } from 'vitest'
import {
  namesLine,
  placesLine,
  searchWorlds,
  storytellerName,
  toneLabel,
  watchedParty
} from './newStory'

describe('new story words', () => {
  it('seats the first four of the cast as a watched party', () => {
    expect(watchedParty(['Wren', 'Ash'])).toEqual({ party: ['Wren', 'Ash'], left: [] })
    expect(watchedParty(['A', 'B', 'C', 'D', 'E'])).toEqual({
      party: ['A', 'B', 'C', 'D'],
      left: ['E']
    })
    expect(namesLine(['Wren', 'Ash', 'Lyra'])).toBe('Wren, Ash and Lyra')
    expect(namesLine(['Wren'])).toBe('Wren')
    expect(namesLine([])).toBe('')
  })

  it('names the storyteller plainly', () => {
    expect(storytellerName('active:venice')).toBe('Venice')
    expect(storytellerName('active:openrouter')).toBe('OpenRouter')
    expect(storytellerName('active:fake')).toBe('Practice storyteller (no live model)')
    expect(storytellerName(null)).toBe('Not known yet')
    expect(storytellerName('mistral:nemo')).toBe('Mistral')
  })

  it('reads a tone as a label', () => {
    expect(toneLabel(' hopeful mystery ')).toBe('Hopeful mystery')
    expect(toneLabel('')).toBe('')
  })

  it('finds worlds by name, description or place', () => {
    const worlds = [
      { name: 'The Saltreach', description: 'Tidebound islands.', places: [{ name: 'Mirewake' }] },
      { name: 'Ember Vale', description: 'A sheltered vale.', places: [{ name: 'Hearth' }] }
    ]
    expect(searchWorlds(worlds, 'mire').map((w) => w.name)).toEqual(['The Saltreach'])
    expect(searchWorlds(worlds, 'vale hearth').map((w) => w.name)).toEqual(['Ember Vale'])
    expect(searchWorlds(worlds, '  ')).toHaveLength(2)
  })

  it('lists the first places with the count', () => {
    const places = ['A', 'B', 'C', 'D'].map((name) => ({ name }))
    expect(placesLine(places)).toBe('4 places · A · B · C')
    expect(placesLine([{ name: 'Hearth' }])).toBe('1 place · Hearth')
  })
})
