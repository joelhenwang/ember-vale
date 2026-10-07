<script setup lang="ts">
/**
 * World Observatory (E5): map-led view of a story with an event feed and
 * server-side autoplay. Step and Play both ask the server to run beats;
 * the page only watches, so closing it never strands a beat, and autoplay
 * pauses itself once nobody is watching.
 */
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import type { ChronicleEntry } from '../../content/clients/worldsim'
import WorldMap from '../components/observatory/WorldMap.vue'
import PlaceMap from '../components/observatory/PlaceMap.vue'
import EventFeed from '../components/observatory/EventFeed.vue'
import EventModal from '../components/observatory/EventModal.vue'
import IconArrowLeft from '../components/icons/IconArrowLeft.vue'
import IconPlay from '../components/icons/IconPlay.vue'
import IconArrowRight from '../components/icons/IconArrowRight.vue'
import { useObservatory } from '../composables/useObservatory'
import { BEAT_LIMITS, SPEEDS, autoplayStatus, beatTimeLabel, speedFor } from '../game/observatory'

const route = useRoute()
const storyId = computed(() => String(route.params.storyId ?? ''))
const obs = useObservatory(storyId)

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
const insideMap = computed(
  () => placeMaps.value.find((m) => m.location_id === insideId.value) ?? null
)

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
  <main class="obs">
    <header class="obs__bar">
      <RouterLink class="obs__back" :to="{ name: 'story-play', params: { storyId } }">
        <IconArrowLeft :size="16" /> Story room
      </RouterLink>
      <div class="obs__title">
        <h1>{{ obs.title.value ?? 'World observatory' }}</h1>
        <p>{{ timeLabel }}</p>
      </div>
      <div class="obs__controls" role="group" aria-label="Autoplay">
        <button
          type="button"
          class="obs__btn"
          :disabled="stepDisabled"
          title="Run one beat"
          @click="obs.step()">
          <IconArrowRight :size="16" /> Step
        </button>
        <button
          type="button"
          class="obs__btn obs__btn--primary"
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
      <p class="obs__status" role="status" aria-live="polite">{{ status }}</p>
    </header>

    <p v-if="obs.error.value" class="obs__notice obs__notice--error" role="alert">
      {{ obs.error.value }}
      <button type="button" class="obs__link" @click="obs.load()">Retry</button>
    </p>
    <p v-if="obs.actionError.value" class="obs__notice obs__notice--error" role="alert">
      {{ obs.actionError.value }}
    </p>
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
        <PlaceMap
          v-if="view && insideMap"
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
          :world-id="storyId"
          :map-asset-id="view.manifest.asset_id ?? null"
          :anchors="view.manifest.anchors ?? []"
          :roads="view.manifest.roads ?? []"
          :places="obs.places.value"
          :tokens="obs.tokens.value"
          :active-place-id="activePlaceId"
          :focus-id="focusId"
          :inside="placeMaps.map((m) => m.location_id)"
          @select="openLatestFor"
          @enter="insideId = $event" />
        <p v-else class="obs__notice">Loading the map…</p>
      </div>
      <EventFeed
        class="obs__feed"
        :beats="obs.feed.value"
        :name-of="nameOf"
        :place-of="placeOf"
        @open="opened = $event"
        @focus="focusId = $event" />
    </div>

    <EventModal
      v-if="opened"
      :world-id="storyId"
      :entry="opened"
      :map-asset-id="view?.manifest.asset_id ?? null"
      :opts="{ role: obs.role.value, characterId: obs.grant.value?.character_id ?? undefined }"
      :name-of="nameOf"
      :place-of="placeOf"
      @close="opened = null" />
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
</style>
