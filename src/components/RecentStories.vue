<script setup lang="ts">
import { useRouter } from 'vue-router'
import { menuState } from '../game/state'
import type { StorySummary } from '../game/model'

const router = useRouter()
import StoryImage from './StoryImage.vue'
import IconSparkle from './icons/IconSparkle.vue'
import IconFeather from './icons/IconFeather.vue'
import IconArrowInCircle from './icons/IconArrowInCircle.vue'
import IconArrowRight from './icons/IconArrowRight.vue'

function resume(story: StorySummary): void {
  router.push({ name: 'story-play', params: { storyId: story.id } })
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

    <p v-if="!menuState.recent.length" class="recent__empty">
      Your recent stories will appear here once you begin a tale.
    </p>
    <div v-else class="recent__grid">
      <article
        v-for="story in menuState.recent"
        :key="story.id"
        class="recent__card ev-card"
        tabindex="0"
        role="button"
        :aria-label="`Resume ${story.title}`"
        @click="resume(story)"
        @keydown.enter="resume(story)"
        @keydown.space.prevent="resume(story)">
        <StoryImage
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
            <span>{{ story.pov }}</span>
            <span class="ev-dot">•</span>
            <span>Day {{ story.beat.day }}</span>
          </p>
          <p class="recent__logline">{{ story.logline }}</p>
        </div>
        <span class="recent__go" aria-hidden="true">
          <IconArrowInCircle :size="24" />
        </span>
      </article>
    </div>
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
}

/* cards ---------------------------------------------------------------------- */
.recent__grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 26px;
}
.recent__card {
  display: flex;
  align-items: center;
  gap: 15px;
  padding: 8px 12px 8px 8px;
  min-height: 126px;
  cursor: pointer;
  transition:
    transform 0.15s ease,
    box-shadow 0.15s ease,
    border-color 0.15s ease;
}
.recent__card:hover {
  transform: translateY(-1px);
  border-color: #c6b48a;
  box-shadow:
    var(--card-shadow),
    0 10px 22px -16px rgba(96, 74, 40, 0.5),
    inset 0 1px 0 rgba(255, 252, 240, 0.7);
}
.recent__img {
  width: 266px;
  height: 108px;
  object-fit: cover;
  border-radius: 8px;
  flex: none;
  box-shadow:
    0 1px 2px rgba(96, 74, 40, 0.25),
    inset 0 0 0 1px rgba(120, 96, 56, 0.2);
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
  transform: translateX(2px);
}

@media (max-width: 900px) {
  .recent__grid {
    grid-template-columns: 1fr;
  }
}
</style>
