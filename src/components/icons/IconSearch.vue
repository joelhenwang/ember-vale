<script setup lang="ts">
withDefaults(defineProps<{ size?: number | string }>(), { size: 16 })
</script>

<template>
  <svg :width="size" :height="size" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
    <g fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round">
      <circle cx="10.5" cy="10.5" r="6.6" />
      <path d="m15.4 15.4 4.4 4.4" />
    </g>
  </svg>
</template>
