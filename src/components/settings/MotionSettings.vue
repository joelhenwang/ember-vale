<!--
  MotionSettings — how much the game moves: follow the computer, full
  motion, or reduced. Saved on this device only (src/game/motion.ts) and
  applied at once; the preview shows what each choice looks like.
-->
<script setup lang="ts">
import { computed, ref } from 'vue'
import { MOTION_CHOICES, motionAllowed } from '../../game/motion'
import { useMotion } from '../../composables/useMotion'

const { choice, systemReduces, set } = useMotion()
const moving = computed(() => motionAllowed(choice.value, systemReduces.value))

/* The preview card replays its entrance each time the choice changes. */
const replay = ref(0)
function pick(key: (typeof MOTION_CHOICES)[number]['key']): void {
  set(key)
  replay.value += 1
}
</script>

<template>
  <div class="motion ev-card">
    <div class="motion__choices" role="radiogroup" aria-label="Motion">
      <button
        v-for="c in MOTION_CHOICES"
        :key="c.key"
        type="button"
        role="radio"
        class="motion__choice ev-press"
        :class="{ 'motion__choice--on': choice === c.key }"
        :aria-checked="choice === c.key"
        @click="pick(c.key)">
        <span class="motion__dot" aria-hidden="true"></span>
        <span class="motion__words">
          <b>{{ c.label }}</b>
          <span>{{ c.hint }}</span>
          <em v-if="c.key === 'system'">
            Your computer currently asks for {{ systemReduces ? 'reduced' : 'full' }} motion.
          </em>
        </span>
      </button>
    </div>

    <div class="motion__preview" aria-hidden="true">
      <span class="motion__label">Preview</span>
      <Transition name="ev-swap" mode="out-in">
        <div :key="replay" class="motion__stage">
          <div class="motion__art">
            <div class="motion__sky ev-drift"></div>
          </div>
          <div class="motion__rows ev-rise">
            <span></span>
            <span></span>
            <span></span>
          </div>
        </div>
      </Transition>
      <p class="motion__now">
        {{
          moving ? 'Things move: pages slide, pictures drift.' : 'Things fade instead of moving.'
        }}
      </p>
    </div>
  </div>
</template>

<style scoped>
.motion {
  margin-top: 16px;
  padding: 20px 22px;
  display: grid;
  grid-template-columns: minmax(0, 1fr) 240px;
  gap: 22px;
}
.motion__choices {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.motion__choice {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 13px 15px;
  text-align: left;
  border: 1px solid var(--line);
  border-radius: 11px;
  background: linear-gradient(180deg, #fdf8ea, #f9f1de);
  transition:
    transform var(--dur-quick) var(--ease-out),
    border-color var(--dur) ease,
    background-color var(--dur) ease,
    box-shadow var(--dur) ease;
}
.motion__choice:hover {
  border-color: var(--line-strong);
}
.motion__choice--on {
  border-color: var(--teal-ink);
  box-shadow: 0 0 0 3px rgba(46, 122, 108, 0.12);
}
.motion__dot {
  flex: none;
  position: relative;
  width: 18px;
  height: 18px;
  margin-top: 2px;
  border-radius: 50%;
  border: 1.5px solid var(--line-strong);
  background: #fffaf0;
  transition: border-color var(--dur) ease;
}
.motion__dot::after {
  content: '';
  position: absolute;
  inset: 3px;
  border-radius: 50%;
  background: var(--teal-ink);
  transform: scale(0);
  transition: transform 0.32s var(--ease-spring);
}
.motion__choice--on .motion__dot {
  border-color: var(--teal-ink);
}
.motion__choice--on .motion__dot::after {
  transform: scale(1);
}
.motion__words {
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: 14.5px;
  color: var(--ink-3);
}
.motion__words b {
  font-family: var(--font-ui);
  font-size: 16px;
  color: var(--ink);
}
.motion__words em {
  font-size: 13.5px;
  color: var(--muted);
}
.motion__preview {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.motion__label {
  font-family: var(--font-ui);
  font-size: 12.5px;
  font-weight: 700;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--gold);
}
.motion__stage {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 10px;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: var(--surface-2);
}
.motion__art {
  height: 96px;
  border-radius: 8px;
  overflow: hidden;
}
.motion__sky {
  width: 100%;
  height: 100%;
  background:
    radial-gradient(40% 50% at 70% 35%, rgba(255, 230, 180, 0.9), transparent 70%),
    linear-gradient(170deg, #9cc3c0 0%, #d9c79a 60%, #8a7a52 100%);
}
.motion__rows {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.motion__rows span {
  height: 8px;
  border-radius: 4px;
  background: var(--line-soft);
}
.motion__rows span:nth-child(2) {
  width: 80%;
}
.motion__rows span:nth-child(3) {
  width: 55%;
}
.motion__now {
  font-size: 13.5px;
  color: var(--muted);
}
@media (max-width: 720px) {
  .motion {
    grid-template-columns: 1fr;
  }
}
</style>
