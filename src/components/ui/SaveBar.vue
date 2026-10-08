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
  <footer class="studio__foot ev-card savebar">
    <slot name="start" />
    <Transition name="ev-swap" mode="out-in">
      <p v-if="dirty" key="dirty" class="dirty">
        <span class="dirty__dot ev-breathe"></span> Unsaved changes
      </p>
      <p v-else-if="saved" key="saved" class="dirty dirty--saved">
        <IconCheck :size="11" class="savebar__tick" /> Saved just now
      </p>
      <p v-else key="clean" class="dirty"><IconCheck :size="11" /> All changes saved</p>
    </Transition>
    <span class="studio__foot-spacer"></span>
    <button v-if="secondaryLabel" type="button" class="ghost" @click="$emit('secondary')">
      {{ secondaryLabel }}
    </button>
    <slot name="end" />
  </footer>
</template>

<style scoped>
/* the bar rises from the bottom edge when the page opens */
.savebar {
  animation: savebar-rise 0.6s var(--ease-settle) 0.15s both;
}
@keyframes savebar-rise {
  from {
    opacity: 0;
    transform: translateY(24px);
  }
}
.dirty__dot {
  --ev-breathe-color: rgba(214, 112, 48, 0.45);
}
/* a fresh save: the tick pops in */
.savebar__tick {
  animation: ev-pop-in 0.45s var(--ease-spring) both;
}
</style>
