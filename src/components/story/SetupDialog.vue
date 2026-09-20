<script setup lang="ts">
import type { StorySetupView } from '../../../content/clients/worldsim'

defineProps<{ setup: StorySetupView | null; open: boolean }>()
defineEmits<{ close: [] }>()

function pretty(value: unknown): string {
  return JSON.stringify(value, null, 2)
}
</script>

<template>
  <div v-if="open" class="setup" role="dialog" aria-modal="true" aria-label="Initial configuration">
    <div class="setup__card">
      <header class="setup__head">
        <h2 class="setup__title">Initial configuration</h2>
        <button type="button" class="setup__close" @click="$emit('close')">Close</button>
      </header>
      <p class="setup__note">
        Frozen when the story was created — it never changes, even as the story moves on.
      </p>
      <dl v-if="setup" class="setup__meta">
        <div><dt>Provenance</dt><dd>{{ setup.provenance }}</dd></div>
        <div><dt>Captured</dt><dd>{{ setup.created_at }}</dd></div>
        <div>
          <dt>Content hash</dt>
          <dd><code>{{ setup.content_hash }}</code></dd>
        </div>
      </dl>
      <pre v-if="setup" class="setup__json">{{ pretty(setup.payload) }}</pre>
      <p v-else class="setup__note">No setup recorded.</p>
    </div>
  </div>
</template>

<style scoped>
.setup {
  position: fixed;
  inset: 0;
  background: rgba(43, 36, 22, 0.45);
  display: grid;
  place-items: center;
  padding: 16px;
  z-index: 40;
}
.setup__card {
  max-width: 640px;
  width: 100%;
  max-height: 80vh;
  overflow: auto;
  background: #fbf6e9;
  border: 1px solid var(--line);
  border-radius: 14px;
  padding: 18px 20px;
}
.setup__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.setup__title {
  margin: 0;
  font-family: 'Cormorant Garamond', Georgia, serif;
  font-size: 24px;
}
.setup__close {
  font: inherit;
  background: none;
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 6px 12px;
  cursor: pointer;
}
.setup__note {
  color: #6b5d43;
  font-size: 14px;
}
.setup__meta {
  display: grid;
  gap: 6px;
  margin: 12px 0 0;
}
.setup__meta > div {
  display: grid;
  grid-template-columns: 130px 1fr;
  gap: 8px;
}
.setup__meta dt {
  font-weight: 600;
  color: #6b5d43;
}
.setup__meta dd {
  margin: 0;
  overflow-wrap: anywhere;
}
.setup__json {
  margin: 12px 0 0;
  padding: 12px;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: #fffdf6;
  font-size: 12.5px;
  overflow: auto;
}
</style>
