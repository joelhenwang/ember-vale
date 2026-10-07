<!--
  LibTabBar — the Library's section tabs, sitting on top of the shelf they
  open. The chosen tab is raised and lit, and a bar slides under the whole
  width of it when the choice changes.
-->
<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import IconGlobe from '../icons/IconGlobe.vue'
import IconUsers from '../icons/IconUsers.vue'
import IconStack from '../icons/IconStack.vue'
import IconDoc from '../icons/IconDoc.vue'

export interface LibTab {
  key: string
  label: string
  count: number
}

const props = withDefaults(defineProps<{ tabs: LibTab[]; modelValue: string }>(), {
  modelValue: 'characters'
})
const emit = defineEmits<{ update: [key: string] }>()

const icons: Record<string, unknown> = {
  worlds: IconGlobe,
  characters: IconUsers,
  'style-packs': IconStack,
  templates: IconDoc
}

/* The sliding bar follows the chosen tab's box. */
const bar = ref<HTMLElement | null>(null)
const marker = ref({ left: 0, width: 0, ready: false })
function measure(): void {
  const el = bar.value?.querySelector<HTMLElement>('.tabs__tab--active')
  if (!el) return
  marker.value = { left: el.offsetLeft, width: el.offsetWidth, ready: true }
}
watch(
  () => [props.modelValue, props.tabs.map((t) => t.count).join()],
  () => nextTick(measure)
)
onMounted(() => {
  void nextTick(measure)
  // web fonts change the tabs' widths once they arrive
  void document.fonts?.ready.then(measure)
  window.addEventListener('resize', measure)
})
onBeforeUnmount(() => window.removeEventListener('resize', measure))
</script>

<template>
  <nav ref="bar" class="tabs" aria-label="Library sections">
    <button
      v-for="tab in tabs"
      :key="tab.key"
      type="button"
      class="tabs__tab"
      :class="{ 'tabs__tab--active': tab.key === modelValue }"
      :aria-current="tab.key === modelValue ? 'page' : undefined"
      @click="emit('update', tab.key)">
      <component :is="icons[tab.key]" :size="20" class="tabs__icon" />
      <span class="tabs__label">{{ tab.label }}</span>
      <span class="tabs__count">{{ tab.count }}</span>
    </button>
    <span
      class="tabs__marker"
      :class="{ 'tabs__marker--ready': marker.ready }"
      :style="{ transform: `translateX(${marker.left}px)`, width: `${marker.width}px` }"
      aria-hidden="true"></span>
  </nav>
</template>

<style scoped>
.tabs {
  position: relative;
  display: flex;
  align-items: stretch;
  border-bottom: 1px solid var(--line);
  background: linear-gradient(180deg, #efe4c8, #f3ead3);
  border-radius: var(--radius-card) var(--radius-card) 0 0;
  overflow-x: auto;
  scrollbar-width: none;
}
.tabs::-webkit-scrollbar {
  display: none;
}
.tabs__tab {
  flex: 1 1 auto;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 14px 22px 13px;
  position: relative;
  white-space: nowrap;
  color: #5b4e35;
  transition:
    color 0.2s ease,
    background-color 0.2s ease;
}
.tabs__tab:first-child {
  border-top-left-radius: var(--radius-card);
}
.tabs__tab:last-of-type {
  border-top-right-radius: var(--radius-card);
}
.tabs__tab + .tabs__tab {
  border-left: 1px solid #e3d5b5;
}
.tabs__tab:hover:not(.tabs__tab--active) {
  background: rgba(255, 250, 238, 0.55);
  color: var(--teal-ink);
}
.tabs__icon {
  color: #a5823f;
  transition:
    color 0.2s ease,
    transform 0.3s var(--ease-spring);
}
.tabs__tab:hover .tabs__icon {
  transform: scale(1.1);
}
.tabs__label {
  font-family: var(--font-ui);
  font-size: 18px;
  font-weight: 500;
  line-height: 1;
}
.tabs__count {
  font-family: var(--font-ui);
  font-size: 13px;
  font-weight: 700;
  line-height: 1;
  color: #7a6a49;
  background: #e6d9b9;
  border-radius: 999px;
  padding: 4px 8px 3px;
  transition:
    background-color 0.2s ease,
    color 0.2s ease;
}

/* the chosen tab is the shelf's own paper, joined to it */
.tabs__tab--active {
  color: var(--teal);
  background: linear-gradient(180deg, var(--surface-2), var(--surface-2));
  box-shadow: 0 1px 0 var(--surface-2);
}
.tabs__tab--active .tabs__icon {
  color: var(--ember);
}
.tabs__tab--active .tabs__label {
  font-weight: 700;
}
.tabs__tab--active .tabs__count {
  background: var(--teal);
  color: var(--cream-on-teal);
}

.tabs__marker {
  position: absolute;
  left: 0;
  top: 0;
  height: 3px;
  border-radius: 0 0 3px 3px;
  background: linear-gradient(90deg, var(--teal-hi), var(--teal) 55%, var(--ember));
  box-shadow: 0 2px 8px -1px var(--ember-glow);
  opacity: 0;
  pointer-events: none;
}
.tabs__marker--ready {
  opacity: 1;
  transition:
    transform 0.4s var(--ease-spring),
    width 0.4s var(--ease-spring);
}
</style>
