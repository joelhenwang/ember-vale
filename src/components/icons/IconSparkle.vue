<script setup lang="ts">
withDefaults(defineProps<{ size?: number | string }>(), { size: 16 })
</script>

<template>
  <svg :width="size" :height="size" viewBox="0 0 32 32" aria-hidden="true" focusable="false">
    <path
      fill="currentColor"
      d="M16 1C17.2 10.5 21.5 14.8 31 16 21.5 17.2 17.2 21.5 16 31 14.8 21.5 10.5 17.2 1 16 10.5 14.8 14.8 10.5 16 1Z" />
  </svg>
</template>
