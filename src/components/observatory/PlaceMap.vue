<script setup lang="ts">
/**
 * Inside one place: its own map art, the spots on it, and the characters
 * who are there, each at the spot that suits what they are doing
 * (src/game/placeMap.ts). Positions never come from model output.
 */
import { computed } from 'vue'
import type {
  ActivityView,
  CastEntry,
  ChronicleEntry,
  PlaceMapView
} from '../../../content/clients/worldsim'
import { layoutSpotTokens } from '../../game/placeMap'
import { assetUrl } from '../../api/worldsim'
import FramedImage from '../ui/FramedImage.vue'
import IconArrowLeft from '../icons/IconArrowLeft.vue'

const props = defineProps<{
  worldId: string
  placeMap: PlaceMapView
  placeName: string
  cast: CastEntry[]
  activities: ActivityView[]
  /** The story so far: a scene set at a spot stands its people there. */
  scenes?: ChronicleEntry[]
  focusId?: string | null
  /** Without the title bar (shown under tabs elsewhere). */
  bare?: boolean
}>()

const emit = defineEmits<{ select: [characterId: string]; leave: [] }>()

const tokens = computed(() =>
  layoutSpotTokens(props.placeMap, props.cast, props.activities, props.scenes ?? [])
)
const busy = computed(() => new Set(tokens.value.map((t) => t.spotKey)))
const art = computed(() => assetUrl(props.worldId, props.placeMap.asset_id))

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
  <section class="pm" :aria-label="`Inside ${placeName}`">
    <header v-if="!bare" class="pm__bar">
      <button type="button" class="pm__back" @click="emit('leave')">
        <IconArrowLeft :size="14" /> World map
      </button>
      <h2 class="pm__title">{{ placeName }}</h2>
      <p class="pm__count">
        {{
          tokens.length === 0
            ? 'Nobody is here'
            : tokens.length === 1
              ? '1 person here'
              : `${tokens.length} people here`
        }}
      </p>
    </header>
    <div class="pm__frame">
      <img class="pm__art" :src="art" :alt="`${placeName} up close`" draggable="false" />
      <span class="pm__light" aria-hidden="true"></span>
      <div
        v-for="(spot, i) in placeMap.spots ?? []"
        :key="spot.key"
        class="pm__spot"
        :class="{ 'pm__spot--busy': busy.has(spot.key) }"
        :style="{ left: `${Number(spot.x) * 100}%`, top: `${Number(spot.y) * 100}%`, '--i': i }"
        :title="spot.name">
        <span class="pm__dot" aria-hidden="true" />
        <span v-if="busy.has(spot.key)" class="pm__label">{{ spot.name }}</span>
      </div>
      <button
        v-for="(token, i) in tokens"
        :key="token.id"
        type="button"
        class="pm__token"
        :class="{ 'pm__token--focus': token.id === focusId }"
        :style="{ left: `${token.x * 100}%`, top: `${token.y * 100}%`, '--i': i }"
        :title="`${token.name} · ${token.spot}`"
        :aria-label="`${token.name}, at ${token.spot}`"
        @click="emit('select', token.id)">
        <FramedImage
          v-if="token.portraitAssetId"
          :src="assetUrl(worldId, token.portraitAssetId)"
          :frame="token.faceFrame" />
        <span v-else>{{ initials(token.name) }}</span>
        <em class="pm__name">{{ token.name }}</em>
      </button>
    </div>
  </section>
</template>

<style scoped>
.pm {
  border-radius: var(--radius-card);
  overflow: hidden;
  border: 1px solid var(--line);
  background: var(--surface-2);
  box-shadow: var(--card-shadow);
}
.pm__bar {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 6px 14px;
  padding: 8px 14px;
  border-bottom: 1px solid var(--line);
}
.pm__back {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font: 600 14.5px var(--font-body);
  color: var(--teal-ink);
  background: none;
  border: none;
  cursor: pointer;
  padding: 0;
}
.pm__back svg {
  transition: translate var(--dur) var(--ease-settle);
}
.pm__back:hover svg {
  translate: -3px 0;
}
.pm__title {
  animation: wm-title-in 0.5s var(--ease-settle) 0.1s both;
}
.pm__title {
  font-family: var(--font-display);
  font-size: 22px;
  color: var(--ink);
}
.pm__count {
  font-size: 14px;
  color: var(--ink-3);
}
.pm__frame {
  position: relative;
  overflow: hidden;
  user-select: none;
}
/* stepping inside: the camera pushes in through a soft blur and settles */
.pm__art {
  display: block;
  width: 100%;
  height: auto;
  animation: ev-push-in 1.1s var(--ease-settle) both;
}
/* a slow pool of warm light moving across the place */
.pm__light {
  position: absolute;
  inset: 0;
  pointer-events: none;
  mix-blend-mode: soft-light;
  background: radial-gradient(40% 50% at 30% 30%, rgba(255, 226, 170, 0.55), transparent 70%);
  animation: pm-light 22s var(--ease-sine) infinite alternate;
}
.pm__spot {
  position: absolute;
  transform: translate(-50%, -50%);
  display: flex;
  flex-direction: column;
  align-items: center;
  opacity: 0.7;
  animation: pm-spot-in 0.45s var(--ease-spring) calc(0.35s + min(var(--i, 0), 12) * 0.035s) both;
  transition: opacity var(--dur) ease;
}
.pm__spot--busy {
  opacity: 1;
  z-index: 1;
}
.pm__spot:hover {
  opacity: 1;
}
.pm__spot--busy .pm__dot {
  animation: pm-glow 2.6s var(--ease-sine) 1s infinite;
}
.pm__dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--gold);
  border: 2px solid var(--cream-on-teal);
  box-shadow: 0 0 0 1px rgba(46, 39, 24, 0.35);
}
.pm__label {
  margin-top: 3px;
  padding: 0 7px;
  border-radius: 999px;
  font-size: 13px;
  font-weight: 600;
  color: var(--ink);
  background: rgba(249, 242, 225, 0.82);
  border: 1px solid var(--line);
  white-space: nowrap;
}
.pm__token {
  position: absolute;
  transform: translate(-50%, calc(-100% - 10px));
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
    left 1.1s var(--ease-io),
    top 1.1s var(--ease-io),
    transform 0.32s var(--ease-spring),
    border-color var(--dur) ease;
  animation:
    pm-token-in 0.6s var(--ease-spring) calc(0.6s + min(var(--i, 0), 8) * 0.06s) both,
    pm-idle 3.6s var(--ease-sine) calc(1.3s + var(--i, 0) * 0.41s) infinite;
}
.pm__token img,
.pm__token .framed {
  width: 100%;
  height: 100%;
  border-radius: 50%;
  object-fit: cover;
  object-position: top;
}
.pm__token:hover,
.pm__token:focus-visible,
.pm__token--focus {
  transform: translate(-50%, calc(-100% - 10px)) scale(1.12);
  border-color: var(--gold-soft);
  z-index: 2;
}
@keyframes wm-title-in {
  from {
    opacity: 0;
    translate: 0 6px;
  }
}
@keyframes pm-light {
  from {
    translate: -10% -6%;
  }
  to {
    translate: 30% 24%;
  }
}
@keyframes pm-spot-in {
  from {
    opacity: 0;
    scale: 0.3;
  }
}
@keyframes pm-glow {
  0%,
  100% {
    box-shadow:
      0 0 0 1px rgba(46, 39, 24, 0.35),
      0 0 0 0 rgba(240, 199, 159, 0.7);
  }
  50% {
    box-shadow:
      0 0 0 1px rgba(46, 39, 24, 0.35),
      0 0 0 6px rgba(240, 199, 159, 0);
  }
}
@keyframes pm-token-in {
  from {
    opacity: 0;
    scale: 0.3;
  }
}
@keyframes pm-idle {
  0%,
  100% {
    translate: 0 0;
  }
  50% {
    translate: 0 -3px;
  }
}
.pm__name {
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
</style>
