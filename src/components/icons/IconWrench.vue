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
      <path
        d="M14.7 6.3a4.5 4.5 0 0 0-6 6L3.8 17.2a1.8 1.8 0 0 0 2.5 2.5l4.9-4.9a4.5 4.5 0 0 0 6-6l-2.7 2.7-2.7-2.7 2.6-2.5Z" />
    </g>
  </svg>
</template>
