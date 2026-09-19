<script setup lang="ts">
import TopBar from './components/TopBar.vue'
</script>

<template>
  <TopBar />
  <RouterView v-slot="{ Component }">
    <Transition name="page" mode="out-in">
      <component :is="Component" />
    </Transition>
  </RouterView>
</template>

<style scoped>
/* gentle page fade — the manuscript turns, it doesn't snap */
.page-enter-active,
.page-leave-active {
  transition:
    opacity 0.16s ease,
    transform 0.16s ease;
}
.page-enter-from,
.page-leave-to {
  opacity: 0;
  transform: translateY(4px);
}
</style>
