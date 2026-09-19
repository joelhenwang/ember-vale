<script setup lang="ts">
withDefaults(defineProps<{ size?: number | string }>(), { size: 14 })
</script>

<template>
  <svg :width="size" :height="size" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
    <path
      fill="none"
      stroke="currentColor"
      stroke-width="1.7"
      stroke-linecap="round"
      d="M6.5 6.5l11 11M17.5 6.5l-11 11" />
  </svg>
</template>
