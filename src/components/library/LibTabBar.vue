<script setup lang="ts">
import IconGlobe from '../icons/IconGlobe.vue'
import IconUsers from '../icons/IconUsers.vue'
import IconStack from '../icons/IconStack.vue'
import IconDoc from '../icons/IconDoc.vue'

export interface LibTab {
  key: string
  label: string
  count: number
}

withDefaults(defineProps<{ tabs: LibTab[]; modelValue: string }>(), { modelValue: 'characters' })
const emit = defineEmits<{ update: [key: string] }>()

const icons: Record<string, unknown> = {
  worlds: IconGlobe,
  characters: IconUsers,
  'style-packs': IconStack,
  templates: IconDoc
}
</script>

<template>
  <nav class="tabs ev-card" aria-label="Library sections">
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
  </nav>
</template>

<style scoped>
.tabs {
  display: flex;
  align-items: stretch;
  padding: 0;
  overflow: hidden;
  position: relative;
}
/* folded-corner detail at the right edge, like the reference */
.tabs::before {
  content: '';
  position: absolute;
  right: 0;
  bottom: 0;
  border-style: solid;
  border-width: 0 0 15px 15px;
  border-color: transparent transparent rgba(158, 128, 74, 0.22) transparent;
  pointer-events: none;
}
.tabs__tab {
  display: inline-flex;
  align-items: center;
  gap: 11px;
  padding: 13px 22px 12px;
  position: relative;
  font-size: 17.5px;
  font-weight: 500;
  color: #453b27;
  transition:
    color 0.14s ease,
    background-color 0.14s ease;
}
.tabs__tab + .tabs__tab {
  border-left: 1px solid #e9ddc0;
}
.tabs__tab:hover {
  background: rgba(210, 186, 136, 0.1);
}
.tabs__icon {
  color: #a5823f;
  transition: color 0.14s ease;
}
.tabs__label {
  font-family: var(--font-display);
  font-size: 20px;
  font-weight: 600;
  line-height: 1;
  letter-spacing: 0.01em;
}
.tabs__count {
  font-size: 12.5px;
  font-weight: 600;
  line-height: 1;
  color: #7a6a49;
  background: #ece1c6;
  border-radius: 999px;
  padding: 4px 8px 3px;
}
.tabs__tab--active {
  color: var(--teal-ink);
}
.tabs__tab--active .tabs__icon {
  color: var(--teal-ink);
}
.tabs__tab--active .tabs__label {
  color: var(--teal-ink);
}
.tabs__tab--active::after {
  content: '';
  position: absolute;
  left: 12px;
  right: 12px;
  bottom: 0;
  height: 3px;
  border-radius: 3px 3px 0 0;
  background: var(--teal-ink);
}
</style>
