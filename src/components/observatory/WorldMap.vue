<script setup lang="ts">
/**
 * Observatory map: the world's map art with place labels, routes and
 * character tokens. Every position comes from the map manifest anchors
 * and the cast's current places, never from model output.
 */
import { computed } from 'vue'
import type { MapAnchorView, MapPlace, MapRoadLineView } from '../../../content/clients/worldsim'
import type { Token } from '../../game/observatory'
import { assetUrl } from '../../api/worldsim'
import FramedImage from '../ui/FramedImage.vue'

const props = defineProps<{
  worldId: string
  mapAssetId: string | null
  anchors: MapAnchorView[]
  places: MapPlace[]
  /** Roads as drawn on the art; places joined otherwise get straight lines. */
  roads?: MapRoadLineView[]
  tokens: Token[]
  /** Place of the latest scene: gently highlighted. */
  activePlaceId: string | null
  /** Character to emphasise (e.g. hovered in the feed). */
  focusId?: string | null
  /** Places with a map of their own, which can be looked inside. */
  inside?: string[]
  /** A small map beside other things: no explanatory note. */
  compact?: boolean
}>()

const emit = defineEmits<{ select: [characterId: string]; enter: [placeId: string] }>()
const enterable = computed(() => new Set(props.inside ?? []))

const at = computed(
  () => new Map(props.anchors.map((a) => [a.location_id, { x: Number(a.x), y: Number(a.y) }]))
)
const labels = computed(() =>
  props.places
    .filter((p) => at.value.has(p.id))
    .map((p) => ({ id: p.id, name: p.name, ...at.value.get(p.id)! }))
)
/** Drawn roads, in the 0..1000 box the overlay uses. */
const drawn = computed(() =>
  (props.roads ?? []).map((road) => ({
    key: [road.from_location_id, road.to_location_id].sort().join('|'),
    by: road.by ?? 'road',
    points: (road.points ?? [])
      .map((p) => `${Number(p[0]) * 1000},${Number(p[1]) * 1000}`)
      .join(' ')
  }))
)
/** Each route once, drawn between the two anchors it joins, unless drawn above. */
const routes = computed(() => {
  const seen = new Set<string>(drawn.value.map((d) => d.key))
  const lines: { key: string; x1: number; y1: number; x2: number; y2: number }[] = []
  for (const place of props.places) {
    const from = at.value.get(place.id)
    for (const route of place.routes ?? []) {
      const to = at.value.get(route.to_location_id)
      const key = [place.id, route.to_location_id].sort().join('|')
      if (!from || !to || seen.has(key)) continue
      seen.add(key)
      lines.push({ key, x1: from.x, y1: from.y, x2: to.x, y2: to.y })
    }
  }
  return lines
})
const art = computed(() => (props.mapAssetId ? assetUrl(props.worldId, props.mapAssetId) : null))

function initials(name: string): string {
  return name
    .split(/\s+/)
    .map((part) => part.charAt(0))
    .join('')
    .slice(0, 2)
    .toUpperCase()
}
</script>

<template>
  <div class="wm" :class="{ 'wm--schematic': !art }">
    <img v-if="art" class="wm__art" :src="art" alt="" draggable="false" />
    <svg class="wm__routes" viewBox="0 0 1000 1000" preserveAspectRatio="none" aria-hidden="true">
      <g v-for="d in drawn" :key="d.key">
        <polyline class="wm__road-under" :points="d.points" vector-effect="non-scaling-stroke" />
        <polyline
          class="wm__road"
          :class="{ 'wm__road--sea': d.by === 'sea' || d.by === 'river' }"
          :points="d.points"
          vector-effect="non-scaling-stroke" />
      </g>
    </svg>
    <svg class="wm__routes" aria-hidden="true">
      <g v-for="r in routes" :key="r.key">
        <line
          class="wm__road-under"
          :x1="`${r.x1 * 100}%`"
          :y1="`${r.y1 * 100}%`"
          :x2="`${r.x2 * 100}%`"
          :y2="`${r.y2 * 100}%`" />
        <line
          class="wm__road"
          :x1="`${r.x1 * 100}%`"
          :y1="`${r.y1 * 100}%`"
          :x2="`${r.x2 * 100}%`"
          :y2="`${r.y2 * 100}%`" />
      </g>
    </svg>
    <div
      v-for="place in labels"
      :key="place.id"
      class="wm__place"
      :class="{ 'wm__place--active': place.id === activePlaceId }"
      :style="{ left: `${place.x * 100}%`, top: `${place.y * 100}%` }">
      <span class="wm__pin" aria-hidden="true" />
      <button
        v-if="enterable.has(place.id)"
        type="button"
        class="wm__label wm__label--enter"
        :title="`Look inside ${place.name}`"
        @click="emit('enter', place.id)">
        {{ place.name }} <span class="wm__enter">Inside ›</span>
      </button>
      <span v-else class="wm__label">{{ place.name }}</span>
    </div>
    <button
      v-for="token in tokens"
      :key="token.id"
      type="button"
      class="wm__token"
      :class="{ 'wm__token--focus': token.id === focusId, 'wm__token--road': token.travelling }"
      :style="{ left: `${token.x * 100}%`, top: `${token.y * 100}%` }"
      :title="token.name"
      :aria-label="`${token.name}`"
      @click="emit('select', token.id)">
      <FramedImage
        v-if="token.portraitAssetId"
        :src="assetUrl(worldId, token.portraitAssetId)"
        :frame="token.faceFrame" />
      <span v-else>{{ initials(token.name) }}</span>
      <em class="wm__name">{{ token.name }}</em>
    </button>
    <p v-if="!art && !compact" class="wm__note">
      No map art for this world yet. Places are shown schematically.
    </p>
  </div>
</template>

<style scoped>
.wm {
  position: relative;
  width: 100%;
  border-radius: var(--radius-card);
  overflow: hidden;
  border: 1px solid var(--line);
  background: var(--surface-2);
  box-shadow: var(--card-shadow);
  user-select: none;
}
.wm--schematic {
  aspect-ratio: 16 / 10;
  background:
    radial-gradient(circle at 30% 30%, rgba(154, 123, 63, 0.08), transparent 60%), var(--surface-2);
}
.wm__art {
  display: block;
  width: 100%;
  height: auto;
}
.wm__routes {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
}
.wm__road-under {
  stroke: rgba(46, 39, 24, 0.45);
  stroke-width: 5px;
  stroke-linecap: round;
}
.wm__road {
  stroke: var(--cream-on-teal);
  stroke-width: 2.5px;
  stroke-dasharray: 10px 8px;
  stroke-linecap: round;
}
.wm__routes polyline {
  fill: none;
  stroke-linejoin: round;
}
.wm__road--sea {
  stroke: #d8ecf5;
}
.wm__token--road {
  border-style: dashed;
  transition:
    left 0.8s ease,
    top 0.8s ease;
}
.wm__place {
  position: absolute;
  transform: translate(-50%, -50%);
  display: flex;
  flex-direction: column;
  align-items: center;
  pointer-events: none;
}
.wm__pin {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: var(--gold);
  border: 2px solid var(--cream-on-teal);
  box-shadow: 0 0 0 1px rgba(46, 39, 24, 0.35);
}
.wm__place--active .wm__pin {
  background: var(--teal);
  animation: wm-pulse 2.4s ease-out infinite;
}
.wm__label {
  margin-top: 4px;
  padding: 1px 8px;
  border-radius: 999px;
  font-family: var(--font-display);
  font-size: 17px;
  font-weight: 600;
  color: var(--ink);
  background: rgba(249, 242, 225, 0.88);
  border: 1px solid var(--line);
  white-space: nowrap;
}
.wm__label--enter {
  pointer-events: auto;
  cursor: pointer;
  border-color: var(--teal);
}
.wm__label--enter:hover,
.wm__label--enter:focus-visible {
  background: var(--cream-on-teal);
  color: var(--teal-ink);
}
.wm__enter {
  margin-left: 5px;
  padding: 1px 8px 2px;
  border-radius: 999px;
  font-family: var(--font-ui);
  font-size: 12.5px;
  font-weight: 700;
  line-height: 1.3;
  letter-spacing: 0.02em;
  vertical-align: 1px;
  background: var(--teal);
  color: var(--cream-on-teal);
}
.wm__token {
  position: absolute;
  transform: translate(-50%, calc(-100% - 22px));
  width: 46px;
  height: 46px;
  padding: 0;
  border-radius: 50%;
  border: 2px solid var(--cream-on-teal);
  background: var(--teal);
  color: var(--cream-on-teal);
  font: 600 15px var(--font-body);
  box-shadow: 0 2px 6px rgba(46, 39, 24, 0.35);
  cursor: pointer;
  transition:
    left 0.8s ease,
    top 0.8s ease,
    transform 0.15s ease;
}
.wm__token img,
.wm__token .framed {
  width: 100%;
  height: 100%;
  border-radius: 50%;
  object-fit: cover;
  object-position: top;
}
.wm__token:hover,
.wm__token:focus-visible,
.wm__token--focus {
  transform: translate(-50%, calc(-100% - 22px)) scale(1.12);
  border-color: var(--gold-soft);
  z-index: 2;
}
.wm__name {
  position: absolute;
  left: 50%;
  top: 100%;
  transform: translateX(-50%);
  margin-top: 2px;
  padding: 0 6px;
  border-radius: 6px;
  font-style: normal;
  font-size: 13px;
  color: var(--ink);
  background: rgba(249, 242, 225, 0.9);
  white-space: nowrap;
}
.wm__note {
  position: absolute;
  left: 12px;
  bottom: 10px;
  font-size: 13px;
  color: var(--ink-3);
}
@keyframes wm-pulse {
  0% {
    box-shadow:
      0 0 0 1px rgba(46, 39, 24, 0.35),
      0 0 0 0 rgba(20, 84, 90, 0.45);
  }
  100% {
    box-shadow:
      0 0 0 1px rgba(46, 39, 24, 0.35),
      0 0 0 18px rgba(20, 84, 90, 0);
  }
}
</style>
