<script setup lang="ts">
/**
 * Shows the framed part of a picture (src/game/framing.ts), filling the
 * box the parent sizes (circle, card) like object-fit: cover: a box of a
 * different shape widens the frame around its centre, never stretching
 * it. Without a frame the picture is simply covered, top-centred.
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { coverFrame, framedStyle, type Frame, type Size } from '../../game/framing'

const props = defineProps<{ src: string; frame?: Frame | null; alt?: string }>()

const box = ref<HTMLElement | null>(null)
const boxRatio = ref<number | null>(null)
const natural = ref<Size | null>(null)
let observer: ResizeObserver | null = null

onMounted(() => {
  if (!box.value || typeof ResizeObserver === 'undefined') return
  observer = new ResizeObserver(([entry]) => {
    const { width, height } = entry!.contentRect
    if (width > 0 && height > 0) boxRatio.value = width / height
  })
  observer.observe(box.value)
})
onBeforeUnmount(() => observer?.disconnect())

function loaded(event: Event): void {
  const img = event.target as HTMLImageElement
  if (img.naturalWidth && img.naturalHeight) {
    natural.value = { width: img.naturalWidth, height: img.naturalHeight }
  }
}

const style = computed(() => {
  if (!props.frame) return null
  const shown =
    natural.value && boxRatio.value
      ? coverFrame(props.frame, natural.value, boxRatio.value)
      : props.frame
  return framedStyle(shown)
})
</script>

<template>
  <span ref="box" class="framed">
    <img v-if="style" :src="src" :alt="alt ?? ''" :style="style" draggable="false" @load="loaded" />
    <img v-else class="framed__cover" :src="src" :alt="alt ?? ''" draggable="false" />
  </span>
</template>

<style scoped>
.framed {
  position: relative;
  display: block;
  width: 100%;
  height: 100%;
  overflow: hidden;
  border-radius: inherit;
}
.framed img {
  display: block;
}
.framed__cover {
  width: 100%;
  height: 100%;
  object-fit: cover;
  object-position: 50% 15%;
}
</style>
