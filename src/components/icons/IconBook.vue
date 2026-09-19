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
      <path
        d="M12 5.6C10 4.1 6.8 3.5 3 3.9v14.3c3.8-.4 7 .2 9 1.7 2-1.5 5.2-2.1 9-1.7V3.9c-3.8-.4-7 .2-9 1.7Z" />
      <path d="M12 5.6v14.3" />
    </g>
  </svg>
</template>
