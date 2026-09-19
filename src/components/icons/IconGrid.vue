<script setup lang="ts">
withDefaults(defineProps<{ size?: number | string }>(), { size: 16 })
</script>

<template>
  <svg :width="size" :height="size" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
    <g
      fill="none"
      stroke="currentColor"
      stroke-width="1.6"
      stroke-linecap="round"
      stroke-linejoin="round">
      <rect x="4.3" y="4.3" width="6.6" height="6.6" rx="1.7" />
      <rect x="13.1" y="4.3" width="6.6" height="6.6" rx="1.7" />
      <rect x="4.3" y="13.1" width="6.6" height="6.6" rx="1.7" />
      <rect x="13.1" y="13.1" width="6.6" height="6.6" rx="1.7" />
    </g>
  </svg>
</template>
