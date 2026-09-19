import { describe, expect, it } from 'vitest'
import { resolveImage, setGeneratedImage } from './images'

describe('image registry', () => {
  it('resolves every slot to a bundled placeholder by default', () => {
    expect(resolveImage('character.miri')).toBe('/images/character-miri.webp')
    expect(resolveImage('world.map')).toContain('/images/')
  })
  it('prefers a generated override once the pipeline delivers one', () => {
    setGeneratedImage('world.map', '/generated/map-v2.png')
    expect(resolveImage('world.map')).toBe('/generated/map-v2.png')
  })
})
