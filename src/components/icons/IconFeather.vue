<script setup lang="ts">
withDefaults(defineProps<{ size?: number | string }>(), { size: 18 })
</script>

<template>
  <svg :width="size" :height="size" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
    <g
      fill="none"
      stroke="currentColor"
      stroke-width="1.5"
      stroke-linecap="round"
      stroke-linejoin="round">
      <path d="M4.5 19.5C8.5 15.5 14.8 7.8 20 4.2c.4 6-2 12.4-8.6 14.6-2.3.8-4.6.8-6.9.7Z" />
      <path d="M4.5 19.5C9 15.6 13.2 11.3 16.6 7" />
      <path d="M10.6 12.6 9 15.4M13.4 9.7l-1.3 2.7M15.9 7.2l-1.2 2.5" opacity=".7" />
    </g>
  </svg>
</template>
