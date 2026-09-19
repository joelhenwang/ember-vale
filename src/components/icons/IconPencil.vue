<script setup lang="ts">
withDefaults(defineProps<{ size?: number | string }>(), { size: 14 })
</script>

<template>
  <svg :width="size" :height="size" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
    <g
      fill="none"
      stroke="currentColor"
      stroke-width="1.6"
      stroke-linecap="round"
      stroke-linejoin="round">
      <path d="m4.6 19.4 1.1-4.3L15.7 5c.9-.9 2.5-.9 3.4 0s.9 2.5 0 3.4L9.1 18.4l-4.5 1Z" />
      <path d="m13.9 6.7 3.4 3.4" />
    </g>
  </svg>
</template>
