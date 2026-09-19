<script setup lang="ts">
import { menuState } from '../game/state'
import { useGameImage } from '../game/images'
import IconEmblem from './icons/IconEmblem.vue'
import IconHelp from './icons/IconHelp.vue'
import IconChevronDown from './icons/IconChevronDown.vue'

const nav = [
  { label: 'Home', to: '/' },
  { label: 'New Story', to: '/new-story' },
  { label: 'Stories', to: '/stories' },
  { label: 'Library', to: '/library' },
  { label: 'Settings', to: '/settings' }
] as const

const avatarUrl = useGameImage(menuState.player.avatarSlot)
</script>

<template>
  <header class="topbar">
    <div class="topbar__inner">
      <router-link class="brand" to="/">
        <IconEmblem :size="27" class="brand__mark" />
        <span class="brand__name">Ember Vale</span>
      </router-link>

      <nav class="nav" aria-label="Main">
        <router-link
          v-for="item in nav"
          :key="item.label"
          :to="item.to"
          class="nav__item"
          :active-class="item.to === '/' ? '' : 'nav__item--active'"
          :exact-active-class="item.to === '/' ? 'nav__item--active' : ''">
          {{ item.label }}
        </router-link>
      </nav>

      <div class="topbar__right">
        <button class="help" type="button">
          <IconHelp :size="19" />
          <span>Help</span>
        </button>
        <span class="vr" aria-hidden="true"></span>
        <button class="profile" type="button" :aria-label="`Menu for ${menuState.player.name}`">
          <img class="profile__avatar" :src="avatarUrl" :alt="menuState.player.name" />
          <span class="profile__name">{{ menuState.player.name }}</span>
          <IconChevronDown :size="15" class="profile__chev" />
        </button>
      </div>
    </div>
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
}
.brand__name {
  font-family: var(--font-display);
  font-size: 27px;
  font-weight: 600;
  letter-spacing: 0.02em;
}

/* nav */
.nav {
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
  font-size: 17.5px;
  font-weight: 500;
  color: #4c4130;
  transition: color 0.15s ease;
}
.nav__item:hover {
  color: var(--teal-ink);
}
.nav__item--active {
  color: var(--teal-ink);
}
.nav__item--active::after {
  content: '';
  position: absolute;
  left: 1px;
  right: 1px;
  bottom: 12px;
  height: 2px;
  border-radius: 2px;
  background: var(--teal-ink);
}

/* right cluster */
.topbar__right {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 16px;
}
.help {
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
.help:hover {
  color: var(--teal-ink);
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
}
.profile__name {
  font-size: 18px;
  font-weight: 500;
  color: var(--ink);
}
.profile__chev {
  color: #6c5f45;
}
</style>
