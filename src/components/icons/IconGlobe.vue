<script setup lang="ts">
withDefaults(defineProps<{ size?: number | string }>(), { size: 22 })
</script>

<template>
  <svg :width="size" :height="size" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
    <g fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round">
      <circle cx="12" cy="12" r="9.3" />
      <path d="M2.8 12h18.4" />
      <path d="M12 2.7c2.6 2.5 2.6 16.1 0 18.6M12 2.7c-2.6 2.5-2.6 16.1 0 18.6" />
      <path
        d="M4.3 6.9c2.3 1.3 4.9 2 7.7 2s5.4-.7 7.7-2M4.3 17.1c2.3-1.3 4.9-2 7.7-2s5.4.7 7.7 2"
        opacity=".8" />
    </g>
  </svg>
</template>
