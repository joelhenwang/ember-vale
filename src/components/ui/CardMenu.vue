<!--
  CardMenu — the "…" button on a card and the little menu it opens. The
  card hands it the choices; picking one emits its key. It closes on a
  pick, a click elsewhere, or Escape, and never lets a click through to
  the card underneath.
-->
<script setup lang="ts">
import { onBeforeUnmount, ref, type Component } from 'vue'
import IconEllipsis from '../icons/IconEllipsis.vue'

export interface CardMenuItem {
  key: string
  label: string
  icon?: Component
  /** Shown in a warning tone, for things that put work away. */
  danger?: boolean
}

defineProps<{ items: CardMenuItem[]; label: string }>()
const emit = defineEmits<{ pick: [key: string] }>()

const open = ref(false)
const root = ref<HTMLElement | null>(null)

function onOutside(event: Event): void {
  if (root.value && !root.value.contains(event.target as Node)) close()
}
function onKey(event: KeyboardEvent): void {
  if (event.key === 'Escape') close()
}
function close(): void {
  open.value = false
  window.removeEventListener('pointerdown', onOutside, true)
  window.removeEventListener('keydown', onKey)
}
function toggle(): void {
  if (open.value) return close()
  open.value = true
  window.addEventListener('pointerdown', onOutside, true)
  window.addEventListener('keydown', onKey)
}
function pick(key: string): void {
  close()
  emit('pick', key)
}
onBeforeUnmount(close)
</script>

<template>
  <div ref="root" class="cmenu" @click.stop @keydown.enter.stop @keydown.space.stop>
    <button
      type="button"
      class="cmenu__dots"
      :class="{ 'cmenu__dots--open': open }"
      :aria-label="label"
      aria-haspopup="menu"
      :aria-expanded="open"
      @click="toggle">
      <IconEllipsis :size="15" class="cmenu__ell" />
    </button>
    <Transition name="cmenu">
      <ul v-if="open" class="cmenu__list" role="menu">
        <li v-for="(item, i) in items" :key="item.key" :style="{ '--i': i }">
          <button
            type="button"
            role="menuitem"
            :class="{ 'cmenu__item--danger': item.danger }"
            @click="pick(item.key)">
            <component :is="item.icon" v-if="item.icon" :size="15" />
            {{ item.label }}
          </button>
        </li>
      </ul>
    </Transition>
  </div>
</template>

<style scoped>
.cmenu {
  position: relative;
  flex: none;
}
.cmenu__dots {
  width: 30px;
  height: 28px;
  border-radius: 8px;
  border: 1px solid #dccfa9;
  background: #fcf7eaee;
  color: #6c5f45;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  transition:
    border-color 0.14s ease,
    color 0.14s ease,
    background-color 0.14s ease;
}
.cmenu__ell {
  transition: transform 0.4s var(--ease-spring);
}
.cmenu__dots--open .cmenu__ell {
  transform: rotate(90deg);
}
.cmenu__dots:active {
  transform: scale(0.92);
}
.cmenu__dots:hover,
.cmenu__dots--open {
  border-color: #b39c6d;
  color: var(--teal-ink);
  background: #fffaf0;
}
.cmenu__list {
  position: absolute;
  z-index: 40;
  top: calc(100% + 6px);
  right: 0;
  min-width: 200px;
  padding: 6px;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 2px;
  border-radius: 11px;
  border: 1px solid var(--line);
  background: linear-gradient(180deg, #fffaf0, #f8f0dc);
  box-shadow: var(--card-shadow-hover);
  transform-origin: top right;
}
.cmenu__list button {
  width: 100%;
  height: 36px;
  border-radius: 7px;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 11px;
  font-size: 15.5px;
  font-weight: 500;
  color: var(--ink-2);
  text-align: left;
  white-space: nowrap;
  transition:
    background-color 0.12s ease,
    color 0.12s ease;
}
.cmenu__list button svg {
  color: var(--gold);
  flex: none;
}
.cmenu__list button:hover {
  background: rgba(37, 110, 103, 0.1);
  color: var(--teal);
}
.cmenu__list button:hover svg {
  color: var(--teal);
}
.cmenu__list .cmenu__item--danger:hover,
.cmenu__list .cmenu__item--danger:hover svg {
  background: rgba(194, 97, 42, 0.1);
  color: var(--ember);
}

.cmenu-enter-active {
  transition:
    opacity 0.16s ease,
    transform 0.32s var(--ease-settle);
}
/* the choices slide in one after another */
.cmenu-enter-active li {
  animation: cmenu-item 0.32s var(--ease-settle) calc(0.03s * var(--i)) both;
}
@keyframes cmenu-item {
  from {
    opacity: 0;
    transform: translateX(8px);
  }
}
.cmenu__list button svg {
  transition: transform 0.3s var(--ease-spring);
}
.cmenu__list button:hover svg {
  transform: scale(1.15);
}
.cmenu-leave-active {
  transition:
    opacity 0.1s ease,
    transform 0.1s ease;
}
.cmenu-enter-from,
.cmenu-leave-to {
  opacity: 0;
  transform: scale(0.92) translateY(-4px);
}
</style>
