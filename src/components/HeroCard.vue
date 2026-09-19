<script setup lang="ts">
import { menuState } from '../game/state'
import { useGameImage } from '../game/images'
import MenuButton from './MenuButton.vue'
import IconSparkle from './icons/IconSparkle.vue'
import IconInfo from './icons/IconInfo.vue'

const story = menuState.current!
const cover = useGameImage(story.imageSlot)
</script>

<template>
  <section class="hero ev-card" aria-label="Current story">
    <div class="hero__frame">
      <img class="hero__img" :src="cover" :alt="`${story.title} — scene illustration`" />

      <!-- parchment overlay, clipped with the signature diagonal notch -->
      <div class="hero__panel">
        <div class="hero__panel-in">
          <div class="hero__lead">
            <span class="ev-eyebrow">
              <IconSparkle :size="13" />
              Current Story
            </span>
            <h1 class="hero__title">
              {{ story.title }}
              <button class="hero__info" type="button" aria-label="Story details">
                <IconInfo :size="23" />
              </button>
            </h1>
            <p class="hero__meta">
              <span>Day {{ story.beat.day }}</span>
              <span class="ev-dot">•</span>
              <span>{{ story.beat.timeOfDay }}</span>
              <span class="ev-dot">•</span>
              <span>{{ story.beat.location }}</span>
            </p>
            <p class="hero__logline">{{ story.logline }}</p>
          </div>

          <div class="hero__action">
            <MenuButton class="hero__continue" size="md" arrow="circle">
              Continue Story
            </MenuButton>
            <div class="ev-divider hero__rule" aria-hidden="true"></div>
            <p class="ev-quote hero__epigraph">“{{ story.epigraph }}”</p>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.hero {
  height: 100%;
  padding: 10px;
  overflow: hidden;
}
.hero__frame {
  position: relative;
  height: 100%;
  min-height: 480px;
}
.hero__img {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
  border-radius: 9px;
  box-shadow:
    inset 0 0 0 1px rgba(120, 96, 56, 0.25),
    0 1px 2px rgba(96, 74, 40, 0.2);
}

/* overlay panel ------------------------------------------------------------ */
.hero__panel {
  --notch: polygon(0 0, calc(100% - 92px) 0, 100% 92px, 100% 100%, 0 100%);
  position: absolute;
  left: 22px;
  right: 8px;
  bottom: 10px;
  padding: 1px;
  border-radius: 13px;
  background: linear-gradient(180deg, #ddcba6, #cdb88e);
  clip-path: var(--notch);
  filter: drop-shadow(0 6px 14px rgba(74, 56, 26, 0.28));
}
.hero__panel-in {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 28px;
  padding: 15px 26px 18px;
  border-radius: 12px;
  background:
    radial-gradient(140% 180% at 8% -40%, rgba(255, 251, 238, 0.85), transparent 55%),
    linear-gradient(180deg, #fbf5e6, #f6eedb);
  clip-path: var(--notch);
}

/* left column ---------------------------------------------------------------- */
.hero__title {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 7px;
  font-family: var(--font-display);
  font-size: 44px;
  font-weight: 600;
  line-height: 1.04;
  letter-spacing: 0.005em;
  color: #26200f;
}
.hero__info {
  display: inline-flex;
  color: #6b5c40;
  opacity: 0.85;
  border-radius: 50%;
  transition:
    color 0.15s ease,
    opacity 0.15s ease;
}
.hero__info:hover {
  color: var(--teal-ink);
  opacity: 1;
}
.hero__meta {
  margin-top: 8px;
  font-size: 17.5px;
  font-weight: 500;
  color: #55482f;
}
.hero__logline {
  margin-top: 15px;
  max-width: 56ch;
  font-size: 17.5px;
  line-height: 1.5;
  color: var(--ink-2);
}

/* right column --------------------------------------------------------------- */
.hero__action {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding-top: 52px;
}
.hero__continue {
  width: 266px;
}
.hero__rule {
  width: 236px;
  margin-top: 21px;
}
.hero__epigraph {
  margin-top: 10px;
  font-size: 16.5px;
  white-space: nowrap;
}

@media (max-width: 1330px) {
  .hero__panel-in {
    grid-template-columns: minmax(0, 1fr);
  }
  .hero__action {
    align-items: flex-start;
    padding-top: 0;
  }
  .hero__continue {
    width: 232px;
  }
  .hero__rule,
  .hero__epigraph {
    display: none;
  }
}
</style>
