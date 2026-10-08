<!--
  MapPreview — a world's saved map in the studio: its picture, roads and
  places, read-only. Drawing happens on the map page; without a map yet
  the slot (a stock picture) shows instead.
-->
<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { getPreset, libraryAssetUrl } from '../../api/worldsim'
import { boardFromPreset, liveRoads, roadLine, type Board } from '../../game/worldMap'

const props = defineProps<{ presetId: string; revision?: number | null }>()

const board = ref<Board | null>(null)

watch(
  () => [props.presetId, props.revision] as const,
  async ([id]) => {
    board.value = null
    if (!id || id === 'new') return
    try {
      board.value = boardFromPreset(await getPreset(id, undefined))
    } catch {
      board.value = null // the stock picture stays
    }
  },
  { immediate: true }
)

const COLORS: Record<string, string> = {
  road: '#c0392b',
  path: '#b7791f',
  sea: '#1f6fb2',
  river: '#2b8a9e',
  bridge: '#7d5a3c',
  pass: '#6b4f9e'
}
const lines = computed(() =>
  board.value
    ? liveRoads(board.value).map((road) => ({
        by: road.by,
        points: roadLine(board.value!, road)
          .map(([x, y]) => `${x},${y}`)
          .join(' ')
      }))
    : []
)
</script>

<template>
  <div
    v-if="board"
    class="mapprev"
    :style="{ aspectRatio: `${board.width} / ${board.height}` }"
    role="img"
    :aria-label="`Map with ${board.places.length} places and ${lines.length} roads`">
    <img :src="libraryAssetUrl(board.assetId)" alt="" draggable="false" />
    <svg viewBox="0 0 1000 1000" preserveAspectRatio="none" aria-hidden="true">
      <polyline
        v-for="(line, i) in lines"
        :key="i"
        :points="line.points"
        :stroke="COLORS[line.by] ?? COLORS['road']"
        :stroke-dasharray="line.by === 'sea' ? '6 5' : undefined"
        fill="none"
        stroke-width="3"
        stroke-linejoin="round"
        vector-effect="non-scaling-stroke" />
    </svg>
    <span
      v-for="(p, i) in board.places"
      :key="p.id"
      class="mapprev__pin"
      :class="{ 'mapprev__pin--left': p.point[0] > 800 }"
      :style="{
        left: `${p.point[0] / 10}%`,
        top: `${p.point[1] / 10}%`,
        '--pin-delay': `${0.35 + Math.min(i, 10) * 0.04}s`
      }">
      <span class="mapprev__dot" />
      <span class="mapprev__label">{{ p.name }}</span>
    </span>
  </div>
  <slot v-else />
</template>

<style scoped>
.mapprev {
  position: relative;
  width: 100%;
  max-width: 100%;
  border-radius: 10px;
  overflow: hidden;
  border: 1px solid var(--line);
  background: var(--bg-deep);
}
.mapprev img,
.mapprev svg {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
}
.mapprev__pin {
  position: absolute;
  transform: translate(-5px, -5px);
  display: flex;
  align-items: center;
  gap: 4px;
  pointer-events: none;
}
/* Near the right edge the name goes on the left, so it is not cut off. */
.mapprev__pin--left {
  flex-direction: row-reverse;
  transform: translate(calc(-100% + 5px), -5px);
}
.mapprev__dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #f2c94c;
  border: 2px solid #2e2718;
  flex: none;
}
.mapprev__label {
  font-size: 11.5px;
  font-weight: 600;
  color: #fff;
  white-space: nowrap;
  text-shadow:
    0 0 3px #000,
    0 0 2px #000;
}
/* ————— motion: the map unrolls, roads are inked in, places drop onto it ————— */
.mapprev img {
  animation: mapprev-unroll 0.9s var(--ease-settle) both;
}
@keyframes mapprev-unroll {
  from {
    opacity: 0;
    transform: scale(1.06);
  }
}
.mapprev svg {
  animation: mapprev-ink 1.1s var(--ease-io) 0.2s both;
}
@keyframes mapprev-ink {
  from {
    clip-path: inset(0 100% 0 0);
  }
  to {
    clip-path: inset(0 0 0 0);
  }
}
.mapprev__pin > * {
  animation: mapprev-drop 0.5s var(--ease-settle) var(--pin-delay, 0.35s) both;
}
@keyframes mapprev-drop {
  from {
    opacity: 0;
    transform: translateY(-10px) scale(0.6);
  }
}
.mapprev__dot {
  box-shadow: 0 0 0 0 rgba(242, 201, 76, 0.6);
}
</style>
