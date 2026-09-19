<script setup lang="ts">
import IconChevronDown from '../icons/IconChevronDown.vue'

/**
 * Styled native select for every settings/studio form.
 * `placeholder` renders an empty option (shown while the model is ''),
 * `disabled` locks the control (e.g. Model until a Provider is chosen).
 */
defineProps<{
  options: readonly string[]
  placeholder?: string
  disabled?: boolean
}>()
const model = defineModel<string>({ required: true })
</script>

<template>
  <span class="ev-sel" :class="{ 'ev-sel--off': disabled }">
    <select v-model="model" class="ev-input" :disabled="disabled">
      <option v-if="placeholder !== undefined" value="">{{ placeholder }}</option>
      <option v-for="opt in options" :key="opt" :value="opt">{{ opt }}</option>
    </select>
    <IconChevronDown :size="14" class="ev-sel__chev" />
  </span>
</template>

<style scoped>
.ev-sel {
  position: relative;
  display: block;
}
.ev-sel select {
  appearance: none;
  -webkit-appearance: none;
  padding-right: 34px;
  cursor: pointer;
}
.ev-sel__chev {
  position: absolute;
  right: 12px;
  top: 50%;
  transform: translateY(-50%);
  color: #55482f;
  pointer-events: none;
}
.ev-sel--off {
  opacity: 0.55;
}
.ev-sel--off select {
  cursor: default;
  color: var(--muted);
}
</style>
