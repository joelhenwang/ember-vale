<script setup lang="ts">
withDefaults(defineProps<{ size?: number | string }>(), { size: 14 })
</script>

<template>
  <svg :width="size" :height="size" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
    <g
      fill="none"
      stroke="currentColor"
      stroke-width="1.6"
      stroke-linecap="round"
      stroke-linejoin="round">
      <path d="M9.2 4.6H4.6v4.6M14.8 4.6h4.6v4.6M9.2 19.4H4.6v-4.6M14.8 19.4h4.6v-4.6" />
    </g>
  </svg>
</template>
