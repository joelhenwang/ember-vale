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
      <path d="M8.6 6.2c0-1.6 1.4-2.6 3.4-2.6s3.4 1 3.4 2.6" />
      <rect x="4.4" y="6.2" width="15.2" height="12.2" rx="2.4" />
      <path d="M4.4 10.8h15.2" />
      <path d="M10.9 10.8h2.2v2.7h-2.2z" />
    </g>
  </svg>
</template>
