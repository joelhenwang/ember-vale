<script setup lang="ts">
import type { WorldDef } from '../../game/model'
import StoryImage from '../StoryImage.vue'
import FramedImage from '../ui/FramedImage.vue'
import TagPill from '../ui/TagPill.vue'
import IconSparkle from '../icons/IconSparkle.vue'
import IconBook from '../icons/IconBook.vue'
import CardMenu, { type CardMenuItem } from '../ui/CardMenu.vue'
import CompassRose from '../decor/CompassRose.vue'

defineProps<{ world: WorldDef; menu: CardMenuItem[] }>()
defineEmits<{ open: []; pick: [key: string] }>()
</script>

<template>
  <article
    class="worldcard ev-card ev-lift"
    role="button"
    tabindex="0"
    @click="$emit('open')"
    @keydown.enter="$emit('open')"
    @keydown.space.prevent="$emit('open')">
    <div class="worldcard__media">
      <FramedImage
        v-if="world.cover"
        :src="world.cover.src"
        :frame="world.cover.frame"
        :alt="`${world.name} vista`"
        class="worldcard__img" />
      <StoryImage
        v-else-if="world.imageSlot !== 'world.map'"
        :image-slot="world.imageSlot"
        :alt="`${world.name} vista`"
        class="worldcard__img" />
      <!-- no picture yet: blank parchment with a compass, not stock art -->
      <div v-else class="worldcard__img worldcard__blank" aria-hidden="true">
        <CompassRose class="worldcard__rose" />
      </div>
    </div>
    <CardMenu
      class="worldcard__menu"
      :items="menu"
      :label="`Options for ${world.name}`"
      @pick="$emit('pick', $event)" />
    <div class="worldcard__body">
      <h3 class="worldcard__name">{{ world.name }}</h3>
      <p class="worldcard__blurb">{{ world.blurb }}</p>
      <div class="worldcard__tags">
        <TagPill v-for="t in world.tags" :key="t.label" :tag="t" />
      </div>
      <div class="worldcard__rule" aria-hidden="true"><IconSparkle :size="11" /></div>
      <div class="worldcard__foot">
        <p class="worldcard__used">
          <IconBook :size="15" />
          {{ world.places }} {{ world.places === 1 ? 'place' : 'places' }}
        </p>
      </div>
    </div>
  </article>
</template>

<style scoped>
.worldcard {
  display: flex;
  flex-direction: column;
  cursor: pointer;
}
.worldcard__media {
  position: relative;
  overflow: hidden;
  border-radius: var(--radius-card) var(--radius-card) 0 0;
}
.worldcard__img {
  width: 100%;
  aspect-ratio: 16 / 7.4;
  object-fit: cover;
  object-position: 50% 45%;
  box-shadow: inset 0 -1px 0 rgba(190, 166, 118, 0.4);
}
.worldcard__blank {
  display: flex;
  align-items: center;
  justify-content: center;
  background:
    radial-gradient(circle at 50% 45%, rgba(255, 250, 235, 0.9), transparent 70%),
    linear-gradient(180deg, #efe2c2, #e6d5ad);
}
.worldcard__rose {
  width: 46%;
  max-width: 150px;
  color: #9a7b3f;
  opacity: 0.55;
  transition: transform 1.2s var(--ease-out);
}
.worldcard:hover .worldcard__rose {
  transform: rotate(45deg);
}
.worldcard__menu {
  position: absolute;
  top: 9px;
  right: 9px;
  z-index: 2;
}
.worldcard__body {
  padding: 13px 16px 13px;
  display: flex;
  flex-direction: column;
  flex: 1;
}
.worldcard__name {
  font-family: var(--font-display);
  font-size: 28px;
  font-weight: 600;
  line-height: 1.05;
  color: #26200f;
}
.worldcard__blurb {
  margin-top: 3px;
  font-size: 15.5px;
  line-height: 1.4;
  color: var(--ink-2);
}
.worldcard__tags {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
  margin-top: 10px;
}
.worldcard__rule {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 12px 2px 0;
  color: var(--gold-soft);
}
.worldcard__rule::before,
.worldcard__rule::after {
  content: '';
  flex: 1;
  height: 1px;
  background: #dfcda1;
}
.worldcard__foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-top: 10px;
}
.worldcard__used {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 13.5px;
  color: #6c5f45;
}
.worldcard__used svg {
  color: var(--gold);
}
</style>
