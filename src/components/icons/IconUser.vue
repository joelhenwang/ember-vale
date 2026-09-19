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
      <circle cx="12" cy="8.1" r="3.7" />
      <path d="M4.9 19.6a7.1 7.1 0 0 1 14.2 0" />
    </g>
  </svg>
</template>
