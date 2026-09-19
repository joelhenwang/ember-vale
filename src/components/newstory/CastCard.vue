<script setup lang="ts">
import type { CharacterDef } from '../../game/model'
import StoryImage from '../StoryImage.vue'
import IconSparkle from '../icons/IconSparkle.vue'
import IconCheck from '../icons/IconCheck.vue'

defineProps<{ character: CharacterDef; selected: boolean }>()
defineEmits<{ toggle: [] }>()
</script>

<template>
  <article
    class="cast"
    :class="{ 'cast--selected': selected }"
    role="button"
    tabindex="0"
    :aria-pressed="selected"
    :aria-label="`${character.name} — ${selected ? 'in the cast' : 'add to cast'}`"
    @click="$emit('toggle')"
    @keydown.enter.prevent="$emit('toggle')"
    @keydown.space.prevent="$emit('toggle')">
    <div class="cast__media">
      <StoryImage
        :image-slot="character.imageSlot"
        :alt="`${character.name} portrait`"
        class="cast__img" />
      <span class="cast__tick" :class="{ 'cast__tick--on': selected }" aria-hidden="true">
        <IconCheck v-if="selected" :size="12" />
      </span>
    </div>
    <div class="cast__body">
      <h3 class="cast__name">{{ character.name }}</h3>
      <p class="cast__role">
        <IconSparkle :size="11" />
        {{ character.role }}
      </p>
      <p class="cast__blurb">{{ character.blurb }}</p>
    </div>
  </article>
</template>

<style scoped>
.cast {
  border: 1px solid var(--line);
  border-radius: 12px;
  overflow: hidden;
  background: linear-gradient(180deg, #fcf7ea, #f8f1df);
  box-shadow: 0 1px 2px rgba(96, 74, 40, 0.08);
  cursor: pointer;
  transition:
    transform 0.14s ease,
    box-shadow 0.14s ease,
    border-color 0.14s ease;
}
.cast:hover {
  transform: translateY(-2px);
  border-color: #bfa978;
  box-shadow: 0 10px 20px -14px rgba(96, 74, 40, 0.5);
}
.cast--selected {
  border-color: #2e7265;
  box-shadow:
    0 0 0 1px #2e7265,
    0 8px 18px -12px rgba(23, 82, 86, 0.5);
}
.cast--selected:hover {
  border-color: #2e7265;
}

.cast__media {
  position: relative;
  aspect-ratio: 5 / 5.6;
  overflow: hidden;
}
.cast__img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  object-position: 50% 18%;
}

.cast__tick {
  position: absolute;
  top: 9px;
  right: 9px;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: #fbf5e6;
  border: 1px solid #c8b691;
  box-shadow: 0 1px 3px rgba(60, 45, 20, 0.28);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--cream-on-teal);
  transition: background 0.14s ease;
}
.cast__tick--on {
  background: linear-gradient(180deg, #256e67, #175a5e);
  border-color: #0f4147;
}

.cast__body {
  padding: 11px 14px 13px;
}
.cast__name {
  font-family: var(--font-display);
  font-size: 24px;
  font-weight: 600;
  line-height: 1.05;
  color: #26200f;
}
.cast__role {
  display: flex;
  align-items: center;
  gap: 7px;
  margin-top: 4px;
  font-size: 14.5px;
  font-weight: 500;
  color: #55482f;
}
.cast__role svg {
  color: var(--gold);
  flex: none;
}
.cast__blurb {
  margin-top: 8px;
  font-size: 14px;
  line-height: 1.42;
  color: var(--ink-2);
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
</style>
