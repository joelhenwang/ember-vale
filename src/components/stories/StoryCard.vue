<!--
  StoryCard — one saved tale on the Stories shelf (grid or list density).
  Presentation-only: it reads the catalog for cast portraits, but every
  mutation (continue navigation, archive toggle, …) is emitted so the view
  stays the single owner of store access, matching the lib-card pattern.

  The ⋮ menu's only wired action is Archive/Restore — production will grow
  Rename/Duplicate/Delete entries here.
-->
<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import type { Component } from 'vue'
import { catalog } from '../../game/catalog'
import { resolveImage } from '../../game/images'
import type { StoryRecord } from '../../game/stories'
import IconArchive from '../icons/IconArchive.vue'
import IconArrowRight from '../icons/IconArrowRight.vue'
import IconBook from '../icons/IconBook.vue'
import IconClock from '../icons/IconClock.vue'
import IconDotsVertical from '../icons/IconDotsVertical.vue'
import IconEye from '../icons/IconEye.vue'
import IconInfo from '../icons/IconInfo.vue'
import IconMoon from '../icons/IconMoon.vue'
import IconPlay from '../icons/IconPlay.vue'
import IconSun from '../icons/IconSun.vue'
import IconUser from '../icons/IconUser.vue'

const props = defineProps<{ story: StoryRecord; layout: 'grid' | 'list' }>()
const emit = defineEmits<{
  continue: []
  configure: []
  saves: []
  archive: [archived: boolean]
}>()

const artUrl = computed(() => resolveImage(props.story.sceneSlot))

const dayIcon = computed<Component>(() =>
  props.story.timeOfDay === 'Morning' || props.story.timeOfDay === 'Afternoon' ? IconSun : IconMoon
)

const player = computed(() => {
  const mode = props.story.mode
  if (mode.kind !== 'player') return null
  return catalog.characters.find((c) => c.id === mode.characterId)?.name ?? '—'
})

const cast = computed(() =>
  props.story.cast.flatMap((id) => {
    const c = catalog.characters.find((x) => x.id === id)
    return c ? [{ id: c.id, name: c.name, url: resolveImage(c.imageSlot) }] : []
  })
)

/* ————— ⋮ menu (closes on any outside click) ————— */
const menuOpen = ref(false)
const isArchived = computed(() => props.story.status === 'archived')
function closeMenu(): void {
  menuOpen.value = false
}
onMounted(() => window.addEventListener('click', closeMenu))
onBeforeUnmount(() => window.removeEventListener('click', closeMenu))

function menuContinue(): void {
  emit('continue')
  closeMenu()
}
function menuArchive(): void {
  emit('archive', !isArchived.value)
  closeMenu()
}
</script>

<template>
  <article class="scard ev-card" :class="{ 'scard--list': layout === 'list' }">
    <div class="scard__art">
      <img :src="artUrl" :alt="`${story.title} — scene from ${story.world}`" />
      <span class="scard__world">{{ story.world }}</span>
    </div>

    <div class="scard__main">
      <header class="scard__row1">
        <h3 class="scard__title">{{ story.title }}</h3>
        <div class="scard__menu-wrap">
          <button
            type="button"
            class="scard__dots"
            aria-label="Story options"
            aria-haspopup="menu"
            :aria-expanded="menuOpen"
            @click.stop="menuOpen = !menuOpen">
            <IconDotsVertical :size="15" />
          </button>
          <ul v-if="menuOpen" class="scard__menu" role="menu" @click.stop>
            <li>
              <button type="button" role="menuitem" @click="menuContinue">
                <IconPlay :size="11" /> Continue reading
              </button>
            </li>
            <li>
              <button type="button" role="menuitem" @click="menuArchive">
                <IconArchive :size="13" />
                {{ isArchived ? 'Restore from archive' : 'Archive story' }}
              </button>
            </li>
          </ul>
        </div>
      </header>

      <p class="scard__tags">
        <span class="tchip"><IconBook :size="13" /> {{ story.world }}</span>
        <span v-if="player" class="tchip tchip--tan">
          <IconUser :size="13" /> Player · {{ player }}
        </span>
        <span v-else class="tchip tchip--teal"><IconEye :size="13" /> Watcher</span>
      </p>

      <p class="scard__meta">
        <span class="meta"
          ><component :is="dayIcon" :size="14" /> Day {{ story.day }} · {{ story.timeOfDay }}</span
        >
        <span class="meta"><IconClock :size="14" /> {{ story.lastPlayedLabel }}</span>
      </p>

      <p class="scard__blurb">{{ story.blurb }}</p>

      <ul class="scard__cast">
        <li v-for="c in cast" :key="c.id">
          <img :src="c.url" :alt="c.name" />
          <span>{{ c.name }}</span>
        </li>
      </ul>

      <div class="scard__actions">
        <button type="button" class="cta scard__continue" @click="emit('continue')">
          <IconPlay :size="12" /> Continue
        </button>
        <button type="button" class="scard__config" @click="emit('configure')">
          <IconInfo :size="16" /> Initial configuration
        </button>
      </div>

      <div class="scard__saveswrap">
        <button type="button" class="scard__saves" @click="emit('saves')">
          View story & saves <IconArrowRight :size="13" />
        </button>
      </div>
    </div>
  </article>
</template>

<style scoped>
.scard {
  padding: 0;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

/* ————— scene art strip ————— */
.scard__art {
  position: relative;
  margin: 10px 10px 0;
  border-radius: 11px;
  overflow: hidden;
  aspect-ratio: 16 / 9.4;
  background: #efe4c9;
}
.scard__art img {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.scard__world {
  position: absolute;
  left: 12px;
  bottom: 8px;
  font-size: 15px;
  font-weight: 500;
  color: #fdf8ec;
  text-shadow: 0 1px 5px rgba(28, 22, 10, 0.75);
}
.scard__art::after {
  content: '';
  position: absolute;
  inset: auto 0 0 0;
  height: 46%;
  background: linear-gradient(180deg, transparent, rgba(30, 24, 12, 0.48));
  pointer-events: none;
}

/* ————— body ————— */
.scard__main {
  padding: 0 16px 12px;
  display: flex;
  flex-direction: column;
  flex: 1;
}
.scard__row1 {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin-top: 12px;
}
.scard__title {
  font-family: var(--font-display);
  font-size: 24px;
  font-weight: 600;
  line-height: 1.15;
  color: var(--ink);
  min-width: 0;
}
.scard__menu-wrap {
  position: relative;
  margin-left: auto;
  flex: none;
}
.scard__dots {
  width: 30px;
  height: 30px;
  border-radius: 8px;
  color: #6c5f45;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  transition: background 0.14s ease;
}
.scard__dots:hover {
  background: rgba(196, 172, 126, 0.2);
}
.scard__menu {
  position: absolute;
  z-index: 30;
  top: 32px;
  right: 0;
  width: 196px;
  padding: 6px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.scard__menu button {
  width: 100%;
  height: 34px;
  border-radius: 7px;
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 0 10px;
  font-size: 14.5px;
  font-weight: 500;
  color: var(--ink-2);
  transition: background 0.12s ease;
}
.scard__menu button:hover {
  background: rgba(37, 110, 103, 0.09);
  color: var(--teal);
}

/* ————— chips & meta ————— */
.scard__tags {
  display: flex;
  gap: 8px;
  margin-top: 10px;
  flex-wrap: wrap;
}
.tchip {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  height: 30px;
  padding: 0 11px;
  border-radius: 8px;
  border: 1px solid #d9c8a3;
  background: #fcf7ea;
  font-size: 14px;
  font-weight: 500;
  color: var(--ink-2);
}
.tchip--teal {
  background: #dcebe3;
  border-color: #b9d3c6;
  color: var(--teal);
}
.tchip--tan {
  background: #f3e5c8;
  border-color: #dfc99d;
  color: #6d5320;
}
.scard__meta {
  display: flex;
  gap: 20px;
  margin-top: 11px;
  flex-wrap: wrap;
}
.meta {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  font-size: 14.5px;
  color: var(--ink-2);
}
.meta svg {
  color: #8a6d2f;
}
.scard__blurb {
  margin-top: 9px;
  font-size: 15px;
  color: #55482f;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* ————— cast strip ————— */
.scard__cast {
  display: flex;
  gap: 16px;
  margin-top: 13px;
}
.scard__cast img {
  width: 64px;
  height: 64px;
  border-radius: 10px;
  object-fit: cover;
  display: block;
  border: 1px solid #d9c8a3;
  box-shadow: 0 1px 4px rgba(96, 74, 40, 0.18);
}
.scard__cast span {
  display: block;
  width: 64px;
  margin-top: 5px;
  text-align: center;
  font-size: 13px;
  color: var(--ink-2);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* ————— actions ————— */
.scard__actions {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-top: 14px;
  padding-top: 13px;
  border-top: 1px solid #eadfc4;
}
.scard__continue {
  min-width: 172px;
}
.scard__config {
  display: inline-flex;
  align-items: center;
  gap: 9px;
  font-size: 15.5px;
  font-weight: 500;
  color: var(--ink-2);
  transition: color 0.14s ease;
}
.scard__config:hover {
  color: var(--teal-ink);
}
.scard__saveswrap {
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px solid #eadfc4;
  text-align: center;
}
.scard__saves {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  font-size: 14.5px;
  font-weight: 600;
  color: var(--teal-ink);
}
.scard__saves:hover {
  text-decoration: underline;
}

/* ————— list density ————— */
.scard--list {
  flex-direction: row;
  align-items: stretch;
  padding: 12px;
  gap: 18px;
}
.scard--list .scard__art {
  margin: 0;
  width: 320px;
  flex: none;
  aspect-ratio: 16 / 9.4;
  align-self: flex-start;
}
.scard--list .scard__main {
  padding: 0 4px 0 0;
}
.scard--list .scard__title {
  font-size: 26px;
}
</style>
