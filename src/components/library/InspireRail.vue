<script setup lang="ts">
import { useRouter } from 'vue-router'
import CompassRose from '../decor/CompassRose.vue'
import BooksIvy from '../decor/BooksIvy.vue'
import MountainRidge from '../decor/MountainRidge.vue'
import IconSparkle from '../icons/IconSparkle.vue'

withDefaults(
  defineProps<{
    title: string
    copy: string
    quote: string
  }>(),
  {}
)
const router = useRouter()
</script>

<template>
  <aside class="rail ev-card" aria-label="Ideas">
    <CompassRose class="rail__rose" />
    <BooksIvy class="rail__books" />
    <MountainRidge class="rail__ridge" />

    <div class="rail__inner">
      <p class="ev-quote rail__note"><span>Ideas today.</span><span>Brighter tomorrows.</span></p>

      <h2 class="rail__title">{{ title }}</h2>
      <div class="ev-divider rail__rule" aria-hidden="true"><IconSparkle :size="12" /></div>
      <p class="rail__copy">{{ copy }}</p>

      <button type="button" class="rail__cta" @click="router.push('/new-story')">
        Start a new story <span aria-hidden="true">→</span>
      </button>

      <p class="ev-quote rail__quote">{{ quote }}</p>
      <IconSparkle :size="11" class="rail__spark" />
    </div>
  </aside>
</template>

<style scoped>
.rail {
  position: relative;
  overflow: hidden;
  padding: 20px 24px 18px;
}
.rail__rose {
  position: absolute;
  top: -26px;
  left: -24px;
  width: 132px;
  opacity: 0.5;
  pointer-events: none;
}
.rail__books {
  position: absolute;
  top: 34px;
  right: -8px;
  width: 168px;
  pointer-events: none;
}
.rail__ridge {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  height: 168px;
  opacity: 0.75;
  pointer-events: none;
}

.rail__inner {
  position: relative;
  z-index: 1;
  height: 100%;
  display: flex;
  flex-direction: column;
}
.rail__note {
  margin-left: auto;
  text-align: right;
  font-size: 14.5px;
  line-height: 1.45;
  color: #8d7c5f;
}
.rail__note span {
  display: block;
}
.rail__title {
  margin-top: 44px;
  font-family: var(--font-display);
  font-size: 31px;
  font-weight: 600;
  line-height: 1.08;
  color: #26200f;
}
.rail__rule {
  margin: 13px 0 15px;
  color: var(--gold);
}
.rail__copy {
  font-size: 15.5px;
  line-height: 1.5;
  color: var(--ink-2);
}
.rail__cta {
  margin-top: 24px;
  height: 42px;
  border-radius: 9px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  background: linear-gradient(180deg, #23665f, #14514f);
  border: 1px solid #0f4147;
  box-shadow:
    inset 0 1px 0 rgba(255, 243, 214, 0.2),
    0 1px 2px rgba(16, 46, 46, 0.3);
  color: var(--cream-on-teal);
  font-size: 16.5px;
  font-weight: 500;
  transition:
    filter 0.14s ease,
    transform 0.12s ease;
}
.rail__cta:hover {
  filter: brightness(1.07);
}
.rail__cta:active {
  transform: translateY(1px);
}
.rail__cta span {
  font-size: 15px;
}
.rail__quote {
  margin: auto auto 2px;
  padding-top: 20px;
  text-align: center;
  font-size: 15px;
  line-height: 1.45;
  white-space: pre-line;
}
.rail__spark {
  align-self: center;
  color: var(--gold-soft);
}
</style>
