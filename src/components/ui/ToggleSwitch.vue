<!--
  ToggleSwitch — an on/off switch with its label. A real checkbox with
  role="switch" underneath, so keyboard and screen readers work as usual.
-->
<script setup lang="ts">
defineProps<{ label: string; hint?: string; disabled?: boolean }>()
const model = defineModel<boolean>({ required: true })
</script>

<template>
  <label class="tsw" :class="{ 'tsw--off': disabled }">
    <input v-model="model" class="tsw__input" type="checkbox" role="switch" :disabled="disabled" />
    <span class="tsw__track" aria-hidden="true"><span class="tsw__thumb"></span></span>
    <span class="tsw__text">
      <span class="tsw__label">{{ label }}</span>
      <span v-if="hint" class="tsw__hint">{{ hint }}</span>
    </span>
  </label>
</template>

<style scoped>
.tsw {
  display: inline-flex;
  align-items: flex-start;
  gap: 12px;
  cursor: pointer;
}
.tsw--off {
  opacity: 0.55;
  cursor: default;
}
.tsw__input {
  position: absolute;
  opacity: 0;
  width: 1px;
  height: 1px;
}
.tsw__track {
  flex: none;
  width: 44px;
  height: 25px;
  margin-top: 1px;
  border-radius: 999px;
  background: #d8ccb0;
  border: 1px solid #c6b48e;
  position: relative;
  transition:
    background 0.25s ease,
    border-color 0.25s ease,
    box-shadow 0.25s ease;
}
.tsw:hover:not(.tsw--off) .tsw__track {
  border-color: #b39d6e;
}
.tsw__thumb {
  position: absolute;
  top: 2px;
  left: 2px;
  width: 19px;
  height: 19px;
  border-radius: 50%;
  background: #fffaf0;
  box-shadow: 0 1px 2px rgba(46, 39, 24, 0.3);
  transform-origin: 50% 50%;
  /* the thumb springs across and squashes a little while held */
  transition: transform 0.42s var(--ease-spring);
}
.tsw:active:not(.tsw--off) .tsw__thumb {
  transform: scaleX(1.18);
  transition-duration: 0.12s;
}
.tsw:active:not(.tsw--off) .tsw__input:checked + .tsw__track .tsw__thumb {
  transform: translateX(19px) scaleX(1.18);
}
.tsw__input:checked + .tsw__track {
  background: linear-gradient(180deg, #256e67, #14535a);
  border-color: #14535a;
  box-shadow: 0 0 0 3px rgba(46, 122, 108, 0.12);
}
.tsw__input:checked + .tsw__track .tsw__thumb {
  transform: translateX(19px);
}
.tsw__input:focus-visible + .tsw__track {
  outline: 2px solid var(--teal-ink);
  outline-offset: 2px;
}
.tsw__text {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.tsw__label {
  font-size: 15.5px;
  font-weight: 600;
  color: var(--ink-2);
}
.tsw__hint {
  font-size: 13.5px;
  color: var(--muted);
  line-height: 1.4;
}
</style>
