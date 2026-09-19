<script setup lang="ts">
withDefaults(defineProps<{ size?: number | string }>(), { size: 16 })
</script>

<template>
  <svg :width="size" :height="size" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
    <g fill="currentColor">
      <circle cx="12" cy="5.6" r="1.35" />
      <circle cx="12" cy="12" r="1.35" />
      <circle cx="12" cy="18.4" r="1.35" />
    </g>
  </svg>
</template>
