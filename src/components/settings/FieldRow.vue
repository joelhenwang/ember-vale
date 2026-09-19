<!--
  FieldRow — one label+control row inside a ConnectionCard's config grid.
  The card body is a 4-column grid (label | control | label | control);
  this row renders with `display: contents` so its pieces become direct
  grid cells, letting two FieldRows share one visual line (Provider + Model)
  or one span the whole width (Endpoint). `span` controls how many control
  columns the field eats; the `after` slot takes the remaining cells.
-->
<script setup lang="ts">
defineProps<{ label: string; span?: 1 | 2 | 3 }>()
</script>

<template>
  <span class="frow__label">{{ label }}</span>
  <div class="frow__field" :data-span="span ?? 1">
    <slot />
  </div>
  <slot name="after" />
</template>

<style scoped>
.frow__label {
  font-size: 15.5px;
  font-weight: 600;
  color: var(--ink-2);
  white-space: nowrap;
}
.frow__field {
  min-width: 0;
}
.frow__field[data-span='2'] {
  grid-column: span 2;
}
.frow__field[data-span='3'] {
  grid-column: span 3;
}
</style>
