<script setup lang="ts">
withDefaults(defineProps<{ size?: number | string }>(), { size: 24 })
</script>

<template>
  <svg :width="size" :height="size" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
    <g
      fill="none"
      stroke="currentColor"
      stroke-width="1.5"
      stroke-linecap="round"
      stroke-linejoin="round">
      <circle cx="12" cy="12" r="10.3" />
      <path d="M10.2 7.8 14.4 12l-4.2 4.2" />
    </g>
  </svg>
</template>
