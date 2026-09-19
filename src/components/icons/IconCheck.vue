<script setup lang="ts">
withDefaults(defineProps<{ size?: number | string }>(), { size: 14 })
</script>

<template>
  <svg :width="size" :height="size" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
    <path
      fill="none"
      stroke="currentColor"
      stroke-width="2.4"
      stroke-linecap="round"
      stroke-linejoin="round"
      d="m5 13.2 4.6 4.8L19 5.8" />
  </svg>
</template>
