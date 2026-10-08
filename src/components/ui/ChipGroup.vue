<script setup lang="ts" generic="T extends string">
import { nextTick, onBeforeUnmount, onMounted, ref, watch, type Component } from 'vue'

/**
 * Segmented filter chips. Generic so views keep their own narrow value
 * types; options may carry a leading icon (Stories' status chips do).
 */
defineProps<{ options: ReadonlyArray<{ value: T; label: string; icon?: Component }> }>()
const model = defineModel<T>({ required: true })

/* One teal marker glides to the chosen chip instead of chips swapping
   colour in place. */
const root = ref<HTMLElement | null>(null)
const mark = ref({ x: 0, w: 0, on: false })
const ready = ref(false)
function place(): void {
  const on = root.value?.querySelector<HTMLElement>('.cg__chip--active')
  mark.value = on ? { x: on.offsetLeft, w: on.offsetWidth, on: true } : { ...mark.value, on: false }
}
watch(model, () => nextTick(place))
let resizer: ResizeObserver | undefined
onMounted(() => {
  place()
  void document.fonts?.ready.then(place)
  requestAnimationFrame(() => (ready.value = true))
  if (typeof ResizeObserver !== 'undefined' && root.value) {
    resizer = new ResizeObserver(place)
    resizer.observe(root.value)
  }
})
onBeforeUnmount(() => resizer?.disconnect())
</script>

<template>
  <div ref="root" class="cg" role="group">
    <span
      class="cg__mark"
      :class="{ 'cg__mark--ready': ready }"
      :style="{
        transform: `translateX(${mark.x}px)`,
        width: `${mark.w}px`,
        opacity: mark.on ? 1 : 0
      }"
      aria-hidden="true"></span>
    <button
      v-for="opt in options"
      :key="opt.value"
      type="button"
      class="cg__chip"
      :class="{ 'cg__chip--active': model === opt.value }"
      @click="model = opt.value">
      <component :is="opt.icon" v-if="opt.icon" :size="14" class="cg__ico" />
      {{ opt.label }}
    </button>
  </div>
</template>

<style scoped>
.cg {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 8px;
}
.cg__chip {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  height: 37px;
  padding: 0 15px;
  border-radius: 9px;
  font-size: 14.5px;
  font-weight: 500;
  color: #55482f;
  background: #fbf5e6;
  border: 1px solid #cdbb93;
  box-shadow: inset 0 1px 0 #fffdf5;
  transition:
    background-color 0.2s ease,
    border-color 0.2s ease,
    color 0.2s ease,
    transform 0.14s var(--ease-out);
  white-space: nowrap;
}
.cg__chip:active {
  transform: scale(0.95);
}
.cg__mark {
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  border-radius: 9px;
  background: linear-gradient(180deg, #21655f, #175256);
  border: 1px solid #0f4147;
  box-shadow:
    inset 0 1px 0 rgba(255, 243, 214, 0.2),
    0 2px 6px -2px rgba(16, 46, 46, 0.4);
  pointer-events: none;
}
.cg__mark--ready {
  transition:
    transform 0.46s var(--ease-settle),
    width 0.46s var(--ease-settle),
    opacity 0.2s ease;
}
.cg__ico {
  transition: transform 0.4s var(--ease-spring);
}
.cg__chip--active .cg__ico {
  transform: scale(1.15);
}
.cg__chip:hover {
  border-color: #b39c6d;
  background: #f7eeda;
}
.cg__chip--active {
  position: relative;
  z-index: 1;
  color: var(--cream-on-teal);
  background: transparent;
  border-color: transparent;
  box-shadow: none;
}
.cg__chip--active:hover {
  background: rgba(255, 245, 215, 0.08);
  border-color: transparent;
}
/* the other chips sit above the marker too, so it slides beneath them */
.cg__chip {
  position: relative;
  z-index: 1;
}
</style>
