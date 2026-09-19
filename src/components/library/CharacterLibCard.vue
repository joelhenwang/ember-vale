<script setup lang="ts">
import type { CharacterDef } from '../../game/model'
import StoryImage from '../StoryImage.vue'
import TagPill from '../ui/TagPill.vue'
import IconSparkle from '../icons/IconSparkle.vue'
import IconEllipsis from '../icons/IconEllipsis.vue'
import IconBook from '../icons/IconBook.vue'

defineProps<{ character: CharacterDef }>()
defineEmits<{ open: [] }>()
</script>

<template>
  <article
    class="libcard ev-card"
    role="button"
    tabindex="0"
    @click="$emit('open')"
    @keydown.enter="$emit('open')"
    @keydown.space.prevent="$emit('open')">
    <StoryImage
      :image-slot="character.imageSlot"
      :alt="`${character.name} portrait`"
      class="libcard__img" />
    <div class="libcard__body">
      <div class="libcard__head">
        <div>
          <h3 class="libcard__name">{{ character.name }}</h3>
          <p class="libcard__role">{{ character.role }}</p>
        </div>
        <button type="button" class="libcard__menu" aria-label="Character options" @click.stop>
          <IconEllipsis :size="15" />
        </button>
      </div>
      <div class="libcard__rule" aria-hidden="true"><IconSparkle :size="10" /></div>
      <p class="libcard__bio">{{ character.bio }}</p>
      <div class="libcard__tags">
        <TagPill v-for="t in character.tags" :key="t.label" :tag="t" />
      </div>
      <p class="libcard__used">
        <IconBook :size="14" />
        Used in {{ character.usedInStories }}
        {{ character.usedInStories === 1 ? 'story' : 'stories' }}
      </p>
    </div>
  </article>
</template>

<style scoped>
.libcard {
  display: flex;
  overflow: hidden;
  cursor: pointer;
  transition:
    transform 0.14s ease,
    box-shadow 0.14s ease,
    border-color 0.14s ease;
  min-height: 196px;
}
.libcard:hover {
  transform: translateY(-1px);
  border-color: #c6b48a;
  box-shadow:
    0 10px 20px -16px rgba(96, 74, 40, 0.55),
    inset 0 1px 0 rgba(255, 252, 240, 0.7);
}
.libcard__img {
  width: 44%;
  min-width: 158px;
  object-fit: cover;
  object-position: 50% 16%;
  box-shadow: inset -1px 0 0 rgba(190, 166, 118, 0.4);
}
.libcard__body {
  position: relative;
  flex: 1;
  min-width: 0;
  padding: 11px 13px 11px 15px;
  display: flex;
  flex-direction: column;
}
.libcard__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
}
.libcard__name {
  font-family: var(--font-display);
  font-size: 24.5px;
  font-weight: 600;
  line-height: 1.02;
  color: #26200f;
}
.libcard__role {
  margin-top: 1px;
  font-size: 15px;
  font-weight: 500;
  color: #55482f;
}
.libcard__menu {
  flex: none;
  width: 27px;
  height: 25px;
  border-radius: 8px;
  border: 1px solid #dccfa9;
  background: #fcf7ea;
  color: #6c5f45;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  transition:
    border-color 0.14s ease,
    color 0.14s ease;
}
.libcard__menu:hover {
  border-color: #b39c6d;
  color: var(--teal-ink);
}
.libcard__rule {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 8px 0 7px;
  color: var(--gold-soft);
}
.libcard__rule::after {
  content: '';
  flex: 1;
  height: 1px;
  background: linear-gradient(90deg, #d8c393, transparent);
}
.libcard__bio {
  font-size: 14px;
  line-height: 1.45;
  color: var(--ink-2);
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.libcard__tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}
.libcard__used {
  margin-top: auto;
  padding-top: 9px;
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 13px;
  color: #6c5f45;
}
.libcard__used svg {
  color: var(--gold);
}

/* list mode: wider row */
:global(.lib--list) .libcard__img {
  width: 240px;
  min-width: 240px;
}
</style>
