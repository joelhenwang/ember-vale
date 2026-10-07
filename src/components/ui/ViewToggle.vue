<!--
  ViewToggle — grid/list density switch used by the Library and the Stories
  shelf: a segmented control whose filled marker slides to the chosen view,
  each side named as well as drawn. Generic on the value type so each page
  keeps its own narrow model ('grid' | 'list' or anything else).
-->
<script setup lang="ts" generic="T extends string">
import { computed, type Component } from 'vue'

const props = defineProps<{
  label: string
  options: ReadonlyArray<{ value: T; label: string; icon: Component; short?: string }>
}>()
const model = defineModel<T>({ required: true })
const at = computed(() =>
  Math.max(
    0,
    props.options.findIndex((o) => o.value === model.value)
  )
)
</script>

<template>
  <div
    class="vt"
    role="radiogroup"
    :aria-label="label"
    :style="{ '--n': options.length, '--at': at }">
    <span class="vt__thumb" aria-hidden="true"></span>
    <button
      v-for="opt in options"
      :key="opt.value"
      type="button"
      role="radio"
      class="vt__opt"
      :class="{ 'vt__opt--on': model === opt.value }"
      :aria-label="opt.label"
      :aria-checked="model === opt.value"
      :title="opt.label"
      @click="model = opt.value">
      <component :is="opt.icon" :size="15" />
      <span class="vt__text">{{ opt.short ?? opt.label }}</span>
    </button>
  </div>
</template>

<style scoped>
.vt {
  position: relative;
  display: grid;
  grid-template-columns: repeat(var(--n), minmax(0, 1fr));
  padding: 3px;
  border-radius: 11px;
  border: 1px solid #cdbb93;
  background: #f1e7cf;
  box-shadow: inset 0 1px 2px rgba(96, 74, 40, 0.14);
}
.vt__thumb {
  position: absolute;
  top: 3px;
  bottom: 3px;
  left: 3px;
  width: calc((100% - 6px) / var(--n));
  transform: translateX(calc(100% * var(--at)));
  border-radius: 8px;
  background: linear-gradient(180deg, #21655f, #175256);
  box-shadow:
    inset 0 1px 0 rgba(255, 243, 214, 0.22),
    0 2px 6px -2px rgba(16, 46, 46, 0.45);
  transition: transform 0.28s var(--ease-spring);
}
.vt__opt {
  position: relative;
  z-index: 1;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  height: 30px;
  padding: 0 12px;
  border-radius: 8px;
  font-size: 14.5px;
  font-weight: 500;
  color: #6c5f45;
  transition: color 0.2s ease;
}
.vt__opt:hover:not(.vt__opt--on) {
  color: var(--teal-ink);
}
.vt__opt--on {
  color: var(--cream-on-teal);
}
@media (max-width: 560px) {
  .vt__text {
    display: none;
  }
}
</style>
