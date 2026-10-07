<!--
  WorldMapView — draw a world from its map: bring a picture (upload or
  paint), let the map reader find the places and trace the roads, fix what
  it got wrong, then say how long the shortest and the longest road take.
  Saving pins the places, adds new ones and times every road (a new world
  revision). Pure board logic: src/game/worldMap.ts.
-->
<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import SaveBar from '../components/ui/SaveBar.vue'
import PageIntro from '../components/ui/PageIntro.vue'
import IconArrowLeft from '../components/icons/IconArrowLeft.vue'
import IconGlobe from '../components/icons/IconGlobe.vue'
import IconImage from '../components/icons/IconImage.vue'
import IconBranch from '../components/icons/IconBranch.vue'
import IconClock from '../components/icons/IconClock.vue'
import IconInfo from '../components/icons/IconInfo.vue'
import IconSparkle from '../components/icons/IconSparkle.vue'
import IconPlus from '../components/icons/IconPlus.vue'
import IconX from '../components/icons/IconX.vue'
import {
  duplicatePreset,
  getPreset,
  libraryAssetUrl,
  paintMap,
  readMapPlaces,
  readMapRoads,
  saveWorldMap,
  uploadMap
} from '../api/worldsim'
import { isVersionConflict } from '../api/http'
import type { PresetDetail } from '../../content/clients/worldsim'
import {
  PHASES_PER_DAY,
  boardFromPreset,
  describePhases,
  keptPlaces,
  liveRoads,
  mapPrompt,
  placesFromReading,
  roadLine,
  roadsFromReading,
  saveProblem,
  saveRequest,
  savedScale,
  timedRoads,
  toPhases,
  worldPlaces,
  type Board,
  type BoardPlace,
  type TimeUnit,
  type WorldPlace
} from '../game/worldMap'

const route = useRoute()
const router = useRouter()
const presetId = computed(() => String(route.params.id ?? ''))

const detail = ref<PresetDetail | null>(null)
const board = ref<Board | null>(null)
const baseline = ref('')
const loading = ref(true)
const busy = ref<'' | 'upload' | 'paint' | 'places' | 'roads' | 'save' | 'copy'>('')
const error = ref<string | null>(null)
const notice = ref<string | null>(null)
const savedFlash = ref(false)
const selected = ref<string | null>(null)
const placing = ref(false)
const dragging = ref<string | null>(null)
const showPaint = ref(false)
const paintPrompt = ref('')
const paintRatio = ref('16:9')
const connectTo = ref('')
const connectBy = ref('road')

const shortestAmount = ref(2)
const shortestUnit = ref<TimeUnit>('phases')
const longestAmount = ref(2)
const longestUnit = ref<TimeUnit>('days')

const worldName = computed(() => detail.value?.name ?? 'This world')
const readonly = computed(() => detail.value?.readonly ?? false)
const places = computed<WorldPlace[]>(() => (detail.value ? worldPlaces(detail.value) : []))
const shortest = computed(() => toPhases(shortestAmount.value, shortestUnit.value))
const longest = computed(() => toPhases(longestAmount.value, longestUnit.value))
const scaleProblem = computed(() =>
  longest.value < shortest.value ? 'The longest road cannot be quicker than the shortest.' : null
)
const timed = computed(() =>
  board.value && !scaleProblem.value ? timedRoads(board.value, shortest.value, longest.value) : []
)
const problem = computed(() =>
  board.value ? (saveProblem(board.value) ?? scaleProblem.value) : 'Bring a map first.'
)
const snapshot = computed(() => JSON.stringify([board.value, shortest.value, longest.value]))
const dirty = computed(() => board.value !== null && snapshot.value !== baseline.value)
const pictureUrl = computed(() => (board.value ? libraryAssetUrl(board.value.assetId) : ''))
const aspect = computed(() =>
  board.value ? `${board.value.width} / ${board.value.height}` : '16 / 9'
)
const selectedPlace = computed(
  () => board.value?.places.find((p) => p.id === selected.value) ?? null
)
const nameOf = (id: string) => board.value?.places.find((p) => p.id === id)?.name ?? '?'
const keptCount = computed(() => (board.value ? keptPlaces(board.value).length : 0))
const linesFor = computed(() =>
  board.value
    ? liveRoads(board.value).map((road) => ({
        road,
        points: roadLine(board.value!, road)
          .map(([x, y]) => `${x},${y}`)
          .join(' ')
      }))
    : []
)
const otherPlaces = computed(() =>
  board.value && selected.value
    ? board.value.places.filter((p) => p.keep && p.id !== selected.value)
    : []
)

function message(err: unknown, fallback: string): string {
  return err instanceof Error && err.message ? err.message : fallback
}

function setScale(phasesShort: number, phasesLong: number): void {
  const pick = (phases: number): [number, TimeUnit] =>
    phases >= PHASES_PER_DAY && phases % PHASES_PER_DAY === 0
      ? [phases / PHASES_PER_DAY, 'days']
      : [phases, 'phases']
  ;[shortestAmount.value, shortestUnit.value] = pick(phasesShort)
  ;[longestAmount.value, longestUnit.value] = pick(phasesLong)
}

function adopt(view: PresetDetail): void {
  detail.value = view
  board.value = boardFromPreset(view)
  const scale = savedScale(view)
  if (scale) setScale(scale.shortest, scale.longest)
  baseline.value = snapshot.value
  paintPrompt.value = mapPrompt(view.name, worldPlaces(view))
}

async function load(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    adopt(await getPreset(presetId.value, undefined))
  } catch (err) {
    error.value = message(err, 'Could not load this world.')
  } finally {
    loading.value = false
  }
}

function newBoard(view: { asset_id: string; width: number; height: number }): void {
  board.value = {
    assetId: view.asset_id,
    width: view.width,
    height: view.height,
    places: [],
    roads: []
  }
  selected.value = null
  notice.value = null
}

async function onFile(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  if (file.size > 16 * 1024 * 1024) {
    error.value = 'That picture is over 16 MB. Try a smaller one.'
    return
  }
  busy.value = 'upload'
  error.value = null
  try {
    const dataUrl = await new Promise<string>((resolve, reject) => {
      const reader = new FileReader()
      reader.onload = () => resolve(String(reader.result))
      reader.onerror = () => reject(new Error('Could not read that file.'))
      reader.readAsDataURL(file)
    })
    newBoard(await uploadMap(dataUrl))
  } catch (err) {
    error.value = message(err, 'Could not upload that map.')
  } finally {
    busy.value = ''
  }
}

async function paint(): Promise<void> {
  if (!paintPrompt.value.trim()) return
  busy.value = 'paint'
  error.value = null
  try {
    newBoard(await paintMap(paintPrompt.value.trim(), paintRatio.value))
    showPaint.value = false
  } catch (err) {
    error.value = message(err, 'Could not paint a map.')
  } finally {
    busy.value = ''
  }
}

async function findPlaces(): Promise<void> {
  if (!board.value) return
  busy.value = 'places'
  error.value = null
  try {
    const reading = await readMapPlaces(board.value.assetId)
    board.value.places = placesFromReading(reading.places, places.value)
    board.value.roads = []
    selected.value = null
    const kept = board.value.places.filter((p) => p.keep).length
    notice.value =
      `Found ${reading.places.length} places in ${Math.round(Number(reading.seconds))} s ` +
      `($${Number(reading.cost_usd).toFixed(4)}). ${kept} are kept as places to go; ` +
      'roads, seas, scenery and parts of other places are left off (grey). Check them, then trace the roads.'
  } catch (err) {
    error.value = message(err, 'The map reader could not find the places.')
  } finally {
    busy.value = ''
  }
}

async function traceRoads(): Promise<void> {
  if (!board.value) return
  const sent = keptPlaces(board.value)
  if (sent.length < 2) {
    error.value = 'Keep at least two places to trace roads between.'
    return
  }
  busy.value = 'roads'
  error.value = null
  try {
    const reading = await readMapRoads(
      board.value.assetId,
      sent.map((p) => ({ name: p.name, kind: p.kind, point: p.point }))
    )
    board.value.roads = roadsFromReading(reading.roads, sent)
    notice.value =
      `Traced ${board.value.roads.length} roads in ${Math.round(Number(reading.seconds))} s ` +
      `($${Number(reading.cost_usd).toFixed(4)}). Remove any that aren't there, add any it missed.`
  } catch (err) {
    error.value = message(err, 'The map reader could not trace the roads.')
  } finally {
    busy.value = ''
  }
}

function pointFrom(event: PointerEvent): [number, number] | null {
  const frame = (event.currentTarget as HTMLElement).closest('.mapframe')
  if (!frame) return null
  const box = frame.getBoundingClientRect()
  const clamp = (v: number) => Math.max(0, Math.min(1000, Math.round(v * 1000)))
  return [
    clamp((event.clientX - box.left) / box.width),
    clamp((event.clientY - box.top) / box.height)
  ]
}

function onFrameClick(event: PointerEvent): void {
  if (!board.value || !placing.value) return
  const point = pointFrom(event)
  if (!point) return
  const place: BoardPlace = {
    id: `added-${Date.now()}`,
    name: 'New place',
    kind: 'landmark',
    point,
    key: null,
    keep: true
  }
  board.value.places.push(place)
  selected.value = place.id
  placing.value = false
}

function startDrag(event: PointerEvent, place: BoardPlace): void {
  selected.value = place.id
  dragging.value = place.id
  ;(event.currentTarget as HTMLElement).setPointerCapture(event.pointerId)
}

function onDrag(event: PointerEvent, place: BoardPlace): void {
  if (dragging.value !== place.id) return
  const point = pointFrom(event)
  if (point) place.point = point
}

function removeRoad(index: number): void {
  if (!board.value) return
  const road = liveRoads(board.value)[index]
  board.value.roads = board.value.roads.filter((r) => r !== road)
}

function addRoad(): void {
  if (!board.value || !selected.value || !connectTo.value) return
  const a = selected.value
  const b = connectTo.value
  const exists = board.value.roads.some((r) => (r.a === a && r.b === b) || (r.a === b && r.b === a))
  if (!exists) board.value.roads.push({ a, b, by: connectBy.value, points: [] })
  connectTo.value = ''
}

function onKeyChange(place: BoardPlace, value: string): void {
  place.key = value || null
  const match = places.value.find((p) => p.key === value)
  if (match) place.name = match.name
}

async function save(): Promise<void> {
  if (!board.value || !detail.value || problem.value || !dirty.value) return
  busy.value = 'save'
  error.value = null
  try {
    const saved = await saveWorldMap(
      presetId.value,
      saveRequest(board.value, shortest.value, longest.value, detail.value.version)
    )
    adopt(saved)
    notice.value = 'Saved. New stories in this world use these places and travel times.'
    savedFlash.value = true
    setTimeout(() => (savedFlash.value = false), 1400)
  } catch (err) {
    error.value = isVersionConflict(err)
      ? 'This world changed elsewhere. Reload the page to see the latest.'
      : message(err, 'Could not save the map.')
  } finally {
    busy.value = ''
  }
}

async function makeCopy(): Promise<void> {
  busy.value = 'copy'
  error.value = null
  try {
    const copy = await duplicatePreset(presetId.value)
    await router.replace({ name: 'library-world-map', params: { id: copy.id } })
    await load()
  } catch (err) {
    error.value = message(err, 'Could not copy this world.')
  } finally {
    busy.value = ''
  }
}

function discard(): void {
  if (detail.value) adopt(detail.value)
  selected.value = null
  notice.value = null
}

const ROAD_COLORS: Record<string, string> = {
  road: '#c0392b',
  path: '#b7791f',
  sea: '#1f6fb2',
  river: '#2b8a9e',
  bridge: '#7d5a3c',
  pass: '#6b4f9e'
}
const colorOf = (by: string) => ROAD_COLORS[by] ?? '#c0392b'

onMounted(load)
</script>

<template>
  <main class="wmap">
    <header class="wmap__head">
      <RouterLink
        class="wmap__back"
        :to="{ name: 'library-world-studio', params: { id: presetId } }">
        <IconArrowLeft :size="14" /> Back to the world
      </RouterLink>
      <PageIntro
        :title="`World map${detail ? ` · ${worldName}` : ''}`"
        sub="Bring a map of this world. The map reader finds its places and roads; you fix what it got wrong and say how long travel takes." />
    </header>

    <p v-if="error" class="wmap__alert" role="alert">{{ error }}</p>
    <p v-if="loading" class="ev-info"><IconInfo :size="14" /> Loading…</p>

    <template v-else-if="detail">
      <section v-if="readonly" class="card ev-card">
        <p class="card__sub">
          <strong>{{ worldName }}</strong> is a built-in world and can't change. Make your own copy
          to give it a map.
        </p>
        <div>
          <button type="button" class="cta cta--sm" :disabled="busy !== ''" @click="makeCopy">
            {{ busy === 'copy' ? 'Copying…' : 'Make my own copy' }}
          </button>
        </div>
      </section>

      <template v-else>
        <!-- picture ------------------------------------------------------------ -->
        <section class="card ev-card">
          <header class="card__head">
            <span class="card__icon"><IconImage :size="20" /></span>
            <div>
              <h2 class="card__title">1 · The map</h2>
              <p class="card__sub">
                Upload a map you made, or paint one. Clear roads and labels help the map reader.
              </p>
            </div>
          </header>
          <div class="row">
            <label class="ghost filepick" :class="{ 'is-busy': busy === 'upload' }">
              <input
                type="file"
                accept="image/png,image/jpeg,image/webp"
                :disabled="busy !== ''"
                @change="onFile" />
              {{
                busy === 'upload' ? 'Uploading…' : board ? 'Upload a different map' : 'Upload a map'
              }}
            </label>
            <button
              type="button"
              class="ghost"
              :disabled="busy !== ''"
              @click="showPaint = !showPaint">
              <IconSparkle :size="14" /> Paint one
            </button>
          </div>
          <div v-if="showPaint" class="paint">
            <label class="field">
              <span class="field__label">What to paint</span>
              <textarea v-model="paintPrompt" class="ev-input words" rows="3" />
            </label>
            <div class="row">
              <select v-model="paintRatio" class="ev-input ratio" aria-label="Shape">
                <option value="16:9">Wide (16:9)</option>
                <option value="3:2">Landscape (3:2)</option>
                <option value="1:1">Square</option>
              </select>
              <button type="button" class="cta cta--sm" :disabled="busy !== ''" @click="paint">
                {{ busy === 'paint' ? 'Painting… (up to a minute)' : 'Paint the map' }}
              </button>
            </div>
          </div>
        </section>

        <!-- board -------------------------------------------------------------- -->
        <section v-if="board" class="card ev-card">
          <header class="card__head">
            <span class="card__icon"><IconGlobe :size="20" /></span>
            <div>
              <h2 class="card__title">2 · Places and roads</h2>
              <p class="card__sub">
                Drag a pin to move it, click one to rename it or connect it.
                <template v-if="board.places.length === 0">Start by finding the places.</template>
              </p>
            </div>
          </header>
          <div class="row">
            <button type="button" class="cta cta--sm" :disabled="busy !== ''" @click="findPlaces">
              {{
                busy === 'places'
                  ? 'Reading the map… (about 10 s)'
                  : board.places.length
                    ? 'Find the places again'
                    : 'Find the places'
              }}
            </button>
            <button
              type="button"
              class="cta cta--sm"
              :disabled="busy !== '' || keptCount < 2"
              @click="traceRoads">
              {{
                busy === 'roads'
                  ? 'Tracing roads… (up to a minute)'
                  : board.roads.length
                    ? 'Trace the roads again'
                    : 'Trace the roads'
              }}
            </button>
            <button
              type="button"
              class="ghost"
              :class="{ 'is-on': placing }"
              :disabled="busy !== ''"
              @click="placing = !placing">
              <IconPlus :size="14" /> {{ placing ? 'Click the map to place it' : 'Add a place' }}
            </button>
          </div>
          <p v-if="notice" class="card__note"><IconInfo :size="14" /> {{ notice }}</p>

          <div class="boardwrap">
            <div
              class="mapframe"
              :class="{ 'mapframe--placing': placing }"
              :style="{ aspectRatio: aspect }"
              @pointerup="dragging = null"
              @click="onFrameClick($event as PointerEvent)">
              <img :src="pictureUrl" :alt="`Map of ${worldName}`" draggable="false" />
              <svg viewBox="0 0 1000 1000" preserveAspectRatio="none" aria-hidden="true">
                <polyline
                  v-for="(line, i) in linesFor"
                  :key="i"
                  :points="line.points"
                  :stroke="colorOf(line.road.by)"
                  :stroke-dasharray="line.road.by === 'sea' ? '6 5' : undefined"
                  fill="none"
                  stroke-width="4"
                  stroke-linejoin="round"
                  vector-effect="non-scaling-stroke" />
              </svg>
              <button
                v-for="p in board.places"
                :key="p.id"
                type="button"
                class="pin"
                :class="{
                  'pin--off': !p.keep,
                  'pin--on': p.id === selected,
                  'pin--new': p.keep && !p.key
                }"
                :style="{ left: `${p.point[0] / 10}%`, top: `${p.point[1] / 10}%` }"
                :title="p.name"
                @click.stop="selected = p.id"
                @pointerdown.stop="startDrag($event, p)"
                @pointermove="onDrag($event, p)"
                @pointerup="dragging = null">
                <span class="pin__dot"></span>
                <span class="pin__label">{{ p.name }}</span>
              </button>
            </div>

            <aside class="side">
              <div v-if="selectedPlace" class="inspect">
                <label class="field">
                  <span class="field__label">Name</span>
                  <input v-model="selectedPlace.name" class="ev-input" maxlength="128" />
                </label>
                <label class="field">
                  <span class="field__label">This is</span>
                  <select
                    class="ev-input"
                    :value="selectedPlace.key ?? ''"
                    @change="
                      onKeyChange(selectedPlace, ($event.target as HTMLSelectElement).value)
                    ">
                    <option value="">A new place</option>
                    <option v-for="w in places" :key="w.key" :value="w.key">
                      {{ w.name }} (already in the world)
                    </option>
                  </select>
                </label>
                <RouterLink
                  v-if="selectedPlace.key && !dirty"
                  class="inside"
                  :to="{
                    name: 'library-place-maps',
                    params: { id: presetId, key: selectedPlace.key }
                  }">
                  Draw inside {{ selectedPlace.name }} →
                </RouterLink>
                <label class="check">
                  <input v-model="selectedPlace.keep" type="checkbox" /> A place to go
                  <small>({{ selectedPlace.kind || 'place' }})</small>
                </label>
                <div v-if="selectedPlace.keep && otherPlaces.length" class="connect">
                  <span class="field__label">Connect to</span>
                  <div class="row">
                    <select v-model="connectTo" class="ev-input" aria-label="Place to connect">
                      <option value="" disabled>Choose a place</option>
                      <option v-for="o in otherPlaces" :key="o.id" :value="o.id">
                        {{ o.name }}
                      </option>
                    </select>
                    <select v-model="connectBy" class="ev-input small" aria-label="Road kind">
                      <option
                        v-for="k in ['road', 'path', 'sea', 'river', 'bridge', 'pass']"
                        :key="k"
                        :value="k">
                        {{ k }}
                      </option>
                    </select>
                    <button type="button" class="ghost" :disabled="!connectTo" @click="addRoad">
                      Add
                    </button>
                  </div>
                </div>
              </div>
              <p v-else class="card__note"><IconInfo :size="14" /> Click a pin to edit it.</p>

              <ul class="legend">
                <li><span class="sw sw--new"></span> New place</li>
                <li><span class="sw"></span> Already in the world</li>
                <li><span class="sw sw--off"></span> Left off</li>
              </ul>
            </aside>
          </div>
        </section>

        <!-- travel -------------------------------------------------------------- -->
        <section v-if="board && board.places.length" class="card ev-card">
          <header class="card__head">
            <span class="card__icon"><IconClock :size="20" /></span>
            <div>
              <h2 class="card__title">3 · Travel time</h2>
              <p class="card__sub">
                Say how long the shortest and the longest road take; every other road scales with
                its length on the map. A day has {{ PHASES_PER_DAY }} phases, dawn to midnight.
              </p>
            </div>
          </header>
          <div class="pair">
            <label class="field">
              <span class="field__label">The shortest road takes</span>
              <span class="row">
                <input
                  v-model.number="shortestAmount"
                  class="ev-input amount"
                  type="number"
                  min="1"
                  max="99" />
                <select v-model="shortestUnit" class="ev-input small" aria-label="Unit">
                  <option value="phases">phases</option>
                  <option value="days">days</option>
                </select>
              </span>
            </label>
            <label class="field">
              <span class="field__label">The longest road takes</span>
              <span class="row">
                <input
                  v-model.number="longestAmount"
                  class="ev-input amount"
                  type="number"
                  min="1"
                  max="99" />
                <select v-model="longestUnit" class="ev-input small" aria-label="Unit">
                  <option value="phases">phases</option>
                  <option value="days">days</option>
                </select>
              </span>
            </label>
          </div>
          <p v-if="scaleProblem" class="over">{{ scaleProblem }}</p>
          <div class="roads-scroll">
            <table v-if="timed.length" class="roads">
              <thead>
                <tr>
                  <th>Road</th>
                  <th>By</th>
                  <th>Takes</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(t, i) in timed" :key="`${t.road.a}-${t.road.b}`">
                  <td><IconBranch :size="13" /> {{ nameOf(t.road.a) }} — {{ nameOf(t.road.b) }}</td>
                  <td>
                    <span class="by" :style="{ color: colorOf(t.road.by) }">{{ t.road.by }}</span>
                  </td>
                  <td class="num">{{ describePhases(t.phases) }}</td>
                  <td>
                    <button
                      type="button"
                      class="iconbtn"
                      :aria-label="`Remove ${nameOf(t.road.a)} to ${nameOf(t.road.b)}`"
                      @click="removeRoad(i)">
                      <IconX :size="12" />
                    </button>
                  </td>
                </tr>
              </tbody>
            </table>
            <p v-else class="card__note">
              <IconInfo :size="14" /> No roads yet: trace them, or connect places by hand.
            </p>
          </div>
        </section>
      </template>
    </template>

    <SaveBar
      v-if="board && !readonly"
      :dirty="dirty"
      :saved="savedFlash"
      secondary-label="Discard"
      @secondary="discard">
      <template #end>
        <span v-if="problem && dirty" class="problem">{{ problem }}</span>
        <button
          type="button"
          class="cta cta--foot"
          :disabled="!dirty || !!problem || busy !== ''"
          @click="save">
          {{ busy === 'save' ? 'Saving…' : 'Save the map to this world' }}
        </button>
      </template>
    </SaveBar>
  </main>
</template>

<style scoped>
.wmap {
  max-width: 1200px;
  margin: 0 auto;
  padding: 14px 16px 40px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.wmap__back {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 14.5px;
  color: var(--teal-ink);
  margin-bottom: 8px;
}
.wmap__alert {
  padding: 10px 14px;
  border: 1px solid #d6a58c;
  border-radius: 10px;
  background: #fbede5;
  color: #8a3b1c;
}
.card {
  padding: 18px 22px 22px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.card__head {
  display: flex;
  gap: 14px;
  align-items: flex-start;
}
.card__head > div {
  flex: 1;
  min-width: 0;
  text-align: left;
}
.card__icon {
  flex: none;
  width: 40px;
  height: 40px;
  border-radius: 10px;
  border: 1px solid #cdbb93;
  background: #fbf5e6;
  color: var(--ink);
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
.card__title {
  font-family: var(--font-display);
  font-size: 24px;
  font-weight: 600;
  color: var(--ink);
}
.card__sub {
  margin-top: 2px;
  font-size: 15px;
  line-height: 1.5;
  color: var(--ink-2);
  max-width: 72ch;
}
.card__note {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  font-size: 13.5px;
  color: var(--muted);
  line-height: 1.45;
}
.card__note svg {
  flex: none;
  margin-top: 2px;
}
.row {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
}
.filepick {
  position: relative;
  cursor: pointer;
}
.filepick input {
  position: absolute;
  inset: 0;
  opacity: 0;
  cursor: pointer;
}
.is-on {
  border-color: var(--teal-ink);
  color: var(--teal-ink);
}
.paint {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.field {
  display: flex;
  flex-direction: column;
  gap: 7px;
  min-width: 0;
}
.field__label {
  font-size: 15.5px;
  font-weight: 600;
  color: var(--ink-2);
}
.words {
  height: auto;
  min-height: 84px;
  padding: 10px 12px;
  resize: vertical;
  line-height: 1.45;
}
.ratio {
  width: auto;
}
.small {
  width: auto;
  min-width: 90px;
}
.amount {
  width: 90px;
  font-variant-numeric: tabular-nums;
}
.boardwrap {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 280px;
  gap: 18px;
  align-items: start;
}
.mapframe {
  position: relative;
  width: 100%;
  max-width: 100%;
  border-radius: 10px;
  overflow: hidden;
  border: 1px solid var(--line-strong);
  background: var(--bg-deep);
  touch-action: none;
  user-select: none;
}
.mapframe--placing {
  cursor: crosshair;
}
.mapframe img,
.mapframe svg {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
}
.mapframe svg {
  pointer-events: none;
}
.pin {
  position: absolute;
  transform: translate(-50%, -50%);
  display: flex;
  align-items: center;
  gap: 4px;
  cursor: grab;
  touch-action: none;
  padding: 2px;
}
.pin:active {
  cursor: grabbing;
}
.pin__dot {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: #f2c94c;
  border: 2px solid #2e2718;
  flex: none;
}
.pin__label {
  font-size: 12.5px;
  font-weight: 600;
  color: #fff;
  text-shadow:
    0 0 3px #000,
    0 0 2px #000;
  white-space: nowrap;
  position: absolute;
  left: 18px;
  pointer-events: none;
}
.pin--new .pin__dot {
  background: #6fcf97;
}
.pin--off .pin__dot {
  background: #bbb;
  opacity: 0.6;
  width: 10px;
  height: 10px;
}
.pin--off .pin__label {
  display: none;
}
.pin--off:hover .pin__label,
.pin--off.pin--on .pin__label {
  display: inline;
  opacity: 0.75;
  font-weight: 400;
}
.pin--on .pin__dot {
  box-shadow: 0 0 0 4px rgba(31, 106, 94, 0.55);
}
.side {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.inspect {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.check {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 15px;
  color: var(--ink-2);
}
.inside {
  font-size: 14px;
  color: var(--teal-ink);
}
.check small {
  color: var(--muted);
}
.connect {
  display: flex;
  flex-direction: column;
  gap: 7px;
}
.connect .ev-input {
  flex: 1;
  min-width: 0;
}
.legend {
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 13.5px;
  color: var(--muted);
}
.sw {
  display: inline-block;
  width: 11px;
  height: 11px;
  border-radius: 50%;
  border: 2px solid #2e2718;
  background: #f2c94c;
  margin-right: 6px;
  vertical-align: -1px;
}
.sw--new {
  background: #6fcf97;
}
.sw--off {
  background: #bbb;
}
.pair {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 18px 24px;
}
.roads-scroll {
  overflow-x: auto;
}
.roads {
  width: 100%;
  border-collapse: collapse;
  font-size: 15px;
}
.roads th {
  text-align: left;
  font-size: 12.5px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--muted);
  font-weight: 600;
  padding: 6px 8px;
  border-bottom: 1px solid var(--line);
}
.roads td {
  padding: 7px 8px;
  border-bottom: 1px solid var(--line-soft);
  color: var(--ink);
}
.num {
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.by {
  font-weight: 600;
}
.iconbtn {
  display: inline-flex;
  padding: 5px;
  border-radius: 6px;
  color: var(--muted);
}
.iconbtn:hover {
  color: #b3542e;
  background: #fbede5;
}
.over,
.problem {
  color: #b3542e;
  font-weight: 600;
  font-size: 14px;
}
@media (max-width: 900px) {
  .boardwrap {
    grid-template-columns: 1fr;
  }
  .pair {
    grid-template-columns: 1fr;
  }
}
</style>
