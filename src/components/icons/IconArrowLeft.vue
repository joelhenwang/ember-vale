<script setup lang="ts">
withDefaults(defineProps<{ size?: number | string }>(), { size: 20 })
</script>

<!-- IconArrowRight, facing back. -->
<template>
  <svg :width="size" :height="size" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
    <path
      fill="none"
      stroke="currentColor"
      stroke-width="2.1"
      stroke-linecap="round"
      stroke-linejoin="round"
      d="M20 12H4.8M10.6 5.6c-.9 3-3 5.4-6.1 6.4 3.1 1 5.2 3.4 6.1 6.4" />
  </svg>
</template>
