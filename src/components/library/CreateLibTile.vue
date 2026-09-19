<script setup lang="ts">
import MountainRidge from '../decor/MountainRidge.vue'
import IconEmblem from '../icons/IconEmblem.vue'
import IconPlus from '../icons/IconPlus.vue'

withDefaults(
  defineProps<{
    title: string
    copy: string
    cta?: string
  }>(),
  { cta: undefined }
)
defineEmits<{ create: [] }>()
</script>

<template>
  <div class="create-tile">
    <MountainRidge class="create-tile__ridge" />
    <IconEmblem :size="cta ? 38 : 42" class="create-tile__mark" />
    <h3 class="create-tile__title">{{ title }}</h3>
    <p class="ev-quote create-tile__copy">{{ copy }}</p>
    <button v-if="cta" type="button" class="create-tile__btn" @click="$emit('create')">
      <IconPlus :size="13" /> {{ cta }}
    </button>
    <button v-else type="button" class="create-tile__hit" @click="$emit('create')">
      <span class="sr-only">Create</span>
    </button>
  </div>
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
    border-color 0.15s ease,
    background-color 0.15s ease;
}
.create-tile:hover {
  border-color: #a98d57;
  background: #f8efdb;
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
  font-size: 15.5px;
  line-height: 1.4;
  white-space: pre-line;
}
.create-tile__btn {
  position: relative;
  margin-top: 16px;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  height: 40px;
  padding: 0 22px;
  border-radius: 9px;
  background: linear-gradient(180deg, #23665f, #14514f);
  border: 1px solid #0f4147;
  box-shadow: inset 0 1px 0 rgba(255, 243, 214, 0.2);
  color: var(--cream-on-teal);
  font-size: 15.5px;
  font-weight: 500;
  transition: filter 0.14s ease;
}
.create-tile__btn:hover {
  filter: brightness(1.07);
}
.create-tile__hit {
  position: absolute;
  inset: 0;
  border-radius: inherit;
}
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
}
</style>
