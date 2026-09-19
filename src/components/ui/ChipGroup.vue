<script setup lang="ts" generic="T extends string">
import type { Component } from 'vue'

/**
 * Segmented filter chips. Generic so views keep their own narrow value
 * types; options may carry a leading icon (Stories' status chips do).
 */
defineProps<{ options: ReadonlyArray<{ value: T; label: string; icon?: Component }> }>()
const model = defineModel<T>({ required: true })
</script>

<template>
  <div class="cg" role="group">
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
    background-color 0.14s ease,
    border-color 0.14s ease,
    color 0.14s ease;
  white-space: nowrap;
}
.cg__chip:hover {
  border-color: #b39c6d;
  background: #f7eeda;
}
.cg__chip--active {
  color: var(--cream-on-teal);
  background: linear-gradient(180deg, #21655f, #175256);
  border-color: #0f4147;
  box-shadow:
    inset 0 1px 0 rgba(255, 243, 214, 0.2),
    0 1px 2px rgba(16, 46, 46, 0.25);
}
.cg__chip--active:hover {
  background: linear-gradient(180deg, #256e67, #1a575b);
  border-color: #0f4147;
}
</style>
