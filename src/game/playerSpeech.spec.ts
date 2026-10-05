import { describe, expect, it } from 'vitest'
import { inputLimit, stripOuterQuotes, topicFor } from './playerSpeech'

describe('playerSpeech', () => {
  it('Say wraps the exact words in quotes', () => {
    expect(topicFor('Is the mill road open?', 'say')).toBe('"Is the mill road open?"')
  })

  it('does not double-quote words the player already quoted', () => {
    expect(topicFor('"Is it open?"', 'say')).toBe('"Is it open?"')
    expect(topicFor('“Is it open?”', 'say')).toBe('"Is it open?"')
  })

  it('About sends a bare topic, even if the player typed quotes', () => {
    expect(topicFor('the mill road', 'about')).toBe('the mill road')
    expect(topicFor('"the mill road"', 'about')).toBe('the mill road')
  })

  it('keeps inner quotes and apostrophes', () => {
    expect(topicFor("It's 'fine', she said", 'say')).toBe(`"It's 'fine', she said"`)
    expect(stripOuterQuotes("'quoted'")).toBe('quoted')
  })

  it('leaves room for the quotes within the backend topic limit', () => {
    expect(inputLimit('say')).toBe(254)
    expect(inputLimit('about')).toBe(256)
    expect(topicFor('x'.repeat(254), 'say')).toHaveLength(256)
  })
})
