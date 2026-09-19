<script setup lang="ts">
import CompassRose from '../decor/CompassRose.vue'
import MountainRidge from '../decor/MountainRidge.vue'
import IconPlus from '../icons/IconPlus.vue'
</script>

<template>
  <button type="button" class="ctile" @click="$emit('create')">
    <CompassRose class="ctile__rose" />
    <span class="ctile__plus"><IconPlus :size="16" /></span>
    <h3 class="ctile__title">Create a new<br />character</h3>
    <p class="ctile__copy">Bring a new companion to life in Ember Vale.</p>
    <MountainRidge class="ctile__ridge" />
  </button>
</template>

<style scoped>
.ctile {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: flex-start;
  text-align: center;
  gap: 0;
  padding: 26px 16px 16px;
  border: 1.5px dashed #c8b184;
  border-radius: 12px;
  background: #faf3e2;
  color: inherit;
  cursor: pointer;
  overflow: hidden;
  transition:
    border-color 0.15s ease,
    background-color 0.15s ease,
    transform 0.15s ease;
}
.ctile:hover {
  border-color: #a98d57;
  background: #f8efdb;
  transform: translateY(-2px);
}

.ctile__rose {
  position: absolute;
  top: 18px;
  left: 50%;
  transform: translateX(-50%) scale(0.62);
  transform-origin: top center;
  width: 140px;
  opacity: 0.75;
  pointer-events: none;
}
.ctile__plus {
  margin-top: 78px;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  border: 1.5px solid #a98d57;
  color: #6d5a34;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: #fbf5e6;
  transition:
    color 0.15s ease,
    border-color 0.15s ease;
}
.ctile:hover .ctile__plus {
  color: var(--teal-ink);
  border-color: var(--teal-ink);
}
.ctile__title {
  margin-top: 12px;
  font-family: var(--font-display);
  font-size: 20.5px;
  font-weight: 600;
  line-height: 1.15;
  color: #26200f;
}
.ctile__copy {
  margin-top: 8px;
  font-size: 13.5px;
  line-height: 1.4;
  color: var(--ink-3);
}
.ctile__ridge {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  height: 76px;
  opacity: 0.85;
  pointer-events: none;
}
</style>
