<template>
  <!-- distant ridge + pines + birds; a quiet horizon for the card's foot -->
  <svg
    class="ridge"
    viewBox="0 0 460 120"
    preserveAspectRatio="none"
    aria-hidden="true"
    focusable="false">
    <!-- far ridge -->
    <path
      d="M0 92 58 57l47 27 55-39 56 42 54-36 60 38 64-31 66 32v30H0Z"
      fill="#d8c49c"
      opacity=".5" />
    <!-- near ground -->
    <path d="M0 105c82-8 150 6 232-2s158 8 228 0v17H0Z" fill="#cbb386" opacity=".42" />
    <!-- pines -->
    <g fill="#ab9061" opacity=".55">
      <g v-for="(p, i) in pines" :key="i" :transform="`translate(${p[0]} ${p[1]}) scale(${p[2]})`">
        <path d="M0 0 -8 0 -4 -7 -7 -7 -3.2 -13 -6 -13 0 -22 6 -13 3.2 -13 7 -7 4 -7 8 0Z" />
        <path d="M-1.1 0h2.2v4h-2.2Z" />
      </g>
    </g>
    <!-- birds -->
    <g fill="none" stroke="#a08a63" stroke-width="1.4" stroke-linecap="round" opacity=".8">
      <path d="M148 66q4-4.5 8 0q4-4.5 8 0" transform="translate(0 -2)" />
      <path d="M176 55q3-3.4 6 0q3-3.4 6 0" />
    </g>
  </svg>
</template>

<script setup lang="ts">
/** [x, baseY, scale] */
const pines: Array<[number, number, number]> = [
  [26, 112, 1.15],
  [58, 115, 0.8],
  [96, 111, 1.35],
  [128, 116, 0.72],
  [352, 115, 0.8],
  [384, 112, 1.25],
  [414, 116, 0.78],
  [444, 112, 1.1]
]
</script>

<style scoped>
.ridge {
  width: 100%;
  height: 100%;
  display: block;
}
</style>
