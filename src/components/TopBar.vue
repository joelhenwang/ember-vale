<script setup lang="ts">
import { menuState } from '../game/state'
import { useGameImage } from '../game/images'
import IconEmblem from './icons/IconEmblem.vue'
import IconHelp from './icons/IconHelp.vue'
import HelpDialog from './HelpDialog.vue'
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

const nav = [
  { label: 'Home', to: '/' },
  { label: 'New Story', to: '/new-story' },
  { label: 'Stories', to: '/stories' },
  { label: 'Library', to: '/library' },
  { label: 'Settings', to: '/settings' }
] as const

const avatarUrl = useGameImage(menuState.player.avatarSlot)
const helpOpen = ref(false)

/* On a phone the nav is a strip that scrolls sideways: keep the current
   page's link in view. */
const route = useRoute()
const navEl = ref<HTMLElement | null>(null)

/* One ink line under the nav glides from page to page instead of each
   link drawing its own: the eye follows where you went. */
const ink = ref({ x: 0, w: 0, on: false })
const inkReady = ref(false)
function placeInk(): void {
  const active = navEl.value?.querySelector<HTMLElement>('.nav__item--active')
  if (!active) {
    ink.value = { ...ink.value, on: false }
    return
  }
  ink.value = { x: active.offsetLeft, w: active.offsetWidth, on: true }
}
watch(
  () => route.path,
  () =>
    nextTick(() => {
      placeInk()
      navEl.value
        ?.querySelector('.nav__item--active')
        ?.scrollIntoView({ inline: 'center', block: 'nearest', behavior: 'smooth' })
    }),
  { immediate: true }
)
let resizer: ResizeObserver | undefined
onMounted(() => {
  placeInk()
  // fonts settle after the first paint: place again, then let it glide
  void document.fonts?.ready.then(placeInk)
  requestAnimationFrame(() => (inkReady.value = true))
  if (typeof ResizeObserver !== 'undefined' && navEl.value) {
    resizer = new ResizeObserver(placeInk)
    resizer.observe(navEl.value)
  }
})
onBeforeUnmount(() => resizer?.disconnect())
</script>

<template>
  <header class="topbar">
    <div class="topbar__inner">
      <router-link class="brand" to="/">
        <IconEmblem :size="27" class="brand__mark" />
        <span class="brand__name">Ember Vale</span>
      </router-link>

      <nav ref="navEl" class="nav" aria-label="Main">
        <router-link
          v-for="item in nav"
          :key="item.label"
          :to="item.to"
          class="nav__item"
          :active-class="item.to === '/' ? '' : 'nav__item--active'"
          :exact-active-class="item.to === '/' ? 'nav__item--active' : ''">
          {{ item.label }}
        </router-link>
        <span
          class="nav__ink"
          :class="{ 'nav__ink--ready': inkReady }"
          :style="{
            transform: `translateX(${ink.x}px) scaleX(${ink.w / 100})`,
            opacity: ink.on ? 1 : 0
          }"
          aria-hidden="true"></span>
      </nav>

      <div class="topbar__right">
        <button
          class="helpbtn ev-press"
          type="button"
          aria-haspopup="dialog"
          @click="helpOpen = true">
          <IconHelp :size="19" class="help__icon" />
          <span>Help</span>
        </button>
        <span class="vr" aria-hidden="true"></span>
        <router-link
          class="profile"
          to="/settings"
          :title="`${menuState.player.name}: settings`"
          :aria-label="`${menuState.player.name}: settings`">
          <img class="profile__avatar" :src="avatarUrl" alt="" />
          <span class="profile__name">{{ menuState.player.name }}</span>
        </router-link>
      </div>
    </div>
    <HelpDialog :open="helpOpen" @close="helpOpen = false" />
  </header>
</template>

<style scoped>
.topbar {
  position: sticky;
  top: 0;
  z-index: 20;
  background: linear-gradient(180deg, #faf4e6, #f7f0df);
  border-bottom: 1px solid var(--hairline);
  box-shadow:
    0 1px 0 rgba(255, 252, 240, 0.8) inset,
    0 2px 8px -6px rgba(96, 74, 40, 0.25);
}
.topbar__inner {
  max-width: 1440px;
  margin: 0 auto;
  height: 62px;
  padding: 0 22px;
  display: flex;
  align-items: center;
  gap: 10px;
}

/* brand */
.brand {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  color: var(--ink);
  margin-right: 46px;
}
.brand__mark {
  color: #3a3122;
  /* the emblem holds a small ember that glows and dims, like a hearth */
  animation: brand-glow 4.8s var(--ease-sine) infinite;
  transition: transform 0.5s var(--ease-spring);
}
.brand:hover .brand__mark {
  transform: rotate(-12deg) scale(1.08);
}
@keyframes brand-glow {
  0%,
  100% {
    filter: drop-shadow(0 0 0 rgba(220, 122, 60, 0));
  }
  50% {
    filter: drop-shadow(0 0 5px rgba(220, 122, 60, 0.55));
  }
}
.brand__name {
  background: linear-gradient(100deg, var(--ink) 40%, #b8722f 50%, var(--ink) 60%) 0 0 / 300% 100%;
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
  background-position: 100% 0;
}
.brand:hover .brand__name {
  animation: brand-sheen 1.1s var(--ease-io);
}
@keyframes brand-sheen {
  from {
    background-position: 100% 0;
  }
  to {
    background-position: 0% 0;
  }
}
.brand__name {
  font-family: var(--font-display);
  font-size: 27px;
  font-weight: 600;
  letter-spacing: 0.02em;
}

/* nav */
.nav {
  position: relative;
  display: flex;
  align-items: center;
  gap: 40px;
  height: 100%;
}
.nav__item {
  position: relative;
  height: 100%;
  display: inline-flex;
  align-items: center;
  font-family: var(--font-ui);
  font-size: 18px;
  font-weight: 500;
  letter-spacing: 0.01em;
  color: #4c4130;
  transition: color 0.15s ease;
}
.nav__item:hover {
  color: var(--teal-ink);
}
.nav__item:active {
  transform: translateY(1px);
}
.nav__item--active {
  color: var(--teal-ink);
}
.nav__item::after {
  content: '';
  position: absolute;
  left: 0;
  right: 0;
  bottom: 12px;
  height: 2.5px;
  border-radius: 2px;
  background: linear-gradient(90deg, var(--teal-ink), var(--ember));
  transform: scaleX(0);
  transition: transform 0.32s var(--ease-out);
}
.nav__item:hover::after {
  transform: scaleX(0.35);
}
.nav__item--active::after {
  transform: scaleX(0);
}
/* the gliding ink: 100px wide, scaled to the active link */
.nav__ink {
  position: absolute;
  left: 0;
  bottom: 12px;
  width: 100px;
  height: 2.5px;
  border-radius: 2px;
  background: linear-gradient(90deg, var(--teal-ink), var(--ember));
  box-shadow: 0 0 8px rgba(220, 122, 60, 0.35);
  transform-origin: 0 50%;
  pointer-events: none;
}
.nav__ink--ready {
  transition:
    transform 0.52s var(--ease-settle),
    opacity 0.3s ease;
}

/* right cluster */
.topbar__right {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 16px;
}
.helpbtn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 17px;
  font-weight: 500;
  color: #4c4130;
  border-radius: 8px;
  padding: 4px 6px;
  transition: color 0.15s ease;
}
.helpbtn:hover {
  color: var(--teal-ink);
}
.help__icon {
  transition: transform 0.45s var(--ease-spring);
}
.helpbtn:hover .help__icon {
  transform: rotate(-14deg) scale(1.1);
}
.vr {
  width: 1px;
  height: 26px;
  background: #ded0b1;
}
.profile {
  display: inline-flex;
  align-items: center;
  gap: 9px;
  padding: 3px 6px 3px 3px;
  border-radius: 999px;
  transition: background-color 0.15s ease;
}
.profile:hover {
  background: rgba(196, 172, 126, 0.16);
}
.profile__avatar {
  width: 38px;
  height: 38px;
  border-radius: 50%;
  object-fit: cover;
  border: 1.5px solid #b9a06e;
  box-shadow:
    0 0 0 2px #fdf9ee,
    0 1px 3px rgba(96, 74, 40, 0.3);
  transition:
    transform 0.35s var(--ease-settle),
    box-shadow 0.25s ease;
}
.profile:hover .profile__avatar {
  transform: scale(1.07);
  box-shadow:
    0 0 0 2px #fdf9ee,
    0 0 0 4px rgba(220, 122, 60, 0.35),
    0 2px 6px rgba(96, 74, 40, 0.3);
}
.profile__name {
  font-family: var(--font-ui);
  font-size: 17px;
  font-weight: 500;
  color: var(--ink);
}
.profile__chev {
  color: #6c5f45;
}

/* Narrow screens: the nav becomes a swipeable strip; labels give way. */
@media (max-width: 820px) {
  .topbar__inner {
    padding: 0 12px;
    gap: 8px;
  }
  .nav {
    flex: 1;
    min-width: 0;
    overflow-x: auto;
    scrollbar-width: none;
    white-space: nowrap;
  }
  .nav::-webkit-scrollbar {
    display: none;
  }
  /* the strip fades at its edges: there is more to swipe to */
  .nav {
    gap: 22px;
    padding: 0 14px;
    -webkit-mask-image: linear-gradient(
      90deg,
      transparent,
      #000 14px,
      #000 calc(100% - 26px),
      transparent
    );
    mask-image: linear-gradient(90deg, transparent, #000 14px, #000 calc(100% - 26px), transparent);
  }
  .nav__item {
    font-size: 16.5px;
  }
  .helpbtn span,
  .profile__name,
  .profile__chev,
  .vr {
    display: none;
  }
}
@media (max-width: 560px) {
  .brand__name {
    display: none;
  }
}
</style>
