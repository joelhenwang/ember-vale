<!--
  SettingsNav — the vertical section switcher on the left of the settings
  page. Tab semantics with an aria-orientation so screen readers announce
  it as a tab strip; active styling matches the studio tab language.
-->
<script setup lang="ts">
import { nextTick, onMounted, ref, watch, type Component } from 'vue'

export interface SettingsSection {
  key: string
  label: string
  icon: Component
}

defineProps<{ sections: readonly SettingsSection[] }>()
const model = defineModel<string>({ required: true })

/* One highlight glides between sections rather than each item lighting up. */
const root = ref<HTMLElement | null>(null)
const mark = ref({ y: 0, h: 0 })
const ready = ref(false)
function place(): void {
  const on = root.value?.querySelector<HTMLElement>('.setnav__item--on')
  if (on) mark.value = { y: on.offsetTop, h: on.offsetHeight }
}
watch(model, () => nextTick(place))
onMounted(() => {
  place()
  requestAnimationFrame(() => (ready.value = true))
})
</script>

<template>
  <aside
    ref="root"
    class="setnav ev-card"
    role="tablist"
    aria-orientation="vertical"
    aria-label="Settings sections">
    <span
      class="setnav__mark"
      :class="{ 'setnav__mark--ready': ready }"
      :style="{ transform: `translateY(${mark.y}px)`, height: `${mark.h}px` }"
      aria-hidden="true"></span>
    <button
      v-for="s in sections"
      :id="`settings-tab-${s.key}`"
      :key="s.key"
      type="button"
      role="tab"
      :aria-selected="model === s.key"
      :aria-controls="`settings-panel-${s.key}`"
      class="setnav__item"
      :class="{ 'setnav__item--on': model === s.key }"
      @click="model = s.key">
      <component :is="s.icon" :size="19" class="setnav__ico" />
      <span>{{ s.label }}</span>
    </button>
  </aside>
</template>

<style scoped>
.setnav {
  padding: 12px;
  isolation: isolate;
  display: flex;
  flex-direction: column;
  gap: 6px;
  align-self: start;
  position: sticky;
  top: 76px;
}
.setnav__item {
  display: flex;
  align-items: center;
  gap: 13px;
  height: 46px;
  padding: 0 14px;
  border-radius: 10px;
  font-size: 16.5px;
  font-weight: 500;
  color: var(--ink-2);
  text-align: left;
  position: relative;
  z-index: 1;
  transition:
    background 0.14s ease,
    color 0.2s ease,
    transform 0.14s var(--ease-out);
}
.setnav__item:active {
  transform: scale(0.98);
}
.setnav__mark {
  position: absolute;
  left: 12px;
  right: 12px;
  top: 0;
  border-radius: 10px;
  background: #dbeae2;
  box-shadow: inset 0 0 0 1px #bcd6cb;
  pointer-events: none;
}
.setnav__mark::before {
  content: '';
  position: absolute;
  left: 0;
  top: 10px;
  bottom: 10px;
  width: 3px;
  border-radius: 2px;
  background: linear-gradient(180deg, var(--teal-ink), var(--ember));
}
.setnav__mark--ready {
  transition:
    transform 0.5s var(--ease-settle),
    height 0.5s var(--ease-settle);
}
.setnav__item:hover {
  background: rgba(196, 172, 126, 0.14);
}
.setnav__item--on {
  color: var(--teal);
}
.setnav__item--on:hover {
  background: transparent;
}
.setnav__ico {
  flex: none;
  color: currentColor;
  transition: transform 0.45s var(--ease-spring);
}
.setnav__item:hover .setnav__ico {
  transform: rotate(-8deg);
}
.setnav__item--on .setnav__ico {
  transform: scale(1.12);
}
</style>
