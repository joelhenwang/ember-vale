<script setup lang="ts">
withDefaults(defineProps<{ size?: number | string }>(), { size: 16 })
</script>

<template>
  <svg :width="size" :height="size" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
    <g fill="currentColor">
      <path d="M8.2 5.7v12.6L19 12Z" stroke="currentColor" stroke-width="1.4" />
    </g>
  </svg>
</template>
