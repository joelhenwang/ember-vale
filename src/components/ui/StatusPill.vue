<!--
  StatusPill — tiny ● + text indicator (connection state in settings;
  any page may reuse). Tones mirror the app's semantic colors.
-->
<script setup lang="ts">
defineProps<{ tone: 'ok' | 'warn' | 'info' | 'fail'; label: string }>()
</script>

<template>
  <span class="spill" :class="`spill--${tone}`">
    <span class="spill__dot" aria-hidden="true"></span>{{ label }}
  </span>
</template>

<style scoped>
.spill {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 15px;
  font-weight: 500;
  white-space: nowrap;
}
.spill__dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  flex: none;
}
.spill--ok {
  color: #2e7d43;
}
.spill--ok .spill__dot {
  background: #2e7d43;
}
.spill--warn {
  color: #a8762a;
}
.spill--warn .spill__dot {
  background: #d9a83c;
}
.spill--info {
  color: var(--teal-ink);
}
.spill--info .spill__dot {
  background: var(--teal-ink);
  animation: spill-pulse 0.9s ease-in-out infinite alternate;
}
.spill--fail {
  color: #a84a2e;
}
.spill--fail .spill__dot {
  background: #b3542e;
}
@keyframes spill-pulse {
  from {
    opacity: 0.35;
  }
  to {
    opacity: 1;
  }
}
</style>
