import { onBeforeUnmount, ref, watch, type Directive, type Ref } from 'vue'
import {
  applyMotion,
  motionAllowed,
  readMotion,
  writeMotion,
  type MotionChoice
} from '../game/motion'

/* One shared choice for the whole app. */
function localStore(): Storage | undefined {
  try {
    return typeof window !== 'undefined' ? window.localStorage : undefined
  } catch {
    return undefined // blocked site data: the getter itself throws
  }
}
const store = localStore()
const choice = ref<MotionChoice>(readMotion(store))
const query =
  typeof window !== 'undefined' && window.matchMedia
    ? window.matchMedia('(prefers-reduced-motion: reduce)')
    : undefined
const systemReduces = ref(query?.matches ?? false)
query?.addEventListener?.('change', (e) => (systemReduces.value = e.matches))

/** Call once at start-up: puts the saved choice on <html>, and fades in
 *  pictures as they arrive. */
export function installMotion(): void {
  applyMotion(document.documentElement, choice.value)
  // A picture that finishes loading after the page is drawn fades in
  // instead of popping. Nothing starts hidden, so a picture can never be
  // stuck invisible; pictures with their own fade (.ev-img-fade) or that
  // opt out (data-no-fade) are left alone. Fades are fine under reduced
  // motion: nothing moves.
  document.addEventListener(
    'load',
    (event) => {
      const img = event.target
      if (!(img instanceof HTMLImageElement) || typeof img.animate !== 'function') return
      if (img.classList.contains('ev-img-fade') || 'noFade' in img.dataset) return
      // one keyframe: it fades up to whatever opacity the picture rests at
      img.animate([{ opacity: 0, offset: 0 }], {
        duration: 450,
        easing: 'cubic-bezier(0.22, 0.8, 0.24, 1)'
      })
    },
    true
  )
}

export function useMotion() {
  function set(next: MotionChoice): void {
    choice.value = next
    writeMotion(store, next)
    applyMotion(document.documentElement, next)
  }
  return { choice, systemReduces, set }
}

/** Whether things may move right now (script-driven motion asks this). */
export function moves(): boolean {
  return motionAllowed(choice.value, systemReduces.value)
}

/* ————— numbers that count toward their new value ————— */

const easeOut = (t: number): number => 1 - Math.pow(1 - t, 4)

/**
 * A number that glides to each new value (stamina, counts, levels).
 * Under reduced motion it jumps straight there.
 */
export function useTweened(source: Ref<number>, duration = 600): Ref<number> {
  const shown = ref(source.value)
  let frame = 0
  watch(source, (to) => {
    cancelAnimationFrame(frame)
    const from = shown.value
    if (!moves() || from === to || typeof requestAnimationFrame === 'undefined') {
      shown.value = to
      return
    }
    const start = performance.now()
    const step = (now: number): void => {
      const t = Math.min(1, (now - start) / duration)
      shown.value = from + (to - from) * easeOut(t)
      if (t < 1) frame = requestAnimationFrame(step)
    }
    frame = requestAnimationFrame(step)
  })
  onBeforeUnmount(() => cancelAnimationFrame(frame))
  return shown
}

/* ————— v-reveal: rise into view when scrolled to ————— */

let watcher: IntersectionObserver | undefined
function revealWatcher(): IntersectionObserver | undefined {
  if (watcher || typeof IntersectionObserver === 'undefined') return watcher
  watcher = new IntersectionObserver(
    (entries) => {
      for (const e of entries) {
        if (!e.isIntersecting) continue
        e.target.classList.add('ev-revealed')
        watcher?.unobserve(e.target)
      }
    },
    { rootMargin: '0px 0px -8% 0px', threshold: 0.05 }
  )
  return watcher
}

/**
 * `v-reveal` (optionally `v-reveal="index"` for a short stagger): the
 * element rises and fades in the first time it scrolls into view.
 */
export const vReveal: Directive<HTMLElement, number | undefined> = {
  mounted(el, binding) {
    const w = revealWatcher()
    if (!w) return
    el.classList.add('ev-reveal')
    if (typeof binding.value === 'number') {
      el.style.setProperty('--ev-reveal-delay', `${Math.min(binding.value, 8) * 45}ms`)
    }
    w.observe(el)
  },
  unmounted(el) {
    watcher?.unobserve(el)
  }
}
