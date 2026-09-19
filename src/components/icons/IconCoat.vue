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
        d="M9 3.8 6.2 5.5 4.3 20.2h5l.6-8.1h.1l.6 8.1h5L18.6 5.5 15.8 3.8c-.5 1.6-1.9 2.5-3.4 2.5S9.5 5.4 9 3.8Z" />
      <path d="M12 6.3v14.2" />
    </g>
  </svg>
</template>
