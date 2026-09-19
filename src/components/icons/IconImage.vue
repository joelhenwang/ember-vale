<script setup lang="ts">
withDefaults(defineProps<{ size?: number | string }>(), { size: 15 })
</script>

<template>
  <svg :width="size" :height="size" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
    <g
      fill="none"
      stroke="currentColor"
      stroke-width="1.6"
      stroke-linecap="round"
      stroke-linejoin="round">
      <rect x="3.4" y="5.2" width="17.2" height="13.6" rx="2" />
      <circle cx="8.6" cy="9.6" r="1.5" />
      <path d="m4.6 16.4 4.6-4.4 3.2 3 3-2.7 4.1 4.1" />
    </g>
  </svg>
</template>
