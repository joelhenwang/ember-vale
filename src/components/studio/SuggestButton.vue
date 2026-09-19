<script setup lang="ts">
import { ref } from 'vue'
import IconSparkle from '../icons/IconSparkle.vue'

const emit = defineEmits<{ suggest: [] }>()
const flash = ref(false)
let timer: ReturnType<typeof setTimeout> | undefined

function suggest(): void {
  emit('suggest')
  flash.value = true
  clearTimeout(timer)
  timer = setTimeout(() => (flash.value = false), 1500)
}
</script>

<template>
  <button type="button" class="sug" :class="{ 'sug--flash': flash }" @click="suggest">
    <IconSparkle :size="14" />
    {{ flash ? 'Details added' : 'Suggest details' }}
  </button>
</template>

<style scoped>
.sug {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  height: 38px;
  padding: 0 15px;
  border-radius: 9px;
  border: 1px solid #9dbfb4;
  background: linear-gradient(180deg, #f4faf3, #eef6ee);
  color: #215a52;
  font-size: 15px;
  font-weight: 500;
  box-shadow: inset 0 1px 0 #ffffffb0;
  transition:
    border-color 0.14s ease,
    background 0.14s ease,
    color 0.14s ease;
  white-space: nowrap;
}
.sug svg {
  color: var(--teal-ink);
}
.sug:hover {
  border-color: #6f9c8f;
  background: linear-gradient(180deg, #eef7ef, #e4f0e6);
}
.sug--flash {
  color: #1c4a44;
  border-color: #5f9488;
}
</style>
