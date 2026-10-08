<script setup lang="ts">
import type { CharacterDef } from '../../game/model'
import FramedImage from '../ui/FramedImage.vue'
import StoryImage from '../StoryImage.vue'
import TagPill from '../ui/TagPill.vue'
import IconSparkle from '../icons/IconSparkle.vue'
import CardMenu, { type CardMenuItem } from '../ui/CardMenu.vue'

defineProps<{ character: CharacterDef; menu: CardMenuItem[] }>()
defineEmits<{ open: []; pick: [key: string] }>()
</script>

<template>
  <article
    class="libcard ev-card ev-lift"
    role="button"
    tabindex="0"
    @click="$emit('open')"
    @keydown.enter="$emit('open')"
    @keydown.space.prevent="$emit('open')">
    <span v-if="character.portrait" class="libcard__img">
      <FramedImage
        :src="character.portrait.src"
        :frame="character.portrait.portrait"
        :alt="`${character.name} portrait`" />
    </span>
    <StoryImage
      v-else
      :image-slot="character.imageSlot"
      :alt="`${character.name} portrait`"
      class="libcard__img" />
    <div class="libcard__body">
      <div class="libcard__head">
        <div>
          <h3 class="libcard__name">{{ character.name }}</h3>
          <p v-if="character.role" class="libcard__role">{{ character.role }}</p>
        </div>
        <CardMenu
          :items="menu"
          :label="`Options for ${character.name}`"
          @pick="$emit('pick', $event)" />
      </div>
      <div class="libcard__rule" aria-hidden="true"><IconSparkle :size="10" /></div>
      <p v-if="character.bio" class="libcard__bio">{{ character.bio }}</p>
      <p v-else class="libcard__bio libcard__bio--empty">No description yet: open to write one.</p>
      <div class="libcard__tags">
        <TagPill v-for="t in character.tags" :key="t.label" :tag="t" />
      </div>
    </div>
  </article>
</template>

<style scoped>
/* A tall card: the portrait on top, then who they are at the full width,
   so the role line ("17 years · Human · Female") never runs out of room. */
.libcard {
  display: flex;
  flex-direction: column;
  cursor: pointer;
  overflow: hidden;
}
.libcard__img {
  display: block;
  width: 100%;
  aspect-ratio: 4 / 5;
  max-height: 340px;
  overflow: hidden;
  border-radius: var(--radius-card) var(--radius-card) 0 0;
  object-fit: cover;
  object-position: 50% 16%;
  box-shadow: inset 0 -1px 0 rgba(190, 166, 118, 0.4);
}
.libcard__body {
  position: relative;
  flex: 1;
  min-width: 0;
  padding: 12px 14px 14px;
  display: flex;
  flex-direction: column;
}
.libcard__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
}
.libcard__head > div {
  min-width: 0;
}
.libcard__name {
  font-family: var(--font-display);
  font-size: 25px;
  font-weight: 600;
  line-height: 1.05;
  color: #26200f;
}
.libcard__role {
  margin-top: 2px;
  font-size: 15px;
  font-weight: 500;
  line-height: 1.3;
  color: #55482f;
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
  font-size: 14.5px;
  line-height: 1.45;
  color: var(--ink-2);
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.libcard__bio--empty {
  font-style: italic;
  color: var(--muted);
}
.libcard__tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: auto;
  padding-top: 10px;
}

/* list mode (a row, the portrait at the side) is styled by LibraryView */
</style>
