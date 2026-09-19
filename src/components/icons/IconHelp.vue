<script setup lang="ts">
withDefaults(defineProps<{ size?: number | string }>(), { size: 19 })
</script>

<template>
  <svg :width="size" :height="size" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
    <g
      fill="none"
      stroke="currentColor"
      stroke-width="1.6"
      stroke-linecap="round"
      stroke-linejoin="round">
      <circle cx="12" cy="12" r="9.3" />
      <path d="M9.5 9.3c.2-1.7 1.5-2.9 3-2.9 1.7 0 3 1.2 3 2.8 0 2.2-2.9 2.5-2.9 4.6" />
      <path d="M12.6 16.9h.01" />
    </g>
  </svg>
</template>
