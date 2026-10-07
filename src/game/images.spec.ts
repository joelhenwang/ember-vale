import { describe, expect, it } from 'vitest'
import { resolveImage, setGeneratedImage } from './images'

describe('image registry', () => {
  it('prefers a generated override once the pipeline delivers one', () => {
    setGeneratedImage('world.map', '/generated/map-v2.png')
    expect(resolveImage('world.map')).toBe('/generated/map-v2.png')
  })
})
