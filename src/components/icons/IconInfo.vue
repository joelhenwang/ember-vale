<script setup lang="ts">
withDefaults(defineProps<{ size?: number | string }>(), { size: 22 })
</script>

<template>
  <svg :width="size" :height="size" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
    <g fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round">
      <circle cx="12" cy="12" r="9.2" />
      <path d="M12 10.8v5.4" />
      <path d="M12 7.4h.01" />
    </g>
  </svg>
</template>
