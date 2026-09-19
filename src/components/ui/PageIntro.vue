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
}
.intro__text {
  min-width: 0;
}
.intro__title {
  font-family: var(--font-display);
  font-size: 37px;
  font-weight: 600;
  line-height: 1.08;
  color: var(--ink);
}
.intro__sub {
  margin-top: 3px;
  font-size: 15.5px;
  color: #55482f;
}
.intro__actions {
  margin-left: auto;
  align-self: center;
  flex: none;
  display: flex;
  align-items: center;
  gap: 10px;
}
</style>
