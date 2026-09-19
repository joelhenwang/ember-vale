<script setup lang="ts">
import { useRouter } from 'vue-router'
import { catalog } from '../../game/catalog'
import StoryImage from '../StoryImage.vue'
import IconSparkle from '../icons/IconSparkle.vue'
import IconArrowRight from '../icons/IconArrowRight.vue'

const world = catalog.worlds[0] // Quick Start picked Ember Vale on step 1
const router = useRouter()
</script>

<template>
  <section class="world-mini ev-card" aria-label="World">
    <div class="world-mini__head">
      <h2 class="world-mini__title">
        <IconSparkle :size="14" />
        World
      </h2>
      <a class="ev-link" href="#" @click.prevent="router.push('/library?tab=worlds')">
        Change
        <IconArrowRight :size="11" class="ev-chevron" />
      </a>
    </div>
    <h3 class="world-mini__name">{{ world.name }}</h3>
    <StoryImage
      :image-slot="world.imageSlot"
      :alt="`${world.name} vista`"
      class="world-mini__img" />
    <p class="world-mini__copy">New lands, new people, new possibilities.</p>
  </section>
</template>

<style scoped>
.world-mini {
  padding: 16px 18px 15px;
}
.world-mini__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.world-mini__title {
  display: inline-flex;
  align-items: center;
  gap: 9px;
  font-family: var(--font-display);
  font-size: 21.5px;
  font-weight: 600;
  color: #26200f;
}
.world-mini__title svg {
  color: var(--gold);
}
.world-mini__name {
  margin-top: 8px;
  font-family: var(--font-display);
  font-size: 24px;
  font-weight: 600;
  color: #26200f;
}
.world-mini__img {
  margin-top: 10px;
  width: 100%;
  aspect-ratio: 16 / 7;
  object-fit: cover;
  border-radius: 8px;
  box-shadow:
    0 1px 2px rgba(96, 74, 40, 0.25),
    inset 0 0 0 1px rgba(120, 96, 56, 0.22);
}
.world-mini__copy {
  margin-top: 9px;
  font-size: 14.5px;
  color: var(--ink-3);
}
</style>
