<script setup lang="ts">
import { useRouter } from 'vue-router'
import { menuState } from '../game/state'
import type { StorySummary } from '../game/model'

const router = useRouter()
import StoryImage from './StoryImage.vue'
import FramedImage from './ui/FramedImage.vue'
import IconSparkle from './icons/IconSparkle.vue'
import IconFeather from './icons/IconFeather.vue'
import IconArrowInCircle from './icons/IconArrowInCircle.vue'
import IconArrowRight from './icons/IconArrowRight.vue'
import IconPlus from './icons/IconPlus.vue'
import QuickHeroDialog from './QuickHeroDialog.vue'
import { ref } from 'vue'

const heroOpen = ref(false)
import { storyLocation } from '../game/storyRoute'
import { vTilt } from '../composables/useEffects'

function resume(story: StorySummary): void {
  router.push(storyLocation(story.id, story.pov))
}
</script>

<template>
  <section class="recent" aria-labelledby="recent-heading">
    <div class="recent__head">
      <h2 class="recent__heading" id="recent-heading">
        <IconSparkle :size="17" class="recent__spark" />
        Recent stories
      </h2>
      <router-link class="ev-link" to="/stories">
        View all stories
        <IconArrowRight :size="12" class="ev-chevron" />
      </router-link>
    </div>

    <div class="recent__grid">
      <article
        v-for="(story, i) in menuState.recent"
        :key="story.id"
        v-tilt="4"
        class="recent__card ev-card"
        :style="{ '--i': i }"
        tabindex="0"
        role="button"
        :aria-label="`Resume ${story.title}`"
        @click="resume(story)"
        @keydown.enter="resume(story)"
        @keydown.space.prevent="resume(story)">
        <FramedImage
          v-if="story.cover"
          class="recent__img"
          :src="story.cover.src"
          :frame="story.cover.frame"
          :alt="`${story.title}: its world`" />
        <StoryImage
          v-else
          class="recent__img"
          :image-slot="story.imageSlot"
          :alt="`${story.title} — scene`" />
        <div class="recent__body">
          <h3 class="recent__title">
            <component
              :is="story.mark === 'leaf' ? IconFeather : IconSparkle"
              :size="16"
              class="recent__mark" />
            {{ story.title }}
          </h3>
          <p class="recent__meta">
            {{ story.pov === 'Player' ? 'You play' : 'Watching' }} · Day {{ story.beat.day }} ·
            {{ story.beat.timeOfDay }}
          </p>
          <p class="recent__logline">In {{ story.beat.location }}</p>
        </div>
        <span class="recent__go" aria-hidden="true">
          <IconArrowInCircle :size="24" />
        </span>
      </article>
      <div class="recent__card recent__new ev-card" :style="{ '--i': menuState.recent.length }">
        <router-link
          class="recent__plus"
          :to="{ name: 'new-story' }"
          aria-label="Start a new story">
          <IconPlus :size="28" />
        </router-link>
        <span class="recent__body">
          <router-link class="recent__title recent__newlink" :to="{ name: 'new-story' }"
            >Start a new story</router-link
          >
          <span class="recent__logline">Choose a world and someone to be.</span>
          <span class="recent__quick">
            <router-link :to="{ name: 'new-story', query: { quickstart: '1' } }"
              >Quick start in {{ menuState.quickStartWorld }}</router-link
            >
            <button type="button" @click="heroOpen = true">Play as a new hero</button>
          </span>
        </span>
      </div>
    </div>
    <QuickHeroDialog :open="heroOpen" @close="heroOpen = false" />
  </section>
</template>

<style scoped>
.recent {
  margin-top: 26px;
}

.recent__head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: 14px;
}
.recent__heading {
  display: inline-flex;
  align-items: center;
  gap: 11px;
  font-family: var(--font-display);
  font-size: 27px;
  font-weight: 600;
  color: #26200f;
}
.recent__spark {
  color: var(--gold);
  transform: translateY(-1px);
  animation: recent-twinkle 4.8s var(--ease-sine) infinite;
}
@keyframes recent-twinkle {
  0%,
  70%,
  100% {
    transform: translateY(-1px) scale(1) rotate(0deg);
  }
  80% {
    transform: translateY(-1px) scale(1.25) rotate(20deg);
    color: var(--ember-hi);
  }
}

/* cards ---------------------------------------------------------------------- */
.recent__grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 18px;
}
.recent__card {
  display: flex;
  align-items: center;
  gap: 15px;
  padding: 8px 12px 8px 8px;
  min-height: 126px;
  cursor: pointer;
  animation: recent-in 0.7s var(--ease-settle) backwards;
  animation-delay: calc(0.25s + var(--i, 0) * 0.08s);
  transition:
    transform 0.5s var(--ease-settle),
    box-shadow 0.3s var(--ease-settle),
    border-color 0.2s ease;
}
@keyframes recent-in {
  from {
    opacity: 0;
    transform: translateY(18px) scale(0.97);
  }
}
.recent__card:hover {
  border-color: #c6b48a;
  box-shadow:
    var(--card-shadow),
    0 10px 22px -16px rgba(96, 74, 40, 0.5),
    inset 0 1px 0 rgba(255, 252, 240, 0.7);
}
/* the tilt's glare lights the card without washing out its words */
.recent__card::before {
  mix-blend-mode: soft-light;
}
.recent__img {
  transition: filter 0.4s var(--ease-settle);
  width: 42%;
  max-width: 220px;
  height: 108px;
  object-fit: cover;
  border-radius: 8px;
  flex: none;
  box-shadow:
    0 1px 2px rgba(96, 74, 40, 0.25),
    inset 0 0 0 1px rgba(120, 96, 56, 0.2);
}
.recent__card:hover .recent__img {
  filter: brightness(1.05) saturate(1.08);
}
.recent__body {
  min-width: 0;
}
.recent__title {
  display: flex;
  align-items: center;
  gap: 9px;
  font-family: var(--font-display);
  font-size: 20.5px;
  font-weight: 600;
  color: #2b2413;
}
.recent__mark {
  color: var(--gold);
  flex: none;
}
.recent__meta {
  margin-top: 2px;
  font-size: 14.5px;
  font-weight: 500;
  color: #55482f;
}
.recent__logline {
  margin-top: 5px;
  font-size: 15px;
  line-height: 1.42;
  color: var(--ink-2);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.recent__go {
  margin-left: auto;
  flex: none;
  width: 40px;
  height: 40px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid #c8b691;
  border-radius: 50%;
  background: #fbf5e6;
  color: #4c4130;
  box-shadow: inset 0 1px 0 #fffdf5;
  transition:
    color 0.15s ease,
    border-color 0.15s ease,
    transform 0.15s ease;
}
.recent__card:hover .recent__go {
  color: var(--teal-ink);
  border-color: #9db39b;
  transform: translateX(4px);
}
.recent__card:active:not(.recent__new) {
  transform: scale(0.98);
  transition-duration: 0.1s;
}

.recent__new {
  color: inherit;
  cursor: default;
}
.recent__newlink {
  color: inherit;
  text-decoration: none;
}
.recent__newlink:hover {
  color: var(--teal-ink);
}
/* the two quick ways in, kept from the old "Begin a new tale" card */
.recent__quick {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 14px;
  margin-top: 6px;
  font-family: var(--font-ui);
  font-size: 14.5px;
}
.recent__quick a,
.recent__quick button {
  color: var(--teal-ink);
  text-decoration: underline;
  text-underline-offset: 3px;
}
.recent__new .recent__body {
  display: flex;
  flex-direction: column;
}
.recent__plus {
  display: grid;
  place-items: center;
  flex: none;
  width: 108px;
  height: 108px;
  border-radius: 8px;
  border: 1px dashed var(--line-strong);
  background: var(--panel-2);
  color: var(--teal-ink);
  transition:
    transform 0.45s var(--ease-settle),
    border-color 0.2s ease,
    background-color 0.2s ease;
}
.recent__plus svg {
  transition: transform 0.5s var(--ease-settle);
}
.recent__new:hover .recent__plus {
  border-color: var(--teal-ink);
  background-color: #eef3ec;
}
.recent__new:hover .recent__plus svg {
  transform: rotate(90deg) scale(1.12);
}
.recent__plus:active {
  transform: scale(0.94);
}

@media (max-width: 1180px) {
  .recent__grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
@media (max-width: 760px) {
  .recent__grid {
    grid-template-columns: 1fr;
  }
}
</style>
