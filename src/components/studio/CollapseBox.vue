<script setup lang="ts">
import { ref } from 'vue'
import IconArrowRight from '../icons/IconArrowRight.vue'

withDefaults(defineProps<{ title: string; open?: boolean }>(), { open: false })
const isOpen = ref(false)
</script>

<template>
  <div class="cb" :class="{ 'cb--open': isOpen }">
    <button type="button" class="cb__head" :aria-expanded="isOpen" @click="isOpen = !isOpen">
      <IconArrowRight :size="13" class="cb__chev" />
      {{ title }}
    </button>
    <div v-show="isOpen" class="cb__body">
      <slot />
    </div>
  </div>
</template>

<style scoped>
.cb {
  border-radius: 10px;
  background: #f4ecd8;
  border: 1px solid #e6d9bb;
  overflow: hidden;
}
.cb--open {
  background: #f7f0df;
}
.cb__head {
  display: flex;
  align-items: center;
  gap: 11px;
  width: 100%;
  text-align: left;
  padding: 13px 16px;
  font-size: 16.5px;
  font-weight: 500;
  color: #3c3420;
  transition: color 0.14s ease;
}
.cb__head:hover {
  color: var(--teal-ink);
}
.cb__chev {
  color: #6c5f45;
  transition: transform 0.18s ease;
}
.cb--open .cb__chev {
  transform: rotate(90deg);
}
.cb__body {
  padding: 2px 16px 15px;
}
</style>
