<script setup lang="ts">
import IconChevronDown from '../icons/IconChevronDown.vue'

export interface SortOption {
  value: string
  label: string
}

withDefaults(defineProps<{ label?: string; options: SortOption[] }>(), { label: 'Sort by' })
const model = defineModel<string>({ required: true })
</script>

<template>
  <label class="ss">
    <span v-if="label" class="ss__label">{{ label }}</span>
    <span class="ss__field">
      <select v-model="model">
        <option v-for="opt in options" :key="opt.value" :value="opt.value">
          {{ opt.label }}
        </option>
      </select>
      <IconChevronDown :size="14" class="ss__chev" />
    </span>
  </label>
</template>

<style scoped>
.ss {
  display: inline-flex;
  align-items: center;
  gap: 9px;
  white-space: nowrap;
}
.ss__label {
  font-size: 14.5px;
  color: #6c5f45;
}
.ss__field {
  position: relative;
  display: inline-flex;
  align-items: center;
}
.ss select {
  appearance: none;
  -webkit-appearance: none;
  height: 37px;
  padding: 0 32px 0 13px;
  border-radius: 9px;
  border: 1px solid #cdbb93;
  background: #fbf5e6;
  font-family: var(--font-body);
  font-size: 14.5px;
  font-weight: 500;
  color: var(--ink);
  box-shadow: inset 0 1px 0 #fffdf5;
  cursor: pointer;
  transition: border-color 0.14s ease;
}
.ss select:hover {
  border-color: #b39c6d;
}
.ss__chev {
  position: absolute;
  right: 10px;
  color: #6c5f45;
  pointer-events: none;
}
</style>
