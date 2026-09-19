<!--
  SettingsNav — the vertical section switcher on the left of the settings
  page. Tab semantics with an aria-orientation so screen readers announce
  it as a tab strip; active styling matches the studio tab language.
-->
<script setup lang="ts">
import type { Component } from 'vue'

export interface SettingsSection {
  key: string
  label: string
  icon: Component
}

defineProps<{ sections: readonly SettingsSection[] }>()
const model = defineModel<string>({ required: true })
</script>

<template>
  <aside
    class="setnav ev-card"
    role="tablist"
    aria-orientation="vertical"
    aria-label="Settings sections">
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
  transition:
    background 0.14s ease,
    color 0.14s ease;
}
.setnav__item:hover {
  background: rgba(196, 172, 126, 0.14);
}
.setnav__item--on {
  background: #dbeae2;
  color: var(--teal);
  box-shadow: inset 0 0 0 1px #bcd6cb;
}
.setnav__item--on:hover {
  background: #d3e5db;
}
.setnav__ico {
  flex: none;
  color: currentColor;
}
</style>
