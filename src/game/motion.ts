/**
 * Motion preference: follow the system, or choose full or reduced motion.
 *
 * Kept per device (a viewer's own comfort, not game state). The choice is
 * written onto <html data-motion="…"> so plain CSS can follow it:
 *   - "full"    — every animation plays, whatever the system says
 *   - "reduced" — no movement; colour and opacity fades stay (they do not
 *                 cause motion sickness), progress spinners keep turning
 *   - "system"  — no attribute; `prefers-reduced-motion` decides
 */

export type MotionChoice = 'system' | 'full' | 'reduced'

export const MOTION_CHOICES: readonly { key: MotionChoice; label: string; hint: string }[] = [
  {
    key: 'system',
    label: 'Follow my computer',
    hint: 'Uses your system’s “reduce motion” or “animation effects” setting.'
  },
  {
    key: 'full',
    label: 'Full motion',
    hint: 'Pages slide, pictures drift and cards lift, whatever the system says.'
  },
  {
    key: 'reduced',
    label: 'Reduced motion',
    hint: 'Nothing moves across the screen; things fade in and out instead.'
  }
]

const KEY = 'ev.motion'

export function parseMotion(raw: string | null | undefined): MotionChoice {
  return raw === 'full' || raw === 'reduced' ? raw : 'system'
}

export function readMotion(storage: Pick<Storage, 'getItem'> | undefined): MotionChoice {
  try {
    return parseMotion(storage?.getItem(KEY))
  } catch {
    return 'system'
  }
}

export function writeMotion(
  storage: Pick<Storage, 'setItem' | 'removeItem'> | undefined,
  choice: MotionChoice
): void {
  try {
    if (choice === 'system') storage?.removeItem(KEY)
    else storage?.setItem(KEY, choice)
  } catch {
    // private window or blocked storage: the choice lasts this visit only
  }
}

export function applyMotion(root: HTMLElement | undefined, choice: MotionChoice): void {
  if (!root) return
  if (choice === 'system') delete root.dataset.motion
  else root.dataset.motion = choice
}

/** Whether movement should play right now (for script-driven motion). */
export function motionAllowed(choice: MotionChoice, systemReduces: boolean): boolean {
  if (choice === 'full') return true
  if (choice === 'reduced') return false
  return !systemReduces
}

/* ————— resting: ambient loops pause when nobody is there ————— */

/** Quiet time after which the ambient loops rest (any input wakes them). */
export const REST_AFTER_MS = 60_000

/*
 * Decorative loops that may rest: drifting pictures, embers, breathing
 * rings, idle bobs, birds, ivy, fog. Progress indicators (spinners,
 * shimmers, writing dots, "turning" bars) are NOT listed: they report real
 * waiting and must keep moving. A new ambient loop joins by name here.
 * Scoped styles add an 8-hex suffix in builds; it is ignored.
 */
const AMBIENT =
  /^(ev-(ring|float|sheen|drift|flicker|ember-rise)|brand-glow|intro-glow|recent-twinkle|ridge-|rose-swing|ivy-|ctile-sway|desk-write|wm-(fog|flow|idle|bob|walk|turn)|pm-light|lib-art-pan|wmap-(halo|march))/

export function isAmbient(animationName: string): boolean {
  return AMBIENT.test(animationName.replace(/-[0-9a-f]{8}$/, ''))
}
