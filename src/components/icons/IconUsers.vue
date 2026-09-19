<script setup lang="ts">
withDefaults(defineProps<{ size?: number | string }>(), { size: 22 })
</script>

<template>
  <svg :width="size" :height="size" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
    <g
      fill="none"
      stroke="currentColor"
      stroke-width="1.6"
      stroke-linecap="round"
      stroke-linejoin="round">
      <circle cx="9.1" cy="8.2" r="3.4" />
      <path d="M3.2 20.2c0-4 2.5-6.3 5.9-6.3s5.9 2.3 5.9 6.3" />
      <circle cx="17.4" cy="8.9" r="2.6" />
      <path d="M16.6 14.2c2.8.3 4.6 2.4 4.6 6" />
    </g>
  </svg>
</template>
