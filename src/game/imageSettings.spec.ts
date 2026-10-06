import { describe, expect, it } from 'vitest'
import {
  DEFAULT_IMAGE_PREFS,
  checkpointLabel,
  estimateSeconds,
  imagePrefsFrom,
  switchesCheckpoint,
  validateImagePrefs
} from './imageSettings'

describe('image settings', () => {
  it('fills older or partial server preferences with defaults', () => {
    const prefs = imagePrefsFrom({ mode: 'draft' })
    expect(prefs.mode).toBe('draft')
    expect(prefs.checkpoint).toBe('krea2Anime_v15_bf16')
    expect(imagePrefsFrom(undefined)).toEqual(DEFAULT_IMAGE_PREFS)
  })

  it('validates strengths, seeds and steps', () => {
    expect(validateImagePrefs(DEFAULT_IMAGE_PREFS)).toEqual({})
    const bad = validateImagePrefs({
      ...DEFAULT_IMAGE_PREFS,
      detail_scale: 2.5,
      style_scale: -1,
      seed: 1.5,
      steps: 5
    })
    expect(Object.keys(bad).sort()).toEqual(['detail_scale', 'seed', 'steps', 'style_scale'])
  })

  it('estimates what each choice costs', () => {
    const base = estimateSeconds(DEFAULT_IMAGE_PREFS)
    expect(base).toBe(12) // 11.5 s + the style
    expect(estimateSeconds({ ...DEFAULT_IMAGE_PREFS, detail_scale: 1.3 })).toBe(base + 4)
    expect(estimateSeconds({ ...DEFAULT_IMAGE_PREFS, detail: false })).toBe(base + 4)
    expect(estimateSeconds({ ...DEFAULT_IMAGE_PREFS, turbo: false })).toBeGreaterThan(20)
    expect(estimateSeconds({ ...DEFAULT_IMAGE_PREFS, mode: 'draft' })).toBeLessThan(base)
    expect(estimateSeconds({ ...DEFAULT_IMAGE_PREFS, mode: 'full' })).toBeGreaterThan(base)
  })

  it('knows when a checkpoint switch would happen', () => {
    expect(switchesCheckpoint(DEFAULT_IMAGE_PREFS, 'krea2Anime_v15_bf16')).toBe(false)
    expect(switchesCheckpoint(DEFAULT_IMAGE_PREFS, 'serendipity_v30_bf16')).toBe(true)
    expect(switchesCheckpoint(DEFAULT_IMAGE_PREFS, null)).toBe(false)
    expect(checkpointLabel('krea2Anime_v15_bf16')).toBe('Krea 2 Anime v1.5')
    expect(checkpointLabel('mystery')).toBe('mystery')
  })
})
