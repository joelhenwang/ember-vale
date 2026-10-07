<script setup lang="ts">
/**
 * The current story, inviting you back in. A banner runs from the story's
 * world picture into its latest painted moment; under it, who you play,
 * where the story stands, what happened last time and Continue, beside
 * the latest key moment (opened like a page of the story).
 */
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { menuState } from '../game/state'
import { useGameImage } from '../game/images'
import { assetUrl } from '../api/worldsim'
import { momentTitle } from '../game/moments'
import MenuButton from './MenuButton.vue'
import FramedImage from './ui/FramedImage.vue'
import MomentDialog from './story/MomentDialog.vue'
import { storyLocation } from '../game/storyRoute'
import IconSparkle from './icons/IconSparkle.vue'
import IconArrowRight from './icons/IconArrowRight.vue'

const router = useRouter()
const story = computed(() => menuState.current)
const fallbackCover = useGameImage('hero.currentStory')
const playing = computed(() => story.value?.playing ?? null)
const moments = computed(() => playing.value?.moments ?? [])
const latest = computed(() => moments.value[moments.value.length - 1] ?? null)
const latestUrl = computed(() =>
  story.value && latest.value?.asset_id ? assetUrl(story.value.id, latest.value.asset_id) : null
)
/** The world's own picture; else where you stand; else the house art. */
const worldCover = computed(() => story.value?.cover ?? null)
const plainCover = computed(() => playing.value?.sceneUrl ?? fallbackCover.value)

const speakers = computed(() => new Map(Object.entries(playing.value?.speakers ?? {})))
const places = computed(() => new Map(Object.entries(playing.value?.places ?? {})))
const opened = ref<number | null>(null)
const opts = computed(() => ({
  role: 'player' as const,
  characterId: playing.value?.characterId
}))

function openLatest(): void {
  if (moments.value.length) opened.value = moments.value.length - 1
}
</script>

<template>
  <section class="hero ev-card" aria-label="Current story">
    <div class="hero__banner" :class="{ 'hero__banner--paired': latestUrl }">
      <FramedImage
        v-if="worldCover"
        class="hero__world"
        :src="worldCover.src"
        :frame="worldCover.frame"
        :alt="`${story?.title ?? 'Ember Vale'}: its world`" />
      <img
        v-else
        class="hero__world"
        :src="plainCover"
        :alt="`${story?.title ?? 'Ember Vale'}: a scene`" />
      <button
        v-if="latestUrl && latest"
        class="hero__moment"
        type="button"
        :aria-label="`Open the latest key moment: ${momentTitle(latest)}`"
        @click="openLatest">
        <img :src="latestUrl" alt="" />
      </button>
    </div>

    <div v-if="story" class="hero__body" :class="{ 'hero__body--moment': latest }">
      <img
        v-if="playing?.portraitUrl"
        class="hero__portrait"
        :src="playing.portraitUrl"
        :alt="playing.name" />

      <div class="hero__story">
        <span class="ev-eyebrow">Current story</span>
        <h1 class="hero__title">{{ story.title }}</h1>
        <p class="hero__meta">
          Day {{ story.beat.day }} · {{ story.beat.timeOfDay }} · {{ story.beat.location }}
        </p>
        <p v-if="playing" class="hero__you">
          Playing as <b>{{ playing.name }}</b>
          <template v-if="playing.title"> · {{ playing.title }}</template>
        </p>
        <div class="hero__resume">
          <p class="hero__logline">
            <template v-if="playing?.lastLine">Last time: {{ playing.lastLine }}</template>
            <template v-else>{{ story.logline }}</template>
          </p>
          <MenuButton
            class="hero__continue"
            size="md"
            arrow="circle"
            @click="router.push(storyLocation(story.id, story.pov))">
            {{ playing ? `Continue as ${playing.name}` : 'Continue story' }}
          </MenuButton>
        </div>
      </div>

      <button v-if="latest" class="hero__event" type="button" @click="openLatest">
        <span class="ev-eyebrow">Latest key moment</span>
        <span class="hero__event-title">{{ momentTitle(latest) }}</span>
        <span class="hero__event-line">{{ latest.caption }}</span>
        <span class="hero__event-more">
          Read this moment
          <template v-if="moments.length > 1">· {{ moments.length }} in all</template>
          <IconArrowRight :size="12" />
        </span>
      </button>
    </div>

    <div v-else class="hero__body hero__body--empty">
      <div class="hero__story">
        <span class="ev-eyebrow">
          <IconSparkle :size="13" />
          Ember Vale
        </span>
        <h1 class="hero__title">Your first story</h1>
        <p class="hero__logline">
          Choose a world and someone to be, and the vale will remember your story here.
        </p>
      </div>
      <MenuButton
        class="hero__continue"
        size="md"
        arrow="circle"
        @click="router.push({ name: 'new-story' })">
        Begin a story
      </MenuButton>
    </div>

    <MomentDialog
      v-if="story && playing"
      :world-id="story.id"
      :moments="moments"
      :index="opened"
      :speakers="speakers"
      :places="places"
      :opts="opts"
      @update:index="opened = $event"
      @close="opened = null" />
  </section>
</template>

<style scoped>
.hero {
  padding: 10px;
  overflow: hidden;
}

/* banner: the world, fading into the latest painted moment ---------------- */
.hero__banner {
  position: relative;
  height: clamp(200px, 24vw, 350px);
  border-radius: 9px;
  overflow: hidden;
  background: var(--panel-2);
  box-shadow: inset 0 0 0 1px rgba(120, 96, 56, 0.25);
}
.hero__world {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
}
/* The world runs under the moment, so the fade has no edge to show. */
.hero__banner--paired .hero__world {
  object-position: left center;
}
.hero__moment {
  position: absolute;
  top: 0;
  right: 0;
  bottom: 0;
  width: 58%;
  padding: 0;
  cursor: zoom-in;
  -webkit-mask-image: linear-gradient(90deg, transparent 0, #000 34%);
  mask-image: linear-gradient(90deg, transparent 0, #000 34%);
}
.hero__moment img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  transition: transform 0.6s var(--ease-out);
}
.hero__moment:hover img,
.hero__moment:focus-visible img {
  transform: scale(1.02);
}

/* body ---------------------------------------------------------------------- */
.hero__body {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  gap: 26px;
  align-items: start;
  padding: 18px 16px 10px;
}
.hero__body--moment {
  grid-template-columns: auto minmax(0, 1.5fr) minmax(0, 1fr);
}
.hero__body--empty {
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
}
.hero__portrait {
  width: 172px;
  aspect-ratio: 4 / 5;
  margin-top: -64px;
  border-radius: 10px;
  object-fit: cover;
  border: 3px solid var(--surface-2);
  box-shadow: var(--card-shadow);
  position: relative;
}
.hero__story {
  min-width: 0;
}
.hero__title {
  margin-top: 6px;
  font-family: var(--font-display);
  font-size: 42px;
  font-weight: 600;
  line-height: 1.05;
  color: var(--ink);
  text-wrap: balance;
}
.hero__meta {
  margin-top: 6px;
  font-size: 17px;
  font-weight: 500;
  color: var(--ink-2);
}
.hero__you {
  margin-top: 2px;
  font-size: 16px;
  color: var(--ink-3);
}
.hero__you b {
  color: var(--ink);
}
.hero__resume {
  display: flex;
  align-items: center;
  gap: 22px;
  margin-top: 14px;
  padding-top: 14px;
  border-top: 1px solid var(--line-soft);
}
.hero__logline {
  flex: 1;
  min-width: 0;
  max-width: 60ch;
  font-size: 17px;
  line-height: 1.5;
  color: var(--ink-2);
}
.hero__continue {
  flex: none;
  width: 260px;
}

.hero__event {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
  padding: 4px 0 4px 24px;
  border-left: 1px solid var(--line);
  text-align: left;
  cursor: pointer;
}
.hero__event-title {
  margin-top: 4px;
  font-family: var(--font-display);
  font-size: 30px;
  font-weight: 600;
  line-height: 1.1;
  color: var(--ink);
  text-wrap: balance;
}
.hero__event-line {
  font-size: 16.5px;
  line-height: 1.45;
  color: var(--ink-2);
}
.hero__event-more {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-top: 6px;
  font-family: var(--font-ui);
  font-size: 15px;
  color: var(--teal-ink);
}
.hero__event:hover .hero__event-title,
.hero__event:focus-visible .hero__event-title {
  color: var(--teal-ink);
}

@media (max-width: 1280px) {
  .hero__body--moment {
    grid-template-columns: auto minmax(0, 1fr);
  }
  .hero__body--moment .hero__event {
    grid-column: 1 / -1;
    padding: 14px 0 0;
    border-left: 0;
    border-top: 1px solid var(--line-soft);
  }
  .hero__resume {
    flex-wrap: wrap;
  }
}
@media (max-width: 720px) {
  .hero__moment {
    width: 70%;
  }
  .hero__body,
  .hero__body--moment,
  .hero__body--empty {
    grid-template-columns: minmax(0, 1fr);
    gap: 14px;
    padding: 14px 6px 6px;
  }
  .hero__portrait {
    width: 112px;
    margin-top: -56px;
  }
  .hero__title {
    font-size: 32px;
  }
  .hero__continue {
    width: 100%;
  }
}
</style>
