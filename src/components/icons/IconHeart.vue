<script setup lang="ts">
withDefaults(defineProps<{ size?: number | string }>(), { size: 18 })
</script>

<template>
  <svg :width="size" :height="size" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
    <g
      fill="none"
      stroke="currentColor"
      stroke-width="1.6"
      stroke-linecap="round"
      stroke-linejoin="round">
      <path
        d="M12 20.2C6.5 16.5 3.6 13 3.6 9.6a4.4 4.4 0 0 1 8.4-1.9 4.4 4.4 0 0 1 8.4 1.9c0 3.4-2.9 6.9-8.4 10.6Z" />
    </g>
  </svg>
</template>
