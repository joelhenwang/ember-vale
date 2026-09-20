<script setup lang="ts">
import { useRoute } from 'vue-router'
import TopBar from './components/TopBar.vue'

// Remount the room when the story id changes so an in-place A→B navigation
// never reuses A's captured lifecycle; other routes stay keyed by path so
// query changes (e.g. ?draft=) do not reboot their views.
const route = useRoute()
function roomKey(): string {
  const id = route.params.storyId
  if (typeof id === 'string' && id) return `story:${id}`
  return `path:${route.path}`
}
</script>

<template>
  <TopBar />
  <RouterView v-slot="{ Component }">
    <Transition name="page" mode="out-in">
      <component :is="Component" :key="roomKey()" />
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
