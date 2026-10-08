<script setup lang="ts">
import { computed, type Component } from 'vue'
import IconArrowRight from './icons/IconArrowRight.vue'

const props = withDefaults(
  defineProps<{
    variant?: 'teal' | 'outline'
    size?: 'lg' | 'md' | 'sm'
    /** How the trailing arrow looks: bare, in a medallion, or left off. */
    arrow?: 'plain' | 'circle' | 'none'
    /** A leading icon (the #icon slot does the same). */
    icon?: Component
  }>(),
  { variant: 'teal', size: 'md', arrow: 'plain', icon: undefined }
)
/** Matches --i in the styles below. */
const arrowSize = computed(() => (props.arrow === 'circle' ? (props.size === 'sm' ? 14 : 16) : 18))
</script>

<template>
  <button class="mb" :class="[`mb--${variant}`, `mb--${size}`]" type="button">
    <span v-if="$slots.icon || icon" class="mb__icon">
      <slot name="icon"><component :is="icon" :size="size === 'sm' ? 16 : 19" /></slot>
    </span>
    <span class="mb__label"><slot /></span>
    <span
      v-if="arrow !== 'none'"
      class="mb__arrow"
      :class="{ 'mb__arrow--circle': arrow === 'circle' }"
      aria-hidden="true">
      <!-- two arrows: on hover the first flies out and the second takes its place -->
      <span class="mb__arrows">
        <IconArrowRight :size="arrowSize" />
        <IconArrowRight :size="arrowSize" />
      </span>
    </span>
  </button>
</template>

<style scoped>
.mb {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  padding: 0 18px;
  border-radius: 10px;
  font-family: var(--font-ui);
  letter-spacing: 0.01em;
  position: relative;
  overflow: hidden;
  isolation: isolate;
  transition:
    transform 0.16s var(--ease-out),
    box-shadow 0.2s var(--ease-out),
    filter 0.16s ease,
    background-color 0.16s ease,
    border-color 0.16s ease;
}
.mb:hover:not(:disabled) {
  transform: translateY(-1px);
}
.mb:active:not(:disabled) {
  transform: translateY(1px);
}
.mb:disabled {
  cursor: not-allowed;
  opacity: 0.55;
  filter: saturate(0.6);
}

.mb__icon {
  display: inline-flex;
  align-items: center;
  flex: none;
}
.mb__label {
  flex: 1;
  min-width: 0;
  text-align: left;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* trailing arrow ------------------------------------------------------------ */
/* Two arrows side by side, --i wide with --g between; the box shows one at
   a time. At rest the second shows; on hover the row slides so the first
   comes in from the left as the second flies out to the right. */
.mb__arrow {
  --w: 22px;
  --i: 18px;
  --g: 14px;
  position: relative;
  flex: none;
  display: inline-flex;
  align-items: center;
  width: var(--w);
  height: var(--w);
  padding-left: calc((var(--w) - var(--i)) / 2);
  overflow: hidden;
}
.mb__arrow--circle {
  --w: 34px;
  --i: 16px;
  border-radius: 50%;
}
.mb__arrows {
  display: flex;
  flex: none;
  gap: var(--g);
  transform: translateX(calc(-1 * (var(--i) + var(--g))));
  transition: transform 0.4s var(--ease-out);
}
.mb__arrows :deep(svg) {
  flex: none;
}
.mb:hover:not(:disabled) .mb__arrows {
  transform: translateX(0);
}

/* ——— deep teal primary ——— */
.mb--teal {
  color: var(--cream-on-teal);
  background:
    radial-gradient(140% 240% at 50% -60%, rgba(255, 245, 215, 0.16), transparent 60%),
    linear-gradient(180deg, var(--teal-hi) 0%, #175a5e 52%, #114c52 100%);
  border: 1px solid #0c3f46;
  box-shadow:
    inset 0 1px 0 rgba(255, 243, 214, 0.24),
    inset 0 -8px 14px -10px rgba(0, 0, 0, 0.45),
    0 1px 2px rgba(16, 46, 46, 0.3),
    0 8px 18px -8px rgba(16, 46, 46, 0.45);
  text-shadow: 0 1px 0 rgba(0, 0, 0, 0.25);
}
.mb--teal::after {
  content: '';
  position: absolute;
  inset: 2px;
  border-radius: 8px;
  border: 1px solid rgba(244, 236, 215, 0.26);
  pointer-events: none;
}
/* a sheen of light crosses the button on hover */
.mb--teal::before {
  content: '';
  position: absolute;
  inset: -2px auto -2px -60%;
  width: 45%;
  z-index: -1;
  background: linear-gradient(
    100deg,
    transparent,
    rgba(255, 236, 196, 0.22) 45%,
    rgba(255, 236, 196, 0.32) 50%,
    transparent
  );
  transform: skewX(-18deg);
  transition: left 0.6s var(--ease-out);
}
.mb--teal:hover:not(:disabled)::before {
  left: 120%;
}
.mb--teal:hover:not(:disabled) {
  filter: brightness(1.06);
  box-shadow:
    inset 0 1px 0 rgba(255, 243, 214, 0.24),
    inset 0 -8px 14px -10px rgba(0, 0, 0, 0.45),
    0 2px 3px rgba(16, 46, 46, 0.3),
    0 12px 24px -10px rgba(16, 46, 46, 0.55),
    0 0 0 3px var(--ember-glow);
}
.mb--teal .mb__arrow {
  color: #ffe2bf;
}
.mb--teal .mb__arrow--circle {
  color: var(--teal);
  background: radial-gradient(circle at 35% 30%, #fff6e3, #f0dcb4 70%, #e0c58f);
  box-shadow:
    0 1px 2px rgba(0, 0, 0, 0.3),
    inset 0 -1px 2px rgba(150, 110, 50, 0.35);
}
.mb--teal:hover:not(:disabled) .mb__arrow--circle {
  color: var(--ember);
}

/* ——— parchment outline ——— */
.mb--outline {
  color: var(--ink);
  background: linear-gradient(180deg, #fdf8ea, #f8efda);
  border: 1px solid #cdbd99;
  box-shadow:
    inset 0 1px 0 rgba(255, 253, 245, 0.9),
    0 1px 2px rgba(120, 96, 56, 0.12),
    0 6px 12px -8px rgba(120, 96, 56, 0.3);
}
.mb--outline .mb__arrow {
  color: var(--teal-ink);
}
.mb--outline .mb__arrow--circle {
  color: var(--cream-on-teal);
  background: linear-gradient(180deg, var(--teal-hi), var(--teal));
}
.mb--outline .mb__icon {
  color: var(--gold);
}
.mb--outline:hover:not(:disabled) {
  background: linear-gradient(180deg, #fcf5e3, #f4e9cf);
  border-color: #b9a06c;
  box-shadow:
    inset 0 1px 0 rgba(255, 253, 245, 0.9),
    0 2px 3px rgba(120, 96, 56, 0.14),
    0 10px 18px -10px rgba(120, 96, 56, 0.42);
}
.mb--outline:hover:not(:disabled) .mb__arrow {
  color: var(--ember);
}
.mb--outline:hover:not(:disabled) .mb__icon {
  color: var(--ember);
}

.mb--lg {
  height: 58px;
  padding: 0 20px;
  font-size: 20px;
  font-weight: 500;
}
.mb--md {
  height: 52px;
  font-size: 17.5px;
  font-weight: 500;
}
.mb--sm {
  height: 42px;
  padding: 0 14px;
  gap: 9px;
  font-size: 16px;
  font-weight: 500;
}
.mb--sm .mb__arrow--circle {
  --w: 28px;
  --i: 14px;
}
.mb--lg .mb__arrow--circle,
.mb--md .mb__arrow--circle {
  margin-right: -8px;
}

:root[data-motion='reduced'] .mb:hover:not(:disabled) .mb__arrows {
  transform: translateX(calc(-1 * (var(--i) + var(--g))));
}
@media (prefers-reduced-motion: reduce) {
  :root:not([data-motion='full']) .mb:hover:not(:disabled) .mb__arrows {
    transform: translateX(calc(-1 * (var(--i) + var(--g))));
  }
}
</style>
