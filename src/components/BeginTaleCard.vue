<script setup lang="ts">
import { useRouter } from 'vue-router'
import { menuState } from '../game/state'
import MenuButton from './MenuButton.vue'
import CompassRose from './decor/CompassRose.vue'
import ScrollDesk from './decor/ScrollDesk.vue'
import MountainRidge from './decor/MountainRidge.vue'
import IconSparkle from './icons/IconSparkle.vue'
import IconEmblem from './icons/IconEmblem.vue'
import IconBook from './icons/IconBook.vue'

const router = useRouter()
</script>

<template>
  <section class="begin ev-card" aria-label="Start a new story">
    <CompassRose class="begin__rose" />
    <ScrollDesk class="begin__art" />

    <div class="begin__body">
      <h2 class="begin__title">Begin a new tale</h2>
      <div class="ev-divider begin__rule" aria-hidden="true">
        <IconSparkle :size="13" />
      </div>
      <p class="begin__copy">
        New lands, new people, new possibilities. Let your imagination shape what comes next in
        Ember Vale.
      </p>

      <MenuButton class="begin__cta" size="lg" @click="router.push({ name: 'new-story' })">
        <template #icon><IconEmblem :size="22" /></template>
        New Story
      </MenuButton>
      <MenuButton
        class="begin__cta2"
        variant="outline"
        size="md"
        @click="router.push({ name: 'new-story' })">
        <template #icon><IconBook :size="20" /></template>
        Quick Start: {{ menuState.quickStartWorld }}
      </MenuButton>

      <p class="ev-quote begin__motto">“{{ menuState.motto }}”</p>
    </div>

    <MountainRidge class="begin__ridge" aria-hidden="true" />
  </section>
</template>

<style scoped>
.begin {
  display: flex;
  flex-direction: column;
  padding: 24px 26px 0;
  overflow: hidden;
}

/* decor -------------------------------------------------------------------- */
.begin__rose {
  position: absolute;
  top: -34px;
  right: -30px;
  width: 172px;
  opacity: 0.55;
  pointer-events: none;
}
.begin__art {
  position: absolute;
  top: 4px;
  right: 10px;
  width: 208px;
  pointer-events: none;
}
.begin__ridge {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  height: 112px;
  opacity: 0.8;
  pointer-events: none;
}

/* content ------------------------------------------------------------------ */
.begin__body {
  position: relative;
  z-index: 1;
  display: flex;
  flex-direction: column;
  flex: 1;
  min-width: 0;
}
.begin__title {
  font-family: var(--font-display);
  font-size: 34px;
  font-weight: 600;
  letter-spacing: 0.01em;
  color: #26200f;
}
.begin__rule {
  width: 206px;
  margin-top: 13px;
  color: var(--gold);
}
.begin__copy {
  margin-top: 15px;
  max-width: 30ch;
  font-size: 16.5px;
  line-height: 1.5;
  color: var(--ink-2);
}
.begin__cta {
  margin-top: 24px;
}
.begin__cta2 {
  margin-top: 12px;
}
.begin__motto {
  margin: auto auto 20px;
  padding-top: 26px;
  font-size: 16.5px;
  text-align: center;
}
</style>
