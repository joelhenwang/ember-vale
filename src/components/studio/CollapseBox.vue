<script setup lang="ts">
import { ref } from 'vue'
import IconChevronRight from '../icons/IconChevronRight.vue'

withDefaults(defineProps<{ title: string; open?: boolean }>(), { open: false })
const isOpen = ref(false)
</script>

<template>
  <div class="cb" :class="{ 'cb--open': isOpen }">
    <button type="button" class="cb__head" :aria-expanded="isOpen" @click="isOpen = !isOpen">
      <IconChevronRight :size="13" class="cb__chev" />
      {{ title }}
    </button>
    <div class="cb__wrap" :inert="!isOpen">
      <div class="cb__inner">
        <div class="cb__body">
          <slot />
        </div>
      </div>
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
  transition: transform 0.32s var(--ease-settle);
}
.cb--open .cb__chev {
  transform: rotate(90deg);
}
/* opens by growing its row, so the content below glides instead of jumping */
.cb__wrap {
  display: grid;
  grid-template-rows: 0fr;
  visibility: hidden;
  transition:
    grid-template-rows 0.3s var(--ease-io),
    visibility 0s linear 0.3s;
}
.cb--open .cb__wrap {
  grid-template-rows: 1fr;
  visibility: visible;
  transition: grid-template-rows 0.42s var(--ease-settle);
}
.cb__inner {
  min-height: 0;
  overflow: hidden;
}
.cb__body {
  padding: 2px 16px 15px;
  opacity: 0;
  transform: translateY(-6px);
  transition:
    opacity 0.2s var(--ease-in),
    transform 0.2s var(--ease-in);
}
.cb--open .cb__body {
  opacity: 1;
  transform: none;
  transition:
    opacity 0.32s var(--ease-out) 0.08s,
    transform 0.42s var(--ease-settle) 0.08s;
}
</style>
