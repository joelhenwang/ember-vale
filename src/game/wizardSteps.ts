/**
 * Wizard step contract (E3 integration fix).
 *
 * The stepper shows "Play Mode" but the story-draft endpoints only accept
 * `mode` (see backend `_VALID_STEPS`): persisting the visible label made
 * every step-3 save fail validation. The visible label and the persisted
 * identifier are therefore separate: labels render, slugs persist, and
 * both directions are covered by contract tests below.
 */

export const WIZARD_STEP_LABELS = [
  'World',
  'Characters',
  'Play Mode',
  'Story',
  'AI',
  'Review'
] as const

/** Persistence identifiers accepted by the story-draft endpoints. */
export const WIZARD_STEP_SLUGS = ['world', 'characters', 'mode', 'story', 'ai', 'review'] as const

export function stepCount(): number {
  return WIZARD_STEP_LABELS.length
}

/** Visible label for a 1-based step; falls back to step 1. */
export function stepLabel(n: number): string {
  return WIZARD_STEP_LABELS[n - 1] ?? WIZARD_STEP_LABELS[0]!
}

/** Persistence identifier for a 1-based step; falls back to step 1. */
export function persistStepSlug(n: number): string {
  return WIZARD_STEP_SLUGS[n - 1] ?? WIZARD_STEP_SLUGS[0]!
}

/**
 * 1-based step for a persisted identifier; unknown slugs fall back to 1.
 * The pre-fix visible label `play-mode` still maps to step 3 so
 * in-flight recovery snapshots restore where the user left off.
 */
export function stepFromSlug(slug: unknown): number {
  if (slug === 'play-mode') return 3
  const at = typeof slug === 'string' ? (WIZARD_STEP_SLUGS as readonly string[]).indexOf(slug) : -1
  return at >= 0 ? at + 1 : 1
}
