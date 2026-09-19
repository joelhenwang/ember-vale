<script setup lang="ts">
import IconCheck from '../icons/IconCheck.vue'

const props = defineProps<{ current: number }>()
const emit = defineEmits<{ go: [step: number] }>()

const steps = [
  { n: 1, label: 'World' },
  { n: 2, label: 'Characters' },
  { n: 3, label: 'Play Mode' },
  { n: 4, label: 'Story' },
  { n: 5, label: 'AI' },
  { n: 6, label: 'Review' }
]

function isDone(n: number): boolean {
  return n < props.current
}
</script>

<template>
  <ol class="stepper" aria-label="Story creation progress">
    <template v-for="(s, i) in steps" :key="s.n">
      <li
        class="stepper__step"
        :class="{
          'stepper__step--done': isDone(s.n),
          'stepper__step--active': s.n === current,
          'stepper__step--todo': !isDone(s.n) && s.n !== current
        }">
        <button
          type="button"
          :aria-current="s.n === current ? 'step' : undefined"
          @click="emit('go', s.n)">
          <span class="stepper__circle">
            <IconCheck v-if="isDone(s.n)" :size="13" />
            <span v-else-if="s.n === current" class="stepper__dot"></span>
          </span>
          <span class="stepper__num">{{ s.n }}</span>
          <span class="stepper__label">{{ s.label }}</span>
        </button>
      </li>
      <li
        v-if="i < steps.length - 1"
        class="stepper__link"
        :class="{ 'stepper__link--done': isDone(s.n) }"
        aria-hidden="true"></li>
    </template>
  </ol>
</template>

<style scoped>
.stepper {
  list-style: none;
  display: flex;
  align-items: flex-start;
}
.stepper__step {
  flex: none;
  width: 76px;
}
.stepper__step button {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0;
  width: 100%;
  border-radius: 10px;
  padding: 2px 0;
  transition: transform 0.12s ease;
}
.stepper__step button:hover {
  transform: translateY(-1px);
}

.stepper__circle {
  width: 29px;
  height: 29px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #fbf5e6;
  border: 1px solid #cdbb93;
  box-shadow:
    inset 0 1px 0 #fffdf5,
    0 1px 2px rgba(96, 74, 40, 0.14);
  transition: inherit;
}
.stepper__dot {
  width: 11px;
  height: 11px;
  border-radius: 50%;
  background: #175256;
}
.stepper__num {
  margin-top: 7px;
  font-size: 16px;
  font-weight: 600;
  color: #55482f;
}
.stepper__label {
  font-size: 14.5px;
  color: #55482f;
}

.stepper__step--done .stepper__circle {
  background: linear-gradient(180deg, #23665f, #14514f);
  border-color: #0f4147;
  color: var(--cream-on-teal);
  box-shadow: 0 1px 2px rgba(16, 46, 46, 0.3);
}
.stepper__step--active .stepper__circle {
  border: 2px solid #1d6a62;
  background: #fbf5e6;
  box-shadow:
    0 0 0 3px rgba(31, 106, 98, 0.12),
    0 1px 2px rgba(96, 74, 40, 0.16);
}
.stepper__step--active .stepper__num,
.stepper__step--active .stepper__label {
  color: var(--teal-ink);
  font-weight: 600;
}

.stepper__link {
  flex: 1 1 34px;
  min-width: 30px;
  height: 2px;
  margin-top: 14px;
  border-radius: 2px;
  background: #dccca6;
}
.stepper__link--done {
  background: #1d6a62;
}
</style>
