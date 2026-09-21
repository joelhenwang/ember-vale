<script setup lang="ts">
import type { WorldDef } from '../../game/model'
import StoryImage from '../StoryImage.vue'
import TagPill from '../ui/TagPill.vue'
import IconSparkle from '../icons/IconSparkle.vue'
import IconEllipsis from '../icons/IconEllipsis.vue'
import IconBook from '../icons/IconBook.vue'
import IconPencil from '../icons/IconPencil.vue'

defineProps<{ world: WorldDef }>()
defineEmits<{ open: [] }>()
</script>

<template>
  <article
    class="worldcard ev-card"
    role="button"
    tabindex="0"
    @click="$emit('open')"
    @keydown.enter="$emit('open')"
    @keydown.space.prevent="$emit('open')">
    <div class="worldcard__media">
      <StoryImage
        :image-slot="world.imageSlot"
        :alt="`${world.name} vista`"
        class="worldcard__img" />
      <button type="button" class="worldcard__menu" aria-label="World options" @click.stop>
        <IconEllipsis :size="15" />
      </button>
    </div>
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
          {{ world.places }} places ·
          <template v-if="world.usedInStories !== null">
            Used in {{ world.usedInStories }}
            {{ world.usedInStories === 1 ? 'story' : 'stories' }}
          </template>
          <template v-else>usage not tracked yet</template>
          <template v-if="world.revision !== null"> · rev {{ world.revision }}</template>
        </p>
        <button type="button" class="worldcard__edit" @click.stop>
          <IconPencil :size="12" /> Edit
        </button>
      </div>
    </div>
  </article>
</template>

<style scoped>
.worldcard {
  display: flex;
  flex-direction: column;
  overflow: hidden;
  cursor: pointer;
  transition:
    transform 0.14s ease,
    box-shadow 0.14s ease,
    border-color 0.14s ease;
}
.worldcard:hover {
  transform: translateY(-1px);
  border-color: #c6b48a;
  box-shadow:
    0 10px 20px -16px rgba(96, 74, 40, 0.55),
    inset 0 1px 0 rgba(255, 252, 240, 0.7);
}
.worldcard__media {
  position: relative;
}
.worldcard__img {
  width: 100%;
  aspect-ratio: 16 / 7.4;
  object-fit: cover;
  object-position: 50% 45%;
  box-shadow: inset 0 -1px 0 rgba(190, 166, 118, 0.4);
}
.worldcard__menu {
  position: absolute;
  top: 9px;
  right: 9px;
  width: 27px;
  height: 25px;
  border-radius: 8px;
  border: 1px solid #dccfa9;
  background: #fcf7eae6;
  color: #6c5f45;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
}
.worldcard__menu:hover {
  color: var(--teal-ink);
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
.worldcard__edit {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  height: 31px;
  padding: 0 12px;
  border-radius: 8px;
  border: 1px solid #cdbb93;
  background: #fcf7ea;
  font-size: 14px;
  font-weight: 500;
  color: var(--ink-2);
  transition:
    border-color 0.14s ease,
    color 0.14s ease;
}
.worldcard__edit:hover {
  border-color: #b39c6d;
  color: var(--teal-ink);
}
</style>
