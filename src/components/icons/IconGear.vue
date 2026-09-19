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
      <circle cx="12" cy="12" r="2.6" />
      <circle cx="12" cy="12" r="6.6" />
      <path
        d="M12 2.9v2.4M12 18.7v2.4M2.9 12h2.4M18.7 12h2.4M5.4 5.4l1.7 1.7M16.9 16.9l1.7 1.7M18.6 5.4l-1.7 1.7M7.1 16.9l-1.7 1.7" />
    </g>
  </svg>
</template>
