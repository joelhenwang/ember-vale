import { onBeforeUnmount, ref, watch, type Directive, type Ref } from 'vue'
import {
  REST_AFTER_MS,
  applyMotion,
  isAmbient,
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
  installRest()
  installRecomposite()
}

/**
 * A loop that starts while its page or list is still fading in (opacity 0)
 * is judged by Chromium to have "no visible change" and runs on the main
 * thread for good: style recalculated every frame, 13-19 % of the main
 * thread on Adventure and Watch (perf-frontend-001). When an entrance
 * animation or transition ends, the running infinite loops inside it are
 * paused and played again in place (no visible jump), which lets the
 * browser hand them to the compositor.
 */
function installRecomposite(): void {
  if (typeof Element === 'undefined' || typeof Element.prototype.getAnimations !== 'function')
    return
  const ended = new Set<Element>()
  let timer = 0
  const flush = (): void => {
    timer = 0
    for (const el of ended) {
      if (!el.isConnected) continue
      for (const a of el.getAnimations({ subtree: true })) {
        if (a.playState === 'running' && a.effect?.getTiming().iterations === Infinity) {
          a.pause()
          a.play()
        }
      }
    }
    ended.clear()
  }
  const note = (event: Event): void => {
    if (!(event.target instanceof Element)) return
    ended.add(event.target)
    if (!timer) timer = window.setTimeout(flush, 120)
  }
  document.addEventListener('animationend', note, true)
  document.addEventListener('transitionend', note, true)
}

/**
 * Ambient loops rest after REST_AFTER_MS without input and wake on the
 * next one. Any running infinite animation keeps the compositor drawing
 * every frame: measured at 30-100 % of a CPU core while a page sat idle
 * (perf-frontend-001), which drains a laptop left on the game. Progress
 * indicators never rest (see isAmbient).
 */
function installRest(): void {
  if (typeof document.getAnimations !== 'function') return
  let last = performance.now()
  let resting: Animation[] = []
  const wake = (): void => {
    last = performance.now()
    if (!resting.length) return
    for (const a of resting) if (a.playState === 'paused') a.play()
    resting = []
  }
  for (const type of ['pointermove', 'pointerdown', 'keydown', 'wheel', 'touchstart', 'scroll'])
    window.addEventListener(type, wake, { passive: true, capture: true })
  const connected = (a: Animation): boolean => {
    const target = (a.effect as KeyframeEffect | null)?.target
    return !!target && target.isConnected
  }
  window.setInterval(() => {
    // pages left while resting take their animations with them: never hold
    // on to those (and through them, detached elements)
    resting = resting.filter(connected)
    if (performance.now() - last < REST_AFTER_MS) return
    for (const a of document.getAnimations()) {
      if (
        a.playState === 'running' &&
        'animationName' in a &&
        connected(a) &&
        a.effect?.getTiming().iterations === Infinity &&
        isAmbient(String(a.animationName))
      ) {
        a.pause()
        resting.push(a)
      }
    }
  }, 5000)
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
