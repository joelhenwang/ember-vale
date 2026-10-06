/**
 * Image generation preferences (Krea 2 Studio fields), mirrored from the
 * backend's ImagePrefs. Kept Vue-free: defaults, validation, labels and
 * the per-image time estimate the settings page shows next to each choice.
 *
 * Timings come from krea2-studio docs/API.md (measured 2026-09-24/25 on a
 * power-saver profile, so they are upper bounds).
 */

export type ImageMode = 'draft' | 'fast' | 'full'
export type SeedMode = 'stable' | 'random' | 'fixed'
export type ImageRatio = '1:1' | '16:9' | '9:16' | '3:2' | '2:3' | '4:3' | '3:4'

export interface ImagePrefs {
  enabled: boolean
  checkpoint: string | null
  mode: ImageMode
  seed_mode: SeedMode
  seed: number
  detail: boolean
  detail_scale: number
  turbo: boolean
  steps: number | null
  style: string | null
  style_scale: number
  portrait_ratio: ImageRatio | null
  place_ratio: ImageRatio | null
}

export const PREFERRED_CHECKPOINT = 'krea2Anime_v15_bf16'

export const DEFAULT_IMAGE_PREFS: ImagePrefs = {
  enabled: true,
  checkpoint: PREFERRED_CHECKPOINT,
  mode: 'fast',
  seed_mode: 'stable',
  seed: 0,
  detail: true,
  detail_scale: 1,
  turbo: true,
  steps: null,
  style: 'kreanima-lora-r32',
  style_scale: 1,
  portrait_ratio: null,
  place_ratio: null
}

export const IMAGE_RATIOS: readonly ImageRatio[] = [
  '1:1',
  '16:9',
  '9:16',
  '3:2',
  '2:3',
  '4:3',
  '3:4'
]
export const IMAGE_STEPS: readonly number[] = [4, 6, 8, 10, 12, 16, 20]
export const MAX_SEED = 2 ** 31 - 1

export const MODE_OPTIONS: ReadonlyArray<{ value: ImageMode; label: string; hint: string }> = [
  { value: 'draft', label: 'Draft', hint: '~768 px, quickest' },
  { value: 'fast', label: 'Fast', hint: '~1024 px, recommended' },
  { value: 'full', label: 'Full', hint: '~1024 px, ~35% slower, finest' }
]

export const SEED_OPTIONS: ReadonlyArray<{ value: SeedMode; label: string; hint: string }> = [
  {
    value: 'stable',
    label: 'Stable',
    hint: 'Each character or place keeps its own seed, so a redraw looks the same.'
  },
  { value: 'random', label: 'Random', hint: 'A new seed every time: every redraw differs.' },
  { value: 'fixed', label: 'Fixed', hint: 'One seed for everything (good for comparing settings).' }
]

/** Readable name for a checkpoint id ("krea2Anime_v15_bf16" → "Krea2 Anime v15"). */
export function checkpointLabel(id: string): string {
  const known: Record<string, string> = {
    krea2Anime_v15_bf16: 'Krea 2 Anime v1.5',
    serendipity_v30_bf16: 'Serendipity v3.0 (photoreal)',
    animosity_krea2Ver10Turbo: 'Animosity v1.0 Turbo'
  }
  return known[id] ?? id
}

/** Field errors keyed by preference name; empty when the form can be saved. */
export function validateImagePrefs(p: ImagePrefs): Partial<Record<keyof ImagePrefs, string>> {
  const errors: Partial<Record<keyof ImagePrefs, string>> = {}
  const scale = (v: number) => Number.isFinite(v) && v >= 0 && v <= 2
  if (!scale(p.detail_scale)) errors.detail_scale = 'Between 0 and 2.'
  if (!scale(p.style_scale)) errors.style_scale = 'Between 0 and 2.'
  if (!Number.isInteger(p.seed) || p.seed < 0 || p.seed > MAX_SEED) {
    errors.seed = `A whole number from 0 to ${MAX_SEED}.`
  }
  if (p.steps !== null && !IMAGE_STEPS.includes(p.steps)) {
    errors.steps = `One of ${IMAGE_STEPS.join(', ')}.`
  }
  return errors
}

/** Server preferences (possibly older or partial) as a complete form. */
export function imagePrefsFrom(raw: Record<string, unknown> | undefined): ImagePrefs {
  return { ...DEFAULT_IMAGE_PREFS, ...(raw as Partial<ImagePrefs> | undefined) }
}

/**
 * Seconds one image should take with these choices on an idle service.
 * The detail LoRA is free at strength 1; any other strength (or off)
 * swaps weights (~+4 s). Turbo off runs 8 steps by default (~24 s).
 */
export function estimateSeconds(p: ImagePrefs): number {
  const turboSteps = 4
  const steps = p.steps ?? (p.turbo ? turboSteps : 8)
  // Sampling dominates: ~2.6 s a step at 1024 px, plus ~1.1 s of fixed work.
  let seconds = p.turbo ? 11.5 * (steps / turboSteps) : 24 * (steps / 8)
  if (p.mode === 'full') seconds *= 1.35
  if (p.mode === 'draft') seconds *= 0.6
  const detailOn = p.detail && p.detail_scale > 0
  if (!detailOn || p.detail_scale !== 1) seconds += 4
  if (p.style) seconds += 0.9
  return Math.round(seconds)
}

/** True when the chosen checkpoint differs from the one the service has loaded. */
export function switchesCheckpoint(p: ImagePrefs, loaded: string | null | undefined): boolean {
  return Boolean(p.checkpoint && loaded && p.checkpoint !== loaded)
}
