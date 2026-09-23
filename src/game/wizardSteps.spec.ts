import { describe, expect, it } from 'vitest'
import {
  persistStepSlug,
  stepCount,
  stepFromSlug,
  stepLabel,
  WIZARD_STEP_LABELS,
  WIZARD_STEP_SLUGS
} from './wizardSteps'

// Mirror of backend `_VALID_STEPS` (routes/stories.py): the only
// persistence identifiers the story-draft endpoints accept.
const BACKEND_STEPS = ['world', 'characters', 'mode', 'story', 'ai', 'review']

describe('wizardSteps', () => {
  it('covers all six steps with labels and backend-valid slugs', () => {
    expect(stepCount()).toBe(6)
    expect(WIZARD_STEP_LABELS).toHaveLength(6)
    expect(WIZARD_STEP_SLUGS).toHaveLength(6)
    expect(stepLabel(3)).toBe('Play Mode')
    for (let n = 1; n <= 6; n++) {
      // Every step persists an identifier the backend accepts…
      expect(BACKEND_STEPS).toContain(persistStepSlug(n))
      // …and every persisted identifier restores its step.
      expect(stepFromSlug(persistStepSlug(n))).toBe(n)
    }
    // Step 3 keeps the Play Mode label while persisting `mode`.
    expect(persistStepSlug(3)).toBe('mode')
  })

  it('falls back safely on unknown input', () => {
    expect(stepFromSlug('play-mode')).toBe(3)
    expect(stepFromSlug('nope')).toBe(1)
    expect(stepFromSlug('review')).toBe(6)
    expect(stepFromSlug(undefined)).toBe(1)
    expect(stepFromSlug(42)).toBe(1)
    expect(persistStepSlug(0)).toBe('world')
    expect(persistStepSlug(99)).toBe('world')
    expect(stepLabel(0)).toBe('World')
  })
})
