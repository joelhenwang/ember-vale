<script setup lang="ts">
withDefaults(defineProps<{ size?: number | string }>(), { size: 14 })
</script>

<template>
  <svg :width="size" :height="size" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
    <path
      fill="none"
      stroke="currentColor"
      stroke-width="1.8"
      stroke-linecap="round"
      stroke-linejoin="round"
      d="M14.5 5.5 8.5 12l6 6.5" />
  </svg>
</template>
