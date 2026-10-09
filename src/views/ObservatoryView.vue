<script setup lang="ts">
/**
 * World Observatory (E5): map-led view of a story with an event feed and
 * server-side autoplay. Step and Play both ask the server to run beats;
 * the page only watches, so closing it never strands a beat, and autoplay
 * pauses itself once nobody is watching.
 */
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import type { ChronicleEntry, SceneArtView } from '../../content/clients/worldsim'
import WorldMap from '../components/observatory/WorldMap.vue'
import PlaceMap from '../components/observatory/PlaceMap.vue'
import EventFeed from '../components/observatory/EventFeed.vue'
import EventModal from '../components/observatory/EventModal.vue'
import BranchDialog from '../components/story/BranchDialog.vue'
import { useBranchPoints } from '../composables/useBranchPoints'
import { canBranch, canRewind } from '../game/branches'
import MomentDialog from '../components/story/MomentDialog.vue'
import PaintSceneDialog from '../components/story/PaintSceneDialog.vue'
import { assetUrl } from '../api/worldsim'
import { readyMoments, type Speaker } from '../game/moments'
import { onlyExperience } from '../game/party'
import IconArrowLeft from '../components/icons/IconArrowLeft.vue'
import IconPlay from '../components/icons/IconPlay.vue'
import IconArrowRight from '../components/icons/IconArrowRight.vue'
import { useObservatory } from '../composables/useObservatory'
import { vRipple } from '../composables/useEffects'
import {
  BEAT_LIMITS,
  SPEEDS,
  autoplayStatus,
  beatTimeLabel,
  rollsByScene,
  rollsFor,
  speedFor
} from '../game/observatory'

const route = useRoute()
const storyId = computed(() => String(route.params.storyId ?? ''))
const obs = useObservatory(storyId)
const branchNow = computed(() => obs.presentation.value?.absolute_index ?? 0)
const branches = useBranchPoints(storyId, branchNow)
/** The turn whose "Branch from here" was chosen (the confirmation is open). */
const branchingTurn = ref<number | null>(null)
function branchFrom(index: number): void {
  // The event view is a native dialog on the top layer: close it first.
  opened.value = null
  branchingTurn.value = index
}
/** The turn whose "Go back to this turn" was chosen (the confirmation is open). */
const rewindingTurn = ref<number | null>(null)
function rewindTo(index: number): void {
  opened.value = null
  rewindingTurn.value = index
}
/** The story went back: read it again from the start, in place. */
async function rewound(): Promise<void> {
  await Promise.all([obs.load(), branches.reload()])
}

const speed = ref(SPEEDS[0].delaySeconds)
const beatLimit = ref(BEAT_LIMITS[1])
const panel = ref<'map' | 'events'>('map')
const opened = ref<ChronicleEntry | null>(null)
const focusId = ref<string | null>(null)
/** The place being looked inside, when it has a map of its own. */
const insideId = ref<string | null>(null)

// Re-render the countdown every second without refetching.
const now = ref(Date.now())
let clock: ReturnType<typeof setInterval> | undefined

const view = computed(() => obs.presentation.value)
const status = computed(() => autoplayStatus(obs.autoplay.value, obs.openBeat.value, now.value))
const timeLabel = computed(() =>
  view.value ? beatTimeLabel(view.value.absolute_index) : 'Opening the world…'
)
const busy = computed(() => obs.acting.value || obs.loading.value)
const stepDisabled = computed(
  () => busy.value || !obs.canOperate.value || obs.playing.value || obs.beatOpen.value
)
const names = computed(() => new Map((view.value?.cast ?? []).map((c) => [c.character_id, c.name])))
const placeNames = computed(() => new Map(obs.places.value.map((p) => [p.id, p.name])))
const activePlaceId = computed(() => {
  for (const beat of obs.feed.value) {
    const located = [...beat.entries].reverse().find((e) => e.location_id)
    if (located?.location_id) return located.location_id
  }
  return null
})

const placeMaps = computed(() => view.value?.place_maps ?? [])

/* Going inside zooms the world map into the place; leaving pulls back out of it. */
const lastInside = ref<string | null>(null)
const zoomOrigin = computed(() => {
  const anchor = view.value?.manifest.anchors?.find((a) => a.location_id === lastInside.value)
  return anchor ? `${Number(anchor.x) * 100}% ${Number(anchor.y) * 100}%` : '50% 50%'
})
function goInside(placeId: string): void {
  lastInside.value = placeId
  insideId.value = placeId
}
const insideMap = computed(
  () => placeMaps.value.find((m) => m.location_id === insideId.value) ?? null
)

/* ————— pictures: painted scenes, the moment view, and painting one ————— */
const moments = computed(() => readyMoments(view.value?.scene_art))
const pictured = computed(() => new Set(moments.value.map((m) => m.scene_id)))
const openedMoment = ref<number | null>(null)
const paintingScene = ref<string | null>(null)
const callOpts = computed(() => ({
  role: obs.role.value,
  characterId: obs.grant.value?.character_id ?? undefined
}))
const speakers = computed(() => {
  const out = new Map<string, Speaker>()
  for (const c of view.value?.cast ?? []) {
    out.set(c.character_id, {
      name: c.name,
      portraitUrl: c.portrait_asset_id ? assetUrl(storyId.value, c.portrait_asset_id, 160) : null
    })
  }
  return out
})
/** The scene's newest picture that did not fail (ready, or still being painted). */
/** Each scene's dice (combat stories): a mark in the feed, the rolls in the event view. */
const sceneRolls = computed(() => rollsByScene(obs.entries.value))
const fought = computed(
  () =>
    new Set([...sceneRolls.value].filter(([, rolls]) => !onlyExperience(rolls)).map(([key]) => key))
)

function pictureFor(entry: ChronicleEntry): SceneArtView | null {
  const mine = (view.value?.scene_art ?? []).filter(
    (a) => a.scene_id === entry.scene_id && a.status !== 'failed'
  )
  return mine[mine.length - 1] ?? null
}
function openMoment(pictureId: string): void {
  const at = moments.value.findIndex((m) => m.picture_id === pictureId)
  if (at < 0) return
  opened.value = null
  openedMoment.value = at
}
function paint(sceneId: string): void {
  opened.value = null
  paintingScene.value = sceneId
}

function nameOf(id: string): string {
  return names.value.get(id) ?? 'Someone'
}
function placeOf(id: string | null | undefined): string | null {
  return id ? (placeNames.value.get(id) ?? null) : null
}

function togglePlay(): void {
  if (obs.playing.value) void obs.pause()
  else void obs.play(speed.value, beatLimit.value)
}

function openLatestFor(characterId: string): void {
  for (const beat of obs.feed.value) {
    const hit = beat.entries.find((e) => e.participant_ids?.includes(characterId))
    if (hit) {
      opened.value = hit
      return
    }
  }
}

function onVisibility(): void {
  if (document.visibilityState === 'visible') obs.onVisible()
}

onMounted(() => {
  void obs.load().then(() => {
    const current = obs.autoplay.value
    if (current?.status === 'playing') speed.value = speedFor(current.delay_seconds).delaySeconds
  })
  clock = setInterval(() => (now.value = Date.now()), 1000)
  document.addEventListener('visibilitychange', onVisibility)
})
onUnmounted(() => {
  if (clock !== undefined) clearInterval(clock)
  document.removeEventListener('visibilitychange', onVisibility)
})
</script>

<template>
  <main class="obs ev-rise">
    <header class="obs__bar">
      <RouterLink class="obs__back" :to="{ name: 'story-play', params: { storyId } }">
        <IconArrowLeft :size="16" /> Story room
      </RouterLink>
      <div class="obs__title">
        <h1>{{ obs.title.value ?? 'World observatory' }}</h1>
        <Transition name="obs-tick" mode="out-in">
          <p :key="timeLabel">{{ timeLabel }}</p>
        </Transition>
      </div>
      <div class="obs__controls" role="group" aria-label="Autoplay">
        <button
          v-ripple
          type="button"
          class="obs__btn"
          :disabled="stepDisabled"
          title="Run one beat"
          @click="obs.step()">
          <span
            v-if="obs.acting.value && !obs.playing.value"
            class="obs__spin ev-progress-spin"
            aria-hidden="true" />
          <IconArrowRight v-else :size="16" class="obs__step-ico" /> Step
        </button>
        <button
          v-ripple
          type="button"
          class="obs__btn obs__btn--primary"
          :class="{ 'obs__btn--live': obs.playing.value }"
          :disabled="busy || !obs.canOperate.value"
          :aria-pressed="obs.playing.value"
          @click="togglePlay()">
          <template v-if="obs.playing.value"
            ><span class="obs__pause" aria-hidden="true" /> Pause</template
          >
          <template v-else><IconPlay :size="16" /> Play</template>
        </button>
        <label class="obs__pick">
          <span>Between beats</span>
          <select v-model.number="speed" :disabled="obs.playing.value || !obs.canOperate.value">
            <option v-for="s in SPEEDS" :key="s.key" :value="s.delaySeconds">{{ s.label }}</option>
          </select>
        </label>
        <label class="obs__pick">
          <span>Stop after</span>
          <select v-model.number="beatLimit" :disabled="obs.playing.value || !obs.canOperate.value">
            <option v-for="n in BEAT_LIMITS" :key="n" :value="n">{{ n }} beats</option>
          </select>
        </label>
      </div>
      <p class="obs__status" role="status" aria-live="polite">
        <Transition name="ev-pop">
          <span v-if="obs.playing.value" class="obs__live" aria-hidden="true"><i></i></span>
        </Transition>
        {{ status }}
      </p>
    </header>

    <Transition name="ev-rise">
      <p v-if="obs.error.value" class="obs__notice obs__notice--error ev-nudge" role="alert">
        {{ obs.error.value }}
        <button type="button" class="obs__link" @click="obs.load()">Retry</button>
      </p>
    </Transition>
    <Transition name="ev-rise">
      <p v-if="obs.actionError.value" class="obs__notice obs__notice--error ev-nudge" role="alert">
        {{ obs.actionError.value }}
      </p>
    </Transition>
    <p v-if="view && !obs.canOperate.value" class="obs__notice">
      You are watching a Player story: it moves on its player's attempts, from the story room.
    </p>
    <p v-else-if="obs.autoplay.value && !obs.autoplay.value.runner_enabled" class="obs__notice">
      Autoplay is switched off on this server (WORLDSIM_AUTOPLAY__ENABLED), so Step and Play will
      not run beats.
    </p>

    <nav class="obs__tabs" aria-label="Observatory panels">
      <button type="button" :aria-pressed="panel === 'map'" @click="panel = 'map'">Map</button>
      <button type="button" :aria-pressed="panel === 'events'" @click="panel = 'events'">
        Events
      </button>
    </nav>

    <div class="obs__grid" :data-panel="panel">
      <div class="obs__map">
        <Transition :name="insideMap ? 'obs-dive' : 'obs-surface'" mode="out-in">
          <PlaceMap
            v-if="view && insideMap"
            key="inside"
            :world-id="storyId"
            :place-map="insideMap"
            :place-name="placeOf(insideMap.location_id) ?? 'This place'"
            :cast="view.cast ?? []"
            :activities="view.activities ?? []"
            :scenes="obs.entries.value"
            :focus-id="focusId"
            @select="openLatestFor"
            @leave="insideId = null" />
          <WorldMap
            v-else-if="view"
            key="world"
            :style="{ transformOrigin: zoomOrigin }"
            :world-id="storyId"
            :map-asset-id="view.manifest.asset_id ?? null"
            :map-width="view.manifest.width"
            :map-height="view.manifest.height"
            :anchors="view.manifest.anchors ?? []"
            :roads="view.manifest.roads ?? []"
            :places="obs.places.value"
            :tokens="obs.tokens.value"
            :active-place-id="activePlaceId"
            :focus-id="focusId"
            :inside="placeMaps.map((m) => m.location_id)"
            @select="openLatestFor"
            @enter="goInside" />
          <p v-else key="loading" class="obs__notice obs__loading">
            Loading the map<span class="ev-dots" aria-hidden="true"
              ><span>.</span><span>.</span><span>.</span></span
            >
          </p>
        </Transition>
      </div>
      <EventFeed
        class="obs__feed"
        :beats="obs.feed.value"
        :name-of="nameOf"
        :place-of="placeOf"
        :pictured="pictured"
        :fought="fought"
        :branchable="branches.kept.value"
        :latest-turn="branches.latest.value"
        @branch="branchFrom"
        @rewind="rewindTo"
        @open="opened = $event"
        @focus="focusId = $event" />
    </div>

    <EventModal
      v-if="opened"
      :world-id="storyId"
      :entry="opened"
      :map-asset-id="view?.manifest.asset_id ?? null"
      :opts="callOpts"
      :name-of="nameOf"
      :place-of="placeOf"
      :picture="pictureFor(opened)"
      :rolls="rollsFor(sceneRolls, opened)"
      :branchable="canBranch(branches.kept.value, opened.absolute_index)"
      :rewindable="canRewind(branches.kept.value, branches.latest.value, opened.absolute_index)"
      @branch="branchFrom"
      @rewind="rewindTo"
      @moment="openMoment"
      @paint="paint"
      @close="opened = null" />
    <MomentDialog
      :world-id="storyId"
      :moments="moments"
      :index="openedMoment"
      :speakers="speakers"
      :places="placeNames"
      :opts="callOpts"
      @update:index="openedMoment = $event"
      @repainted="obs.refresh()"
      @close="openedMoment = null" />
    <PaintSceneDialog
      :world-id="storyId"
      :scene-id="paintingScene"
      :opts="callOpts"
      @close="paintingScene = null"
      @painted="obs.refresh()" />
    <BranchDialog
      :open="branchingTurn !== null"
      :story-id="storyId"
      :story-title="obs.title.value ?? 'Story'"
      :turn="branchingTurn"
      @close="branchingTurn = null" />
    <BranchDialog
      mode="rewind"
      :open="rewindingTurn !== null"
      :story-id="storyId"
      :story-title="obs.title.value ?? 'Story'"
      :turn="rewindingTurn"
      :latest="branches.latest.value"
      @rewound="rewound"
      @close="rewindingTurn = null" />
  </main>
</template>

<style scoped>
.obs {
  max-width: 1500px;
  margin: 0 auto;
  padding: 12px 16px 24px;
}
.obs__bar {
  display: grid;
  grid-template-columns: auto 1fr auto;
  grid-template-areas:
    'back title controls'
    'status status status';
  align-items: center;
  gap: 8px 16px;
  padding: 10px 14px;
  border: 1px solid var(--line);
  border-radius: var(--radius-card);
  background: var(--surface-2);
  box-shadow: var(--card-shadow);
}
.obs__back {
  grid-area: back;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--teal-ink);
  text-decoration: none;
  font-size: 15px;
}
.obs__title {
  grid-area: title;
  min-width: 0;
}
.obs__title h1 {
  font-family: var(--font-display);
  font-size: 26px;
  line-height: 1.1;
  color: var(--ink);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.obs__title p {
  font-size: 14px;
  color: var(--gold);
  letter-spacing: 0.03em;
}
.obs__controls {
  grid-area: controls;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}
.obs__btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font: 600 15px var(--font-body);
  padding: 7px 14px;
  border-radius: 10px;
  border: 1px solid var(--line-strong);
  background: var(--surface);
  color: var(--ink-2);
  cursor: pointer;
  transition:
    translate var(--dur) var(--ease-settle),
    scale var(--dur-quick) var(--ease-out),
    box-shadow var(--dur) ease,
    filter var(--dur) ease;
}
.obs__btn:hover:not(:disabled) {
  translate: 0 -1px;
  box-shadow: 0 6px 14px -8px rgba(46, 39, 24, 0.5);
}
.obs__btn:active:not(:disabled) {
  translate: 0 0;
  scale: 0.96;
}
.obs__btn:hover:not(:disabled) .obs__step-ico {
  translate: 2px 0;
}
.obs__step-ico {
  transition: translate var(--dur) var(--ease-settle);
}
.obs__spin {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  border: 2px solid rgba(69, 59, 39, 0.25);
  border-top-color: var(--teal);
  animation: obs-spin 0.8s linear infinite;
}
@keyframes obs-spin {
  to {
    transform: rotate(360deg);
  }
}
/* while the world plays, Pause glows like a lit lantern */
.obs__btn--live {
  position: relative;
  --ev-breathe-color: rgba(20, 84, 90, 0.45);
  --ev-ring-scale: 1.15;
}
.obs__btn--live::after {
  inset: 0;
  content: '';
  position: absolute;
  pointer-events: none;
  border-radius: inherit;
  box-shadow: 0 0 0 3px var(--ev-breathe-color, var(--ember-glow));
  opacity: 0;
  animation: ev-ring 2.4s var(--ease-out) infinite;
}
.obs__live {
  display: inline-grid;
  place-items: center;
  width: 12px;
  height: 12px;
  margin-right: 6px;
  vertical-align: -1px;
}
.obs__live i {
  position: relative;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--ember);
  --ev-breathe-color: rgba(194, 97, 42, 0.55);
  --ev-ring-scale: 2.2;
}
.obs__live i::after {
  inset: 0;
  content: '';
  position: absolute;
  pointer-events: none;
  border-radius: inherit;
  box-shadow: 0 0 0 3px var(--ev-breathe-color, var(--ember-glow));
  opacity: 0;
  animation: ev-ring 1.6s var(--ease-out) infinite;
}
.obs__btn--primary {
  background: var(--teal);
  border-color: var(--teal);
  color: var(--cream-on-teal);
  min-width: 96px;
  justify-content: center;
}
.obs__btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.obs__pause {
  width: 10px;
  height: 12px;
  border-left: 3px solid currentColor;
  border-right: 3px solid currentColor;
}
.obs__pick {
  display: grid;
  font-size: 12px;
  color: var(--ink-3);
}
.obs__pick select {
  font: inherit;
  font-size: 14px;
  color: var(--ink-2);
  padding: 4px 6px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--surface);
}
.obs__status {
  grid-area: status;
  font-size: 14px;
  color: var(--ink-3);
}
.obs__notice {
  margin-top: 10px;
  padding: 8px 14px;
  border-radius: 10px;
  border: 1px solid var(--line);
  background: var(--surface-2);
  font-size: 15px;
}
.obs__notice--error {
  border-color: #b3543f;
  background: #fbeee8;
  color: #7c3226;
}
.obs__link {
  font: inherit;
  color: var(--teal-ink);
  background: none;
  border: none;
  text-decoration: underline;
  cursor: pointer;
}
.obs__tabs {
  display: none;
}
.obs__grid {
  display: grid;
  grid-template-columns: minmax(0, 7fr) minmax(300px, 3fr);
  gap: 14px;
  margin-top: 12px;
  height: calc(100vh - 190px);
  min-height: 420px;
}
.obs__map {
  min-height: 0;
  overflow: auto;
}
.obs__loading {
  margin-top: 0;
  min-height: 320px;
  display: grid;
  place-items: center;
  color: var(--ink-3);
  border-style: dashed;
  animation: ev-shimmer 1.6s linear infinite;
  background:
    linear-gradient(
        100deg,
        rgba(255, 252, 240, 0) 30%,
        rgba(255, 252, 240, 0.7) 50%,
        rgba(255, 252, 240, 0) 70%
      )
      0 0 / 250% 100%,
    var(--surface-2);
}
/* the turn label rolls over like a clock face when a beat passes */
.obs-tick-enter-active {
  transition:
    opacity 0.3s var(--ease-out),
    transform 0.4s var(--ease-settle);
}
.obs-tick-leave-active {
  transition:
    opacity 0.14s var(--ease-in),
    transform 0.14s var(--ease-in);
}
.obs-tick-enter-from {
  opacity: 0;
  transform: translateY(8px);
}
.obs-tick-leave-to {
  opacity: 0;
  transform: translateY(-6px);
}
/* diving into a place: the world map zooms toward it and dissolves */
.obs-dive-leave-active {
  transition:
    transform 0.34s var(--ease-in),
    opacity 0.34s var(--ease-in),
    filter 0.34s var(--ease-in);
}
.obs-dive-leave-to {
  transform: scale(1.7);
  opacity: 0;
  filter: blur(4px);
}
.obs-dive-enter-active {
  transition: opacity 0.3s var(--ease-out);
}
.obs-dive-enter-from {
  opacity: 0;
}
/* coming back out: the place shrinks away, the world map pulls back from it */
.obs-surface-leave-active {
  transition:
    transform 0.22s var(--ease-in),
    opacity 0.22s var(--ease-in);
}
.obs-surface-leave-to {
  transform: scale(0.92);
  opacity: 0;
}
.obs-surface-enter-active {
  transition:
    transform 0.7s var(--ease-settle),
    opacity 0.4s var(--ease-out),
    filter 0.5s var(--ease-out);
}
.obs-surface-enter-from {
  transform: scale(1.7);
  opacity: 0;
  filter: blur(4px);
}
/* a map without art fills the column beside the events */
.obs__map :deep(.wm--schematic) {
  aspect-ratio: auto;
  height: 100%;
  min-height: 380px;
}
.obs__feed {
  min-height: 0;
}
@media (max-width: 900px) {
  .obs__bar {
    grid-template-columns: 1fr;
    grid-template-areas:
      'back'
      'title'
      'controls'
      'status';
  }
  .obs__tabs {
    display: flex;
    gap: 6px;
    margin-top: 10px;
  }
  .obs__tabs button {
    flex: 1;
    font: 600 15px var(--font-body);
    padding: 6px;
    border-radius: 10px;
    border: 1px solid var(--line);
    background: var(--surface);
    color: var(--ink-2);
    transition:
      background-color var(--dur) ease,
      color var(--dur) ease,
      border-color var(--dur) ease,
      scale var(--dur-quick) var(--ease-out);
  }
  .obs__tabs button:active {
    scale: 0.97;
  }
  /* the panel you switch to slides up into place */
  .obs__grid[data-panel='map'] .obs__map,
  .obs__grid[data-panel='events'] .obs__feed {
    animation: obs-panel-in 0.4s var(--ease-settle) both;
  }
  .obs__tabs button[aria-pressed='true'] {
    background: var(--teal);
    border-color: var(--teal);
    color: var(--cream-on-teal);
  }
  .obs__grid {
    grid-template-columns: 1fr;
    height: auto;
  }
  .obs__grid[data-panel='map'] .obs__feed,
  .obs__grid[data-panel='events'] .obs__map {
    display: none;
  }
  .obs__feed {
    height: 70vh;
  }
}
@keyframes obs-panel-in {
  from {
    opacity: 0;
    translate: 0 10px;
  }
}
</style>
