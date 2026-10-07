<script setup lang="ts">
withDefaults(defineProps<{ size?: number | string }>(), { size: 20 })
</script>

<template>
  <svg :width="size" :height="size" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
    <path
      fill="none"
      stroke="currentColor"
      stroke-width="1.8"
      stroke-linecap="round"
      stroke-linejoin="round"
      d="M9.5 5.5 15.5 12l-6 6.5" />
  </svg>
</template>
