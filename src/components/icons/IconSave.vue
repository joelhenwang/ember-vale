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
      <path d="M5 4.8h11L19.2 8v11.2H5V4.8Z" />
      <path d="M8.6 4.8v4.6h6.6V4.8" />
      <path d="M8.8 19.2v-5.6h6.4v5.6" />
    </g>
  </svg>
</template>
