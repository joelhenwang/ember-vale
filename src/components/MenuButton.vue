<script setup lang="ts">
import IconArrowRight from './icons/IconArrowRight.vue'

withDefaults(
  defineProps<{
    variant?: 'teal' | 'outline'
    size?: 'lg' | 'md'
    arrow?: 'plain' | 'circle'
  }>(),
  { variant: 'teal', size: 'md', arrow: 'plain' }
)
</script>

<template>
  <button class="mb" :class="[`mb--${variant}`, `mb--${size}`]" type="button">
    <span v-if="$slots.icon" class="mb__icon"><slot name="icon" /></span>
    <span class="mb__label"><slot /></span>
    <span class="mb__arrow" :class="{ 'mb__arrow--circle': arrow === 'circle' }">
      <IconArrowRight :size="arrow === 'circle' ? 14 : 17" />
    </span>
  </button>
</template>

<style scoped>
.mb {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  border-radius: 10px;
  font-family: var(--font-body);
  position: relative;
  transition:
    transform 0.12s ease,
    box-shadow 0.12s ease,
    filter 0.12s ease,
    background-color 0.12s ease,
    border-color 0.12s ease;
}
.mb:active {
  transform: translateY(1px);
}

.mb__icon {
  display: inline-flex;
  align-items: center;
  margin-left: 14px;
}
.mb__label {
  flex: 1;
  text-align: left;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.mb__arrow {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  margin-right: 14px;
  opacity: 0.9;
  transition: transform 0.15s ease;
}
.mb__arrow--circle {
  width: 27px;
  height: 27px;
  border: 1px solid currentColor;
  border-radius: 50%;
  opacity: 0.75;
}
.mb:hover .mb__arrow {
  transform: translateX(2px);
}

/* ——— deep teal primary ——— */
.mb--teal {
  color: var(--cream-on-teal);
  background:
    radial-gradient(140% 240% at 50% -60%, rgba(255, 245, 215, 0.14), transparent 60%),
    linear-gradient(180deg, var(--teal-hi) 0%, #175a5e 52%, #114c52 100%);
  border: 1px solid #0c3f46;
  box-shadow:
    inset 0 1px 0 rgba(255, 243, 214, 0.22),
    inset 0 -8px 14px -10px rgba(0, 0, 0, 0.45),
    0 1px 2px rgba(16, 46, 46, 0.3),
    0 6px 14px -8px rgba(16, 46, 46, 0.35);
  text-shadow: 0 1px 0 rgba(0, 0, 0, 0.25);
}
.mb--teal::after {
  content: '';
  position: absolute;
  inset: 2px;
  border-radius: 8px;
  border: 1px solid rgba(244, 236, 215, 0.28);
  pointer-events: none;
}
.mb--teal:hover {
  filter: brightness(1.07);
}

/* ——— parchment outline ——— */
.mb--outline {
  color: var(--ink);
  background: linear-gradient(180deg, #fdf8ea, #faf3e1);
  border: 1px solid #cfc0a0;
  box-shadow:
    inset 0 1px 0 rgba(255, 253, 245, 0.9),
    0 1px 1px rgba(120, 96, 56, 0.08);
}
.mb--outline .mb__arrow {
  color: var(--teal-ink);
}
.mb--outline .mb__icon {
  color: var(--gold);
}
.mb--outline:hover {
  background: linear-gradient(180deg, #fbf4e2, #f4ead2);
  border-color: #b9a577;
}

.mb--lg {
  height: 58px;
  font-size: 20.5px;
  font-weight: 500;
}
.mb--md {
  height: 54px;
  font-size: 17.5px;
  font-weight: 500;
}
</style>
