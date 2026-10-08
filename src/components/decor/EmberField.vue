<!--
  EmberField — embers drifting up through a scene, so the world is never
  quite still. Pure CSS, positions derived from the index (no randomness,
  the same field every time). Sits absolutely inside its parent and never
  catches the pointer. Under reduced motion it is not drawn at all, and
  it pauses while scrolled out of sight (or kept alive off-screen by
  KeepAlive), so idle pages cost nothing.
-->
<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

const props = withDefaults(
  defineProps<{ count?: number; rise?: number; tone?: 'ember' | 'dust' | 'snow' }>(),
  { count: 14, rise: 240, tone: 'ember' }
)

/* Pause while out of sight. */
const root = ref<HTMLElement | null>(null)
const seen = ref(true)
let watcher: IntersectionObserver | undefined
onMounted(() => {
  if (!root.value || typeof IntersectionObserver === 'undefined') return
  watcher = new IntersectionObserver(([entry]) => (seen.value = entry?.isIntersecting ?? true))
  watcher.observe(root.value)
})
onBeforeUnmount(() => watcher?.disconnect())

const sparks = computed(() =>
  Array.from({ length: props.count }, (_, i) => {
    const left = ((i * 61) % 97) + 1.5
    const delay = -(((i * 37) % 53) / 53) * 9
    const duration = 6 + ((i * 17) % 7)
    const size = 2 + ((i * 13) % 4)
    const sway = ((i * 29) % 41) - 20
    const opacity = 0.45 + ((i * 7) % 5) / 10
    return {
      left: `${left}%`,
      width: `${size}px`,
      height: `${size}px`,
      animationDelay: `${delay}s`,
      animationDuration: `${duration}s`,
      '--sway': `${sway}px`,
      '--rise': `${props.rise * (0.7 + ((i * 11) % 6) / 10)}px`,
      '--o': `${opacity}`
    }
  })
)
</script>

<template>
  <span
    ref="root"
    class="embers"
    :class="[`embers--${tone}`, { 'embers--paused': !seen }]"
    aria-hidden="true">
    <i v-for="(s, i) in sparks" :key="i" :style="s"></i>
  </span>
</template>

<style scoped>
.embers {
  position: absolute;
  inset: 0;
  overflow: hidden;
  pointer-events: none;
  z-index: 1;
}
.embers i {
  position: absolute;
  bottom: -6px;
  border-radius: 50%;
  opacity: 0;
  background: #ffc98a;
  box-shadow:
    0 0 6px 1px rgba(255, 160, 80, 0.75),
    0 0 14px 2px rgba(220, 110, 40, 0.35);
  animation-name: ev-ember-rise;
  animation-timing-function: cubic-bezier(0.37, 0, 0.63, 1);
  animation-iteration-count: infinite;
  will-change: transform, opacity;
}
.embers--paused i {
  animation-play-state: paused;
}
.embers--dust i {
  background: rgba(255, 246, 220, 0.9);
  box-shadow: 0 0 6px rgba(255, 240, 200, 0.6);
}
.embers--snow i {
  background: #fff;
  box-shadow: 0 0 4px rgba(255, 255, 255, 0.8);
}
:root[data-motion='reduced'] .embers {
  display: none;
}
@media (prefers-reduced-motion: reduce) {
  :root:not([data-motion='full']) .embers {
    display: none;
  }
}
</style>
