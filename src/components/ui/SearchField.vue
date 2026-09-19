<script setup lang="ts">
import IconSearch from '../icons/IconSearch.vue'

defineProps<{ placeholder?: string }>()
const model = defineModel<string>({ default: '' })
</script>

<template>
  <label class="sf">
    <IconSearch :size="15" class="sf__icon" />
    <input v-model="model" type="text" :placeholder="placeholder ?? 'Search…'" />
  </label>
</template>

<style scoped>
.sf {
  display: flex;
  align-items: center;
  gap: 10px;
  height: 40px;
  padding: 0 13px;
  background: #fdf9ee;
  border: 1px solid #d5c6a2;
  border-radius: 9px;
  box-shadow: inset 0 1px 2px rgba(120, 96, 56, 0.08);
  transition:
    border-color 0.15s ease,
    box-shadow 0.15s ease;
  min-width: 0;
}
.sf:focus-within {
  border-color: #7fa79b;
  box-shadow:
    inset 0 1px 2px rgba(120, 96, 56, 0.08),
    0 0 0 3px rgba(46, 122, 108, 0.14);
}
.sf__icon {
  color: #9a8a6b;
  flex: none;
}
.sf input {
  flex: 1;
  min-width: 0;
  border: 0;
  background: transparent;
  font-family: var(--font-body);
  font-size: 15.5px;
  color: var(--ink);
  outline: none;
}
.sf input::placeholder {
  color: #a29172;
  opacity: 0.75;
}
</style>
