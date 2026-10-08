<!--
  StrengthSlider — a LoRA strength from 0 to 2 with its value beside it
  and a mark at the default (1.0). Disabled while its LoRA is off.
-->
<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(
  defineProps<{ label: string; disabled?: boolean; min?: number; max?: number; step?: number }>(),
  { min: 0, max: 2, step: 0.05 }
)
const model = defineModel<number>({ required: true })

const text = computed(() => model.value.toFixed(2))
const percent = computed(() => ((model.value - props.min) / (props.max - props.min)) * 100)

function onInput(event: Event): void {
  model.value = Number((event.target as HTMLInputElement).value)
}
</script>

<template>
  <div class="strength" :class="{ 'strength--off': disabled }">
    <input
      class="strength__range"
      type="range"
      :min="min"
      :max="max"
      :step="step"
      :value="model"
      :disabled="disabled"
      :aria-label="label"
      :style="{ '--fill': `${percent}%` }"
      @input="onInput" />
    <output class="strength__value" :class="{ 'strength__value--default': model === 1 }">
      {{ text }}
    </output>
    <Transition name="ev-pop">
      <button
        v-if="model !== 1 && !disabled"
        type="button"
        class="strength__reset"
        @click="model = 1">
        Reset
      </button>
    </Transition>
  </div>
</template>

<style scoped>
.strength {
  display: flex;
  align-items: center;
  gap: 12px;
  min-height: 44px;
}
.strength--off {
  opacity: 0.5;
}
.strength__range {
  flex: 1;
  min-width: 120px;
  height: 6px;
  appearance: none;
  border-radius: 999px;
  background: linear-gradient(90deg, var(--teal-hi) 0 var(--fill), #e2d6ba var(--fill) 100%);
  cursor: pointer;
}
.strength__range:disabled {
  cursor: default;
}
.strength__range::-webkit-slider-thumb {
  appearance: none;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: #fffaf0;
  border: 2px solid var(--teal);
  box-shadow: 0 1px 3px rgba(46, 39, 24, 0.3);
  transition:
    transform 0.3s var(--ease-spring),
    box-shadow 0.2s ease;
}
.strength__range:not(:disabled):hover::-webkit-slider-thumb {
  transform: scale(1.15);
  box-shadow:
    0 1px 3px rgba(46, 39, 24, 0.3),
    0 0 0 5px rgba(46, 122, 108, 0.14);
}
.strength__range:not(:disabled):active::-webkit-slider-thumb {
  transform: scale(1.28);
}
.strength__range::-moz-range-thumb {
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: #fffaf0;
  border: 2px solid var(--teal);
}
.strength__value {
  min-width: 46px;
  text-align: right;
  font-variant-numeric: tabular-nums;
  font-size: 15px;
  font-weight: 600;
  color: var(--ink);
}
.strength__value--default {
  color: var(--muted);
}
.strength__reset {
  font-size: 13px;
  color: var(--teal-ink);
  text-decoration: underline;
  text-underline-offset: 3px;
}
</style>
