<template>
  <!-- faint cartographer's compass rose, tucked into the card's top-right corner -->
  <svg class="rose" viewBox="0 0 200 200" aria-hidden="true" focusable="false">
    <g fill="none" stroke="currentColor" stroke-width="1.1">
      <circle cx="100" cy="100" r="92" />
      <circle cx="100" cy="100" r="78" opacity=".75" />
      <circle cx="100" cy="100" r="47" opacity=".7" />
      <circle cx="100" cy="100" r="10" opacity=".9" />
      <!-- degree ticks -->
      <g opacity=".85">
        <path
          v-for="i in 32"
          :key="i"
          :d="i % 8 === 1 ? 'M100 8 v 11' : 'M100 8 v 6'"
          :stroke-width="i % 8 === 1 ? 1.6 : 1"
          :transform="`rotate(${(i - 1) * (360 / 32)} 100 100)`" />
      </g>
      <!-- star -->
      <path
        class="rose__star"
        d="M100 12C104.5 60.5 139.5 95.5 188 100c-48.5 4.5-83.5 39.5-88 88-4.5-48.5-39.5-83.5-88-88 48.5-4.5 83.5-39.5 88-88Z"
        stroke-width="1.2" />
      <path
        d="M100 40C102.6 73.5 126.5 97.4 160 100c-33.5 2.6-57.4 26.5-60 60-2.6-33.5-26.5-57.4-60-60 33.5-2.6 57.4-26.5 60-60Z"
        transform="rotate(45 100 100)"
        opacity=".6" />
    </g>
  </svg>
</template>

<style scoped>
.rose {
  color: #b3945d;
}
.rose__star {
  fill: rgba(179, 148, 93, 0.16);
}
</style>
