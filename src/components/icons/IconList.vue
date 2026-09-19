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
      <path d="M8.6 6.6h11.2M8.6 12h11.2M8.6 17.4h11.2" />
      <path d="M4.3 6.6h.01M4.3 12h.01M4.3 17.4h.01" stroke-width="2.2" />
    </g>
  </svg>
</template>
