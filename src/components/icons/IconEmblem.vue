<script setup lang="ts">
withDefaults(defineProps<{ size?: number | string }>(), { size: 26 })
</script>

<template>
  <svg :width="size" :height="size" viewBox="0 0 32 32" aria-hidden="true" focusable="false">
    <path
      fill="currentColor"
      d="M16 1C17.2 10.5 21.5 14.8 31 16 21.5 17.2 17.2 21.5 16 31 14.8 21.5 10.5 17.2 1 16 10.5 14.8 14.8 10.5 16 1Z" />
    <path
      fill="currentColor"
      opacity=".9"
      transform="rotate(45 16 16)"
      d="M16 6.6C16.6 12.9 19.1 15.4 25.4 16 19.1 16.6 16.6 19.1 16 25.4 15.4 19.1 12.9 16.6 6.6 16 12.9 15.4 15.4 12.9 16 6.6Z" />
  </svg>
</template>
