<!--
  CreateLibTile — the dashed "create one" tile at the end of a library
  shelf. The whole tile is the button, on every shelf alike.
-->
<script setup lang="ts">
import MountainRidge from '../decor/MountainRidge.vue'
import IconEmblem from '../icons/IconEmblem.vue'

defineProps<{ title: string; copy: string; soon?: boolean }>()
defineEmits<{ create: [] }>()
</script>

<template>
  <button
    type="button"
    class="create-tile"
    :class="{ 'create-tile--soon': soon }"
    :disabled="soon"
    @click="$emit('create')">
    <MountainRidge class="create-tile__ridge" />
    <IconEmblem :size="42" class="create-tile__mark" />
    <span class="create-tile__title">{{ title }}</span>
    <span class="ev-quote create-tile__copy">{{ copy }}</span>
    <span v-if="soon" class="create-tile__soon">Coming soon</span>
  </button>
</template>

<style scoped>
.create-tile {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: 26px 22px 34px;
  border: 1.5px dashed #c8b184;
  border-radius: var(--radius-card);
  background: #faf3e2;
  min-height: 200px;
  overflow: hidden;
  transition:
    border-color 0.2s ease,
    background-color 0.2s ease,
    transform 0.22s var(--ease-out),
    box-shadow 0.22s var(--ease-out);
}
.create-tile--soon {
  cursor: default;
  opacity: 0.7;
}
.create-tile__soon {
  position: relative;
  margin-top: 10px;
  padding: 3px 10px;
  border-radius: 999px;
  background: #ece1c6;
  font-family: var(--font-ui);
  font-size: 13px;
  font-weight: 700;
  color: #7a6a49;
}
.create-tile:not(.create-tile--soon):hover {
  border-color: var(--ember);
  border-style: solid;
  background: #fbf1dc;
  transform: translateY(-3px);
  box-shadow: var(--card-shadow-hover);
}
.create-tile__ridge {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  height: 118px;
  opacity: 0.85;
  pointer-events: none;
}
.create-tile__mark {
  position: relative;
  color: #b08d3f;
  transition:
    color 0.2s ease,
    transform 0.5s var(--ease-spring);
}
.create-tile:not(.create-tile--soon):hover .create-tile__mark {
  color: var(--ember);
  transform: rotate(90deg) scale(1.12);
}
.create-tile__title {
  position: relative;
  margin-top: 12px;
  font-family: var(--font-display);
  font-size: 27px;
  font-weight: 600;
  line-height: 1.1;
  color: #26200f;
}
.create-tile__copy {
  position: relative;
  margin-top: 6px;
  font-family: var(--font-body);
  font-size: 15.5px;
  line-height: 1.4;
  white-space: pre-line;
}
</style>
