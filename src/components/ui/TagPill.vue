<script setup lang="ts">
import type { Tag } from '../../game/model'

withDefaults(defineProps<{ tag: Tag; small?: boolean }>(), { small: false })
</script>

<template>
  <span class="tp" :class="[`tp--${tag.tone ?? 'tan'}`, { 'tp--sm': small }]">
    {{ tag.label }}
  </span>
</template>

<style scoped>
.tp {
  display: inline-flex;
  align-items: center;
  height: 22px;
  padding: 0 9px;
  border-radius: 6px;
  font-size: 12.5px;
  font-weight: 500;
  letter-spacing: 0.01em;
  border: 1px solid;
  white-space: nowrap;
}
.tp--sm {
  height: 19px;
  padding: 0 7px;
  font-size: 11.5px;
  border-radius: 5px;
}

.tp--tan {
  background: #f3e7cd;
  border-color: #ddc99c;
  color: #7a6234;
}
.tp--green {
  background: #e2edda;
  border-color: #c2d6b4;
  color: #4a723f;
}
.tp--blue {
  background: #e0eaf3;
  border-color: #c1d3e3;
  color: #3f648a;
}
.tp--purple {
  background: #eae3f2;
  border-color: #d3c5e4;
  color: #6a4e92;
}
.tp--rose {
  background: #f6e0d9;
  border-color: #e6c3b7;
  color: #98503b;
}
</style>
