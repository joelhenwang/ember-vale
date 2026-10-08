<script setup lang="ts">
import IconCheck from '../icons/IconCheck.vue'

defineProps<{ steps: string[]; current: number; stretch?: boolean }>()
const emit = defineEmits<{ go: [index: number] }>()
</script>

<template>
  <ol class="istep" :class="{ 'istep--stretch': stretch }" aria-label="Creation progress">
    <template v-for="(label, i) in steps" :key="label">
      <li
        class="istep__step"
        :class="
          i + 1 < current
            ? 'istep__step--done'
            : i + 1 === current
              ? 'istep__step--active'
              : 'istep__step--todo'
        ">
        <button
          type="button"
          :aria-current="i + 1 === current ? 'step' : undefined"
          @click="emit('go', i + 1)">
          <span class="istep__circle">
            <IconCheck v-if="i + 1 < current" :size="12" />
            <template v-else>{{ i + 1 }}</template>
          </span>
          <span class="istep__label">{{ label }}</span>
        </button>
      </li>
      <li
        v-if="i < steps.length - 1"
        class="istep__link"
        :class="{ 'istep__link--done': i + 1 < current }"
        aria-hidden="true"></li>
    </template>
  </ol>
</template>

<style scoped>
.istep {
  list-style: none;
  display: flex;
  align-items: center;
  gap: 0;
}
.istep__step button {
  display: inline-flex;
  align-items: center;
  gap: 11px;
  padding: 4px 4px;
  border-radius: 10px;
  transition: transform 0.22s var(--ease-settle);
}
.istep__step button:hover {
  transform: translateY(-2px);
}
.istep__step button:active {
  transform: scale(0.96);
}
.istep__circle {
  width: 29px;
  height: 29px;
  flex: none;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 15.5px;
  font-weight: 600;
  background: #fbf5e6;
  border: 1px solid #cdbb93;
  color: #55482f;
  box-shadow:
    inset 0 1px 0 #fffdf5,
    0 1px 2px rgba(96, 74, 40, 0.12);
  transition:
    background-color 0.3s ease,
    border-color 0.3s ease,
    color 0.3s ease,
    transform 0.4s var(--ease-settle);
}
/* the check stamps in when a step is finished */
.istep__circle svg {
  animation: istep-check 0.42s var(--ease-spring) both;
}
@keyframes istep-check {
  from {
    opacity: 0;
    transform: scale(0.3) rotate(-20deg);
  }
}
.istep__label {
  font-size: 15.5px;
  font-weight: 500;
  color: #55482f;
  white-space: nowrap;
}
.istep__step--done .istep__circle {
  background: #fbf5e6;
  border-color: #9db39b;
  color: var(--teal-ink);
}
.istep__step--active .istep__circle {
  position: relative;
  background: linear-gradient(180deg, #21655f, #14514f);
  border-color: #0f4147;
  color: var(--cream-on-teal);
  box-shadow: 0 1px 2px rgba(16, 46, 46, 0.3);
  transform: scale(1.08);
  animation: istep-arrive 0.5s var(--ease-settle);
}
/* the current step glows softly while you are on it */
.istep__step--active .istep__circle::after {
  content: '';
  position: absolute;
  inset: -1px;
  border-radius: 50%;
  --ev-breathe-color: rgba(31, 106, 94, 0.32);
  animation: ev-breathe 2.6s var(--ease-sine) infinite;
}
@keyframes istep-arrive {
  from {
    transform: scale(0.8);
  }
}
.istep__step--active .istep__label {
  color: var(--teal-ink);
  font-weight: 600;
}
.istep__step--todo .istep__label,
.istep__step--todo .istep__circle {
  color: #8d7c5f;
}
/* across the page: the links share the room left over */
.istep--stretch .istep__link {
  flex: 1 1 22px;
  width: auto;
}
.istep__link {
  position: relative;
  overflow: hidden;
  width: 42px;
  height: 2px;
  margin: 0 10px;
  border-radius: 2px;
  background: #d5c3a0;
  flex: none;
}
/* the road between steps fills in as you pass along it */
.istep__link::after {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: inherit;
  background: linear-gradient(90deg, var(--teal-ink), #5f9488);
  transform: scaleX(0);
  transform-origin: left center;
  transition: transform 0.55s var(--ease-settle);
}
.istep__link--done::after {
  transform: scaleX(1);
}
/* Narrow screens: every step stays on screen; only the current one is named. */
@media (max-width: 760px) {
  .istep {
    justify-content: space-between;
  }
  .istep__step:not(.istep__step--active) .istep__label {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip: rect(0 0 0 0);
  }
  .istep__link {
    flex: 1 1 8px;
    width: auto;
    min-width: 8px;
    margin: 0 4px;
  }
  .istep__step button {
    gap: 7px;
  }
}
/* A narrower column keeps every name with shorter links between them… */
@container (max-width: 900px) {
  .istep__link {
    width: 22px;
    margin: 0 7px;
  }
}
/* …and one too narrow for every name names only the current step. */
@container (max-width: 740px) {
  .istep__step:not(.istep__step--active) .istep__label {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip: rect(0 0 0 0);
  }
  .istep__link {
    width: 28px;
  }
}
</style>
