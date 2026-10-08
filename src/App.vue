<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import TopBar from './components/TopBar.vue'

// Remount the room when the story id changes so an in-place A→B navigation
// never reuses A's captured lifecycle; other routes stay keyed by path so
// query changes (e.g. ?draft=) do not reboot their views.
const route = useRoute()
const router = useRouter()
function roomKey(): string {
  const id = route.params.storyId
  if (typeof id === 'string' && id) return `story:${id}`
  return `path:${route.path}`
}

/* The main pages stay alive between visits: coming back shows what was
   there at once and refreshes quietly (each view's onActivated). */
const KEPT = ['HomeView', 'StoriesView', 'LibraryView', 'SettingsView']

/* The main pages sit side by side in the nav's order, so moving between
   them slides like turning a carousel: rightwards pages come in from the
   right. Anything else (a studio, a story) fades in place. */
const ORDER = ['/', '/new-story', '/stories', '/library', '/settings']
const transition = ref('page')
router.beforeEach((to, from) => {
  const a = ORDER.indexOf(from.path)
  const b = ORDER.indexOf(to.path)
  transition.value = a >= 0 && b >= 0 && a !== b ? (b > a ? 'slide-next' : 'slide-prev') : 'page'
})
</script>

<template>
  <TopBar />
  <div class="stage">
    <RouterView v-slot="{ Component }">
      <Transition :name="transition">
        <KeepAlive :include="KEPT" :max="6">
          <component :is="Component" :key="roomKey()" />
        </KeepAlive>
      </Transition>
    </RouterView>
  </div>
</template>

<style scoped>
/* Both pages share the stage while one slides out and the next slides in. */
.stage {
  position: relative;
  overflow-x: clip;
}
.page-leave-active,
.slide-next-leave-active,
.slide-prev-leave-active {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  pointer-events: none;
}

/* gentle page fade — the manuscript turns, it doesn't snap */
.page-enter-active {
  transition:
    opacity 0.22s ease,
    transform 0.22s var(--ease-out);
}
.page-leave-active {
  transition: opacity 0.12s ease;
}
.page-enter-from {
  opacity: 0;
  transform: translateY(6px);
}
.page-leave-to {
  opacity: 0;
}

.slide-next-enter-active,
.slide-next-leave-active,
.slide-prev-enter-active,
.slide-prev-leave-active {
  transition:
    transform 0.46s var(--ease-out),
    opacity 0.46s var(--ease-out);
}
.slide-next-enter-from,
.slide-prev-leave-to {
  transform: translateX(100%);
  opacity: 0.3;
}
.slide-next-leave-to,
.slide-prev-enter-from {
  transform: translateX(-100%);
  opacity: 0.3;
}

:root[data-motion='reduced'] .slide-next-enter-from,
:root[data-motion='reduced'] .slide-prev-leave-to,
:root[data-motion='reduced'] .slide-next-leave-to,
:root[data-motion='reduced'] .slide-prev-enter-from {
  transform: none;
}
@media (prefers-reduced-motion: reduce) {
  :root:not([data-motion='full']) .slide-next-enter-from,
  :root:not([data-motion='full']) .slide-prev-leave-to,
  :root:not([data-motion='full']) .slide-next-leave-to,
  :root:not([data-motion='full']) .slide-prev-enter-from {
    transform: none;
  }
}
</style>
