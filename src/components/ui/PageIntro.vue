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
  display: flex;
  align-items: flex-start;
  gap: 14px;
}
.intro__emblem {
  color: var(--gold);
  flex: none;
  margin-top: 2px;
  /* the seal turns into place, then glows softly like the brand mark */
  animation:
    intro-seal 0.9s var(--ease-settle) both,
    intro-glow 5s var(--ease-sine) 0.9s infinite;
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
    filter: drop-shadow(0 0 0 rgba(220, 122, 60, 0));
  }
  50% {
    filter: drop-shadow(0 0 6px rgba(220, 122, 60, 0.45));
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
