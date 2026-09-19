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
      <circle cx="6" cy="5.4" r="2.2" />
      <circle cx="6" cy="18.6" r="2.2" />
      <circle cx="18" cy="12" r="2.2" />
      <path d="M6 7.6v8.8" />
      <path d="M7.9 6.6c2.2 1.3 4.3 2.8 6.1 4.5M7.9 17.4c2.2-1.3 4.3-2.8 6.1-4.5" />
    </g>
  </svg>
</template>
