<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import TopBar from './components/TopBar.vue'
import EmberField from './components/decor/EmberField.vue'
import { moves } from './composables/useMotion'

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

/* Stepping into a story is a scene change, like a game loading a level:
   an iris of ember light opens on the story while the menu falls away.
   Leaving a story pulls back out. Moving within one story stays a fade. */
const IN_STORY = /^\/stories\/[^/]+\/(adventure|watch|play)$/
const curtain = ref(0)
let curtainTimer: ReturnType<typeof setTimeout> | undefined

router.beforeEach((to, from) => {
  const a = ORDER.indexOf(from.path)
  const b = ORDER.indexOf(to.path)
  const into = IN_STORY.test(to.path)
  const outOf = IN_STORY.test(from.path)
  if (a >= 0 && b >= 0 && a !== b) transition.value = b > a ? 'slide-next' : 'slide-prev'
  else if (into && !outOf && from.matched.length) transition.value = 'enter-story'
  else if (outOf && !into) transition.value = 'exit-story'
  else transition.value = 'page'
  if (transition.value === 'enter-story' && moves()) {
    clearTimeout(curtainTimer)
    curtain.value += 1
    // the iris lifts itself when it has opened; the timer is only a fallback
    curtainTimer = setTimeout(() => (curtain.value = 0), 4000)
  }
})
function curtainDone(event: AnimationEvent): void {
  if (event.animationName.includes('curtain-iris')) {
    clearTimeout(curtainTimer)
    curtain.value = 0
  }
}
</script>

<template>
  <TopBar />
  <div
    v-if="curtain"
    :key="curtain"
    class="curtain"
    aria-hidden="true"
    @animationend.self="curtainDone">
    <EmberField class="curtain__embers" :count="22" :rise="420" />
  </div>
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
.slide-prev-leave-active,
.enter-story-leave-active,
.exit-story-leave-active {
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
/* entering a story: the menu falls back and dims, the story comes forward */
.enter-story-leave-active {
  transition:
    opacity 0.4s var(--ease-in),
    transform 0.5s var(--ease-in),
    filter 0.4s ease;
}
.enter-story-leave-to {
  opacity: 0;
  transform: scale(0.94);
  filter: blur(3px) brightness(0.85);
}
.enter-story-enter-active {
  transition:
    opacity 0.6s var(--ease-out) 0.12s,
    transform 1.1s var(--ease-settle) 0.12s,
    filter 0.8s ease 0.12s;
}
.enter-story-enter-from {
  opacity: 0;
  transform: scale(1.06);
  filter: blur(4px);
}

/* leaving a story: the camera pulls back to the menus */
.exit-story-leave-active {
  transition:
    opacity 0.26s var(--ease-in),
    transform 0.32s var(--ease-in);
}
.exit-story-leave-to {
  opacity: 0;
  transform: scale(1.04);
}
.exit-story-enter-active {
  transition:
    opacity 0.4s var(--ease-out) 0.08s,
    transform 0.7s var(--ease-settle) 0.08s;
}
.exit-story-enter-from {
  opacity: 0;
  transform: scale(0.96);
}

/* the ember iris over the stage while a story loads in: the screen goes
   dark with drifting embers, then a widening circle opens on the story */
@property --iris {
  syntax: '<length>';
  inherits: false;
  initial-value: 0px;
}
.curtain {
  position: fixed;
  inset: 0;
  z-index: 19;
  overflow: hidden;
  pointer-events: none;
  background: radial-gradient(
    circle at 50% 46%,
    rgba(120, 62, 22, 0.94),
    rgba(22, 13, 6, 0.98) 62%
  );
  -webkit-mask-image: radial-gradient(
    circle at 50% 46%,
    transparent var(--iris),
    #000 calc(var(--iris) + 9vmax)
  );
  mask-image: radial-gradient(
    circle at 50% 46%,
    transparent var(--iris),
    #000 calc(var(--iris) + 9vmax)
  );
  animation:
    curtain-in 0.2s var(--ease-out) both,
    curtain-iris 1.15s var(--ease-io) 0.22s both;
}
@keyframes curtain-in {
  from {
    opacity: 0;
  }
}
@keyframes curtain-iris {
  from {
    --iris: 0px;
  }
  to {
    --iris: 120vmax;
  }
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
