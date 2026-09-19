<!--
  SaveBar — the sticky-feel save footer shared by all editing pages
  (character studio, world studio, settings). Renders the snapshot-dirty
  status readout and an optional secondary "ghost" action; the host view
  supplies the leading buttons (e.g. Back) and the primary CTA via slots,
  since what "next" means differs per page (Continue vs Save settings).

  Visuals come from the global .studio__foot / .dirty / .ghost chrome in
  src/styles/studio.css — do not re-style those here.
-->
<script setup lang="ts">
import IconCheck from '../icons/IconCheck.vue'

defineProps<{
  dirty: boolean
  /** True briefly after a save, while no changes exist. */
  saved?: boolean
  /** Label for the ghost action ("Save draft", "Discard"); omit to hide. */
  secondaryLabel?: string
}>()
defineEmits<{ secondary: [] }>()
</script>

<template>
  <footer class="studio__foot ev-card">
    <slot name="start" />
    <p class="dirty">
      <template v-if="dirty"><span class="dirty__dot"></span> Unsaved changes</template>
      <template v-else-if="saved"><IconCheck :size="11" /> Saved just now</template>
      <template v-else><IconCheck :size="11" /> All changes saved</template>
    </p>
    <span class="studio__foot-spacer"></span>
    <button v-if="secondaryLabel" type="button" class="ghost" @click="$emit('secondary')">
      {{ secondaryLabel }}
    </button>
    <slot name="end" />
  </footer>
</template>
