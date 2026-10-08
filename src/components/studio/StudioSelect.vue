<script setup lang="ts">
import { computed } from 'vue'
import IconChevronDown from '../icons/IconChevronDown.vue'

/**
 * Styled native select for every settings/studio form.
 * `placeholder` renders an empty option (shown while the model is ''),
 * `disabled` locks the control (e.g. Model until a Provider is chosen).
 * Options are plain strings (value = label) or `{ value, label }` pairs.
 */
interface SelectOption {
  value: string
  label: string
}

const props = defineProps<{
  options: readonly (string | SelectOption)[]
  placeholder?: string
  disabled?: boolean
  /** Accessible name when no visible <label> is associated. */
  ariaLabel?: string
}>()
const model = defineModel<string>({ required: true })

const normalized = computed(() =>
  props.options.map((opt) => (typeof opt === 'string' ? { value: opt, label: opt } : opt))
)
</script>

<template>
  <span class="ev-sel" :class="{ 'ev-sel--off': disabled }">
    <select v-model="model" class="ev-input" :disabled="disabled" :aria-label="ariaLabel">
      <option v-if="placeholder !== undefined" value="">{{ placeholder }}</option>
      <option v-for="opt in normalized" :key="opt.value" :value="opt.value">
        {{ opt.label }}
      </option>
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
/* the chevron turns toward the list while the select is in use */
.ev-sel__chev {
  transition:
    transform 0.3s var(--ease-settle),
    color 0.15s ease;
}
.ev-sel:hover .ev-sel__chev {
  color: var(--teal-ink);
  transform: translateY(-40%);
}
.ev-sel:focus-within .ev-sel__chev {
  color: var(--teal-ink);
  transform: translateY(-50%) rotate(180deg);
}
</style>
