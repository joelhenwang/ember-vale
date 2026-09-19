<!--
  ConnectionCard — one "model provider" panel of the Settings page:
  icon + title + live connection status, an explanatory caption, and a
  config grid supplied by the host through the default slot (laid out as
  four-column rows via FieldRow's display:contents trick).

  Both the story-generation and image-generation cards are this component;
  per-provider extras (last-checked notes, capability panel) live in the
  slot content rather than props, so the card stays presentation-only.
-->
<script setup lang="ts">
import { computed } from 'vue'
import type { Component } from 'vue'
import StatusPill from '../ui/StatusPill.vue'
import type { ConnStatus } from '../../game/settings'

const props = defineProps<{
  icon: Component
  title: string
  caption: string
  status: ConnStatus
}>()

const STATUS = {
  reachable: { tone: 'ok', label: 'Endpoint reachable' },
  unreachable: { tone: 'fail', label: 'Endpoint unreachable' },
  testing: { tone: 'info', label: 'Checking…' },
  untested: { tone: 'warn', label: 'Not tested' }
} as const

const pill = computed(() => STATUS[props.status])
</script>

<template>
  <section class="conn ev-card">
    <header class="conn__head">
      <span class="conn__icon"><component :is="icon" :size="21" /></span>
      <h3 class="conn__title">{{ title }}</h3>
      <StatusPill :tone="pill.tone" :label="pill.label" />
    </header>
    <p class="conn__caption">{{ caption }}</p>
    <div class="conn__body">
      <slot />
    </div>
  </section>
</template>

<style scoped>
.conn {
  padding: 18px 22px 22px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.conn__head {
  display: flex;
  align-items: center;
  gap: 13px;
}
.conn__icon {
  width: 40px;
  height: 40px;
  flex: none;
  border-radius: 10px;
  border: 1px solid #cdbb93;
  background: #fbf5e6;
  color: var(--ink);
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
.conn__title {
  font-family: var(--font-display);
  font-size: 23px;
  font-weight: 600;
  color: var(--ink);
  margin-right: 4px;
}
.conn__caption {
  font-size: 14.5px;
  line-height: 1.45;
  color: var(--muted);
  margin-top: -8px;
}
.conn__body {
  display: grid;
  grid-template-columns: minmax(120px, auto) minmax(0, 1fr) minmax(120px, auto) minmax(0, 1fr);
  column-gap: 26px;
  row-gap: 16px;
  align-items: center;
}
</style>
