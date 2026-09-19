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
      <rect x="5.4" y="10.4" width="13.2" height="8.6" rx="2" />
      <path d="M8.2 10.4V7.9a3.8 3.8 0 0 1 7.6 0v2.5" />
    </g>
  </svg>
</template>
