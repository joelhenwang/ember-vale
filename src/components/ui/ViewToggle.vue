<!--
  ViewToggle — grid/list density switch used by the Library and the Stories
  shelf. Generic on the value type so each page keeps its own narrow model
  ('grid' | 'list' or anything else).
-->
<script setup lang="ts" generic="T extends string">
import type { Component } from 'vue'

defineProps<{
  label: string
  options: ReadonlyArray<{ value: T; label: string; icon: Component }>
}>()
const model = defineModel<T>({ required: true })
</script>

<template>
  <div class="vt" role="group" :aria-label="label">
    <button
      v-for="opt in options"
      :key="opt.value"
      type="button"
      :class="{ 'vt--on': model === opt.value }"
      :aria-label="opt.label"
      :aria-pressed="model === opt.value"
      @click="model = opt.value">
      <component :is="opt.icon" :size="15" />
    </button>
  </div>
</template>

<style scoped>
.vt {
  display: flex;
  gap: 6px;
}
.vt button {
  width: 34px;
  height: 34px;
  border-radius: 9px;
  border: 1px solid #cdbb93;
  background: #fbf5e6;
  color: #6c5f45;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  transition:
    background 0.14s ease,
    color 0.14s ease,
    border-color 0.14s ease;
}
.vt button:hover {
  border-color: #b39c6d;
}
.vt--on {
  background: linear-gradient(180deg, #21655f, #175256);
  border-color: #0f4147;
  color: var(--cream-on-teal);
}
</style>
