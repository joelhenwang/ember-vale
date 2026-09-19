<script setup lang="ts">
import { computed } from 'vue'
import { selectedCharacters, toggleCharacter } from '../../game/catalog'
import { resolveImage } from '../../game/images'
import type { CharacterDef } from '../../game/model'
import TagPill from '../ui/TagPill.vue'
import IconUsers from '../icons/IconUsers.vue'
import IconX from '../icons/IconX.vue'
import IconGrip from '../icons/IconGrip.vue'
import IconInfo from '../icons/IconInfo.vue'

interface CastRow extends CharacterDef {
  avatar: string
}

/** resolveImage() (not useGameImage) inside a computed: no throwaway refs,
 *  still fully reactive because the registry object is watched here. */
const cast = computed<CastRow[]>(() =>
  selectedCharacters.value.map((c) => ({
    ...c,
    avatar: resolveImage(c.imageSlot)
  }))
)
</script>

<template>
  <section class="cast-panel ev-card" aria-label="Selected cast">
    <h2 class="cast-panel__title">
      <IconUsers :size="20" />
      Selected cast
      <span class="cast-panel__count">· {{ selectedCharacters.length }}</span>
    </h2>

    <TransitionGroup tag="ul" name="row" class="cast-panel__rows">
      <li v-for="c in cast" :key="c.id" class="cast-panel__row">
        <IconGrip :size="15" class="cast-panel__grip" />
        <img class="cast-panel__avatar" :src="c.avatar" :alt="c.name" />
        <div class="cast-panel__who">
          <span class="cast-panel__name">{{ c.name }}</span>
          <TagPill :tag="{ label: c.role, tone: 'tan' }" small />
        </div>
        <button
          type="button"
          class="cast-panel__x"
          :aria-label="`Remove ${c.name} from the cast`"
          @click="toggleCharacter(c.id)">
          <IconX :size="13" />
        </button>
      </li>
    </TransitionGroup>

    <p v-if="!cast.length" class="cast-panel__empty">
      No one has joined yet — pick at least one character.
    </p>

    <div class="cast-panel__note">
      <IconInfo :size="18" />
      <p>Playable character selection comes after Play Mode.</p>
    </div>
  </section>
</template>

<style scoped>
.cast-panel {
  padding: 18px 18px 16px;
}
.cast-panel__title {
  display: flex;
  align-items: center;
  gap: 10px;
  font-family: var(--font-display);
  font-size: 21.5px;
  font-weight: 600;
  color: #26200f;
}
.cast-panel__title svg {
  color: var(--gold);
}
.cast-panel__count {
  font-size: 19px;
  font-weight: 600;
}

.cast-panel__rows {
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 14px;
}
.cast-panel__row {
  display: flex;
  align-items: center;
  gap: 11px;
  padding: 8px 10px;
  border: 1px solid #e3d5b4;
  border-radius: 10px;
  background: linear-gradient(180deg, #fdf8ec, #f9f2df);
  box-shadow: 0 1px 1px rgba(96, 74, 40, 0.05);
}
.cast-panel__grip {
  color: #b7a67f;
  flex: none;
  cursor: grab;
}
.cast-panel__avatar {
  width: 42px;
  height: 42px;
  border-radius: 50%;
  object-fit: cover;
  object-position: 50% 22%;
  border: 2px solid #2e7265;
  box-shadow:
    0 0 0 2px #fbf5e6,
    0 1px 2px rgba(96, 74, 40, 0.25);
  flex: none;
}
.cast-panel__who {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 4px;
  min-width: 0;
}
.cast-panel__name {
  font-size: 16.5px;
  font-weight: 600;
  color: var(--ink);
  line-height: 1;
}
.cast-panel__x {
  margin-left: auto;
  flex: none;
  width: 26px;
  height: 26px;
  border-radius: 8px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: #8a7a5c;
  transition:
    background-color 0.14s ease,
    color 0.14s ease;
}
.cast-panel__x:hover {
  background: #f1e4c8;
  color: #6e3b2c;
}

.cast-panel__empty {
  margin-top: 12px;
  padding: 12px;
  border: 1.5px dashed #c8b184;
  border-radius: 10px;
  font-size: 14px;
  color: var(--ink-3);
  text-align: center;
}

.cast-panel__note {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  margin-top: 14px;
  padding: 10px 12px;
  border-radius: 10px;
  background: #ecf0e6;
  border: 1px solid #d8dfcd;
  color: #4c5641;
}
.cast-panel__note svg {
  flex: none;
  margin-top: 1px;
  color: #33504a;
}
.cast-panel__note p {
  font-size: 13.5px;
  line-height: 1.42;
}

/* row enter/leave */
.row-enter-active,
.row-leave-active {
  transition: all 0.22s ease;
}
.row-enter-from,
.row-leave-to {
  opacity: 0;
  transform: translateY(-6px);
}
.row-leave-active {
  position: absolute;
  width: calc(100% - 36px);
}
.row-move {
  transition: transform 0.22s ease;
}
</style>
