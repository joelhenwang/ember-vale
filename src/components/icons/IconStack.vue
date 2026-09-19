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
      <path d="M12 3.1 21 8l-9 4.9L3 8l9-4.9Z" />
      <path d="m4.6 11.7-1.6.9 9 4.9 9-4.9-1.6-.9" />
      <path d="m4.6 15.4-1.6.9 9 4.9 9-4.9-1.6-.9" />
    </g>
  </svg>
</template>
