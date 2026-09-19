<script setup lang="ts">
withDefaults(defineProps<{ size?: number | string }>(), { size: 14 })
</script>

<template>
  <svg :width="size" :height="size" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
    <g fill="currentColor">
      <circle cx="9.4" cy="6.6" r="1.3" />
      <circle cx="14.6" cy="6.6" r="1.3" />
      <circle cx="9.4" cy="12" r="1.3" />
      <circle cx="14.6" cy="12" r="1.3" />
      <circle cx="9.4" cy="17.4" r="1.3" />
      <circle cx="14.6" cy="17.4" r="1.3" />
    </g>
  </svg>
</template>
