<script setup lang="ts">
withDefaults(defineProps<{ size?: number | string }>(), { size: 24 })
</script>

<template>
  <svg :width="size" :height="size" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
    <g
      fill="none"
      stroke="currentColor"
      stroke-width="1.6"
      stroke-linecap="round"
      stroke-linejoin="round">
      <circle cx="12" cy="12" r="10.3" />
      <path d="M7.2 12h9.2M13.2 8.4c.5 1.7 1.7 3 3.4 3.6-1.7.6-2.9 1.9-3.4 3.6" />
    </g>
  </svg>
</template>
