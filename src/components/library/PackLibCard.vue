<script setup lang="ts">
import type { PackDef } from '../../game/model'
import TagPill from '../ui/TagPill.vue'
import IconSparkle from '../icons/IconSparkle.vue'
import IconBook from '../icons/IconBook.vue'
import IconPencil from '../icons/IconPencil.vue'

defineProps<{ pack: PackDef }>()
</script>

<template>
  <article class="packcard ev-card">
    <div class="packcard__top">
      <IconSparkle :size="14" class="packcard__spark" />
      <h3 class="packcard__name">{{ pack.name }}</h3>
    </div>
    <p class="packcard__blurb">{{ pack.blurb }}</p>
    <div class="packcard__tags">
      <TagPill v-for="t in pack.tags" :key="t.label" :tag="t" />
    </div>
    <div class="packcard__rule" aria-hidden="true"><IconSparkle :size="10" /></div>
    <div class="packcard__foot">
      <p class="packcard__used">
        <IconBook :size="14" />
        Used in {{ pack.usedInStories }} {{ pack.usedInStories === 1 ? 'story' : 'stories' }}
      </p>
      <button type="button" class="packcard__edit"><IconPencil :size="12" /> Edit</button>
    </div>
  </article>
</template>

<style scoped>
.packcard {
  padding: 15px 17px 13px;
  display: flex;
  flex-direction: column;
  transition:
    transform 0.14s ease,
    box-shadow 0.14s ease,
    border-color 0.14s ease;
}
.packcard:hover {
  transform: translateY(-1px);
  border-color: #c6b48a;
  box-shadow:
    0 10px 20px -16px rgba(96, 74, 40, 0.55),
    inset 0 1px 0 rgba(255, 252, 240, 0.7);
}
.packcard__top {
  display: flex;
  align-items: center;
  gap: 10px;
}
.packcard__spark {
  color: var(--gold);
}
.packcard__name {
  font-family: var(--font-display);
  font-size: 23px;
  font-weight: 600;
  color: #26200f;
}
.packcard__blurb {
  margin-top: 4px;
  font-size: 15px;
  line-height: 1.45;
  color: var(--ink-2);
}
.packcard__tags {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
  margin-top: 10px;
}
.packcard__rule {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 12px;
  color: var(--gold-soft);
}
.packcard__rule::before,
.packcard__rule::after {
  content: '';
  flex: 1;
  height: 1px;
  background: #dfcda1;
}
.packcard__foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-top: 10px;
}
.packcard__used {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  font-size: 13px;
  color: #6c5f45;
}
.packcard__used svg {
  color: var(--gold);
}
.packcard__edit {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  height: 29px;
  padding: 0 11px;
  border-radius: 8px;
  border: 1px solid #cdbb93;
  background: #fcf7ea;
  font-size: 13.5px;
  font-weight: 500;
  color: var(--ink-2);
}
.packcard__edit:hover {
  border-color: #b39c6d;
  color: var(--teal-ink);
}
</style>
