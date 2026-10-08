/**
 * Game-feel effects, shared by every screen:
 *   - burst(el)    sparks fly from an element (a reward, a confirmation)
 *   - shake(el)    the element shakes its head (refused, failed)
 *   - flash(el)    a warm glow that settles (a value just changed)
 *   - v-tilt       a card leans toward the pointer, like a held game card
 *   - v-ripple     a ring spreads from where a button was pressed
 *
 * All of them respect the motion setting (moves()), add only transient
 * DOM, and clean up after themselves. Nothing here changes game state.
 */
import type { Directive } from 'vue'
import { moves } from './useMotion'

const COLORS = ['#f0c79f', '#dc7a3c', '#e9d38a', '#fff3d6', '#c2612a']

/** Sparks fly from the element's centre (or a point inside it). */
export function burst(
  el: Element | null | undefined,
  opts: { count?: number; spread?: number; colors?: string[] } = {}
): void {
  if (!el || !moves() || typeof document === 'undefined') return
  const box = el.getBoundingClientRect()
  const layer = document.createElement('span')
  layer.className = 'ev-burst'
  layer.style.left = `${box.left + box.width / 2}px`
  layer.style.top = `${box.top + box.height / 2}px`
  const count = opts.count ?? 14
  const spread = opts.spread ?? 70
  const colors = opts.colors ?? COLORS
  for (let i = 0; i < count; i += 1) {
    const p = document.createElement('i')
    // evenly spaced angles with a small index-derived wobble: no randomness needed
    const angle = (i / count) * Math.PI * 2 + ((i * 37) % 11) / 20
    const reach = spread * (0.6 + ((i * 53) % 7) / 14)
    p.style.setProperty('--dx', `${Math.cos(angle) * reach}px`)
    p.style.setProperty('--dy', `${Math.sin(angle) * reach - 10}px`)
    p.style.setProperty('--c', colors[i % colors.length] ?? '#f0c79f')
    p.style.setProperty('--s', `${4 + ((i * 29) % 4)}px`)
    p.style.animationDelay = `${(i % 3) * 18}ms`
    layer.appendChild(p)
  }
  document.body.appendChild(layer)
  window.setTimeout(() => layer.remove(), 900)
}

function replay(el: Element | null | undefined, cls: string): void {
  if (!el) return
  el.classList.remove(cls)
  // force a reflow so the animation starts again
  void (el as HTMLElement).offsetWidth
  el.classList.add(cls)
  el.addEventListener('animationend', () => el.classList.remove(cls), { once: true })
}

/** The element shakes (a refusal). Under reduced motion it flashes instead. */
export function shake(el: Element | null | undefined): void {
  replay(el, moves() ? 'ev-nudge' : 'ev-flash')
}

/** A warm glow that settles: something just changed here. */
export function flash(el: Element | null | undefined): void {
  replay(el, 'ev-flash')
}

/* ————— v-tilt ————— */

type Tilted = HTMLElement & { __evTilt?: { move: (e: PointerEvent) => void; leave: () => void } }

/** `v-tilt` (or `v-tilt="6"` for the max angle in degrees). */
export const vTilt: Directive<Tilted, number | undefined> = {
  mounted(el, binding) {
    const max = binding.value ?? 5
    let frame = 0
    const move = (e: PointerEvent): void => {
      if (e.pointerType !== 'mouse' || !moves()) return
      cancelAnimationFrame(frame)
      frame = requestAnimationFrame(() => {
        const r = el.getBoundingClientRect()
        const x = (e.clientX - r.left) / r.width - 0.5
        const y = (e.clientY - r.top) / r.height - 0.5
        el.style.setProperty('--tilt-x', `${(-y * max).toFixed(2)}deg`)
        el.style.setProperty('--tilt-y', `${(x * max).toFixed(2)}deg`)
        el.style.setProperty('--glare-x', `${((x + 0.5) * 100).toFixed(1)}%`)
        el.style.setProperty('--glare-y', `${((y + 0.5) * 100).toFixed(1)}%`)
        el.classList.add('ev-tilting')
      })
    }
    const leave = (): void => {
      cancelAnimationFrame(frame)
      el.classList.remove('ev-tilting')
      el.style.setProperty('--tilt-x', '0deg')
      el.style.setProperty('--tilt-y', '0deg')
    }
    el.classList.add('ev-tilt')
    el.addEventListener('pointermove', move)
    el.addEventListener('pointerleave', leave)
    el.__evTilt = { move, leave }
  },
  unmounted(el) {
    if (!el.__evTilt) return
    el.removeEventListener('pointermove', el.__evTilt.move)
    el.removeEventListener('pointerleave', el.__evTilt.leave)
  }
}

/* ————— v-ripple ————— */

type Rippled = HTMLElement & { __evRipple?: (e: PointerEvent) => void }

export const vRipple: Directive<Rippled, undefined> = {
  mounted(el) {
    const down = (e: PointerEvent): void => {
      if ((el as HTMLButtonElement).disabled) return
      const r = el.getBoundingClientRect()
      const ring = document.createElement('span')
      ring.className = 'ev-ripple'
      const size = Math.max(r.width, r.height) * 2.2
      ring.style.width = ring.style.height = `${size}px`
      ring.style.left = `${e.clientX - r.left - size / 2}px`
      ring.style.top = `${e.clientY - r.top - size / 2}px`
      el.appendChild(ring)
      window.setTimeout(() => ring.remove(), 650)
    }
    el.classList.add('ev-ripple-host')
    el.addEventListener('pointerdown', down)
    el.__evRipple = down
  },
  unmounted(el) {
    if (el.__evRipple) el.removeEventListener('pointerdown', el.__evRipple)
  }
}
