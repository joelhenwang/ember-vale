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
.libcard {
  display: flex;
  cursor: pointer;
  min-height: 196px;
}
.libcard__img {
  overflow: hidden;
  border-radius: var(--radius-card) 0 0 var(--radius-card);
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
.libcard__bio--empty {
  font-style: italic;
  color: var(--muted);
}
.libcard__role {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
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
