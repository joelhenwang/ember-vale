<!--
  PageIntro — the standard "emblem + display title + quiet subtitle" header
  row, with an optional action slot on the right (Stories' New-story button,
  and anything future pages need). Host containers (band card, plain page)
  supply their own background; this component is just the row.
-->
<script setup lang="ts">
import IconEmblem from '../icons/IconEmblem.vue'

defineProps<{ title: string; sub?: string }>()
</script>

<template>
  <div class="intro">
    <IconEmblem :size="40" class="intro__emblem" />
    <div class="intro__text">
      <h1 class="intro__title">{{ title }}</h1>
      <p v-if="sub" class="intro__sub">{{ sub }}</p>
    </div>
    <div v-if="$slots.actions" class="intro__actions">
      <slot name="actions" />
    </div>
  </div>
</template>

<style scoped>
.intro {
  position: relative;
  isolation: isolate;
  display: flex;
  align-items: flex-start;
  gap: 14px;
}
/* a soft light behind the seal, faded by opacity so the loop stays cheap */
.intro::before {
  content: '';
  position: absolute;
  z-index: -1;
  left: -10px;
  top: -8px;
  width: 60px;
  height: 60px;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(220, 122, 60, 0.32), rgba(220, 122, 60, 0) 66%);
  pointer-events: none;
  opacity: 0;
  /* three breaths as the page opens, then rest (an endless loop keeps the
     compositor drawing every frame; perf-frontend-001) */
  animation: intro-glow 5s var(--ease-sine) 0.9s 3;
}
.intro__emblem {
  color: var(--gold);
  flex: none;
  margin-top: 2px;
  /* the seal turns into place, then glows softly like the brand mark */
  animation: intro-seal 0.9s var(--ease-settle) both;
}
@keyframes intro-seal {
  from {
    opacity: 0;
    transform: rotate(-120deg) scale(0.5);
  }
}
@keyframes intro-glow {
  0%,
  100% {
    opacity: 0;
  }
  50% {
    opacity: 1;
  }
}
.intro__text {
  min-width: 0;
}
.intro__title {
  animation: intro-title 0.8s var(--ease-settle) 0.08s both;
  font-family: var(--font-display);
  font-size: 37px;
  font-weight: 600;
  line-height: 1.08;
  color: var(--ink);
}
.intro__sub {
  animation: ev-fade 0.6s var(--ease-out) 0.3s both;
  margin-top: 3px;
  font-size: 15.5px;
  color: #55482f;
}
@keyframes intro-title {
  from {
    opacity: 0;
    transform: translateX(-14px);
  }
}
.intro__actions {
  animation: ev-fade 0.5s var(--ease-out) 0.35s both;
  margin-left: auto;
  align-self: center;
  flex: none;
  display: flex;
  align-items: center;
  gap: 10px;
}
</style>
