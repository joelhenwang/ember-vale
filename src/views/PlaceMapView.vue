<!--
  PlaceMapView — draw inside a world's places: a closer picture of one
  place (uploaded or painted), the spots in it read off the picture (the
  inn, the market, the smithy), fixed by hand, saved to the world (a new
  revision). While a story plays, its watchers look inside the place and
  see who is where. Pure board logic: src/game/placeMap.ts.
-->
<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { burst, shake } from '../composables/useEffects'
import { useRoute, useRouter } from 'vue-router'
import SaveBar from '../components/ui/SaveBar.vue'
import PageIntro from '../components/ui/PageIntro.vue'
import IconArrowLeft from '../components/icons/IconArrowLeft.vue'
import IconCheck from '../components/icons/IconCheck.vue'
import IconGlobe from '../components/icons/IconGlobe.vue'
import IconImage from '../components/icons/IconImage.vue'
import IconInfo from '../components/icons/IconInfo.vue'
import IconPlus from '../components/icons/IconPlus.vue'
import IconSparkle from '../components/icons/IconSparkle.vue'
import {
  duplicatePreset,
  getPreset,
  libraryAssetUrl,
  paintMap,
  readMapSpots,
  savePlaceMap,
  uploadMap
} from '../api/worldsim'
import { isVersionConflict } from '../api/http'
import type { PresetDetail } from '../../content/clients/worldsim'
import {
  insideCandidates,
  keptSpots,
  placeMapRequest,
  placePrompt,
  presetPlaces,
  spotProblem,
  spotsFromReading,
  type BoardSpot,
  type InsideCandidate,
  type PresetPlace,
  type SpotBoard
} from '../game/placeMap'

const route = useRoute()
const router = useRouter()
const presetId = computed(() => String(route.params.id ?? ''))
const placeKey = computed(() => String(route.params.key ?? ''))

const detail = ref<PresetDetail | null>(null)
const board = ref<SpotBoard | null>(null)
const baseline = ref('')
const loading = ref(true)
const busy = ref<'' | 'upload' | 'paint' | 'spots' | 'save' | 'copy'>('')
const error = ref<string | null>(null)
const notice = ref<string | null>(null)
const savedFlash = ref(false)
const selected = ref<string | null>(null)
const placing = ref(false)
const dragging = ref<string | null>(null)
const showPaint = ref(false)
const paintPrompt = ref('')
const paintRatio = ref('16:9')

const worldName = computed(() => detail.value?.name ?? 'This world')
const readonly = computed(() => detail.value?.readonly ?? false)
const places = computed<PresetPlace[]>(() => (detail.value ? presetPlaces(detail.value) : []))
const place = computed(() => places.value.find((p) => p.key === placeKey.value) ?? null)
const snapshot = computed(() => JSON.stringify(board.value))
const dirty = computed(() => snapshot.value !== baseline.value)
const problem = computed(() => (board.value ? spotProblem(board.value) : null))
const pictureUrl = computed(() => (board.value ? libraryAssetUrl(board.value.assetId) : ''))
const aspect = computed(() =>
  board.value ? `${board.value.width} / ${board.value.height}` : '16 / 9'
)
const selectedSpot = computed(() => board.value?.spots.find((s) => s.id === selected.value) ?? null)
const keptCount = computed(() => (board.value ? keptSpots(board.value).length : 0))

/* inside every place at once ------------------------------------------------ */

type Step = 'waiting' | 'painting' | 'reading' | 'saving' | 'done' | 'failed' | 'skipped'
interface BatchRow extends InsideCandidate {
  tick: boolean
  step: Step
  note: string
}
const batch = ref<BatchRow[]>([])
const offered = ref(false)
const batchRunning = ref(false)
const batchStop = ref(false)
const batchCost = ref(0)
const ticked = computed(() => batch.value.filter((r) => r.tick).length)
const STEP_TEXT: Record<Step, string> = {
  waiting: '',
  painting: 'Painting…',
  reading: 'Reading the spots…',
  saving: 'Saving…',
  done: 'Done',
  failed: 'Failed',
  skipped: 'Stopped'
}

function offerBatch(): void {
  if (batchRunning.value || !detail.value) return
  offered.value = true
  batch.value = insideCandidates(detail.value).map((c) => ({
    ...c,
    tick: c.suggested,
    step: 'waiting',
    note: ''
  }))
}

/** Paint, read and save each ticked place in turn; one failure does not stop the rest. */
async function runBatch(): Promise<void> {
  if (batchRunning.value || dirty.value || !detail.value) return
  batchRunning.value = true
  batchStop.value = false
  batchCost.value = 0
  error.value = null
  for (const row of batch.value) {
    if (!row.tick || row.step === 'done') continue
    if (batchStop.value) {
      row.step = 'skipped'
      continue
    }
    try {
      row.step = 'painting'
      const picture = await paintMap(
        placePrompt(worldName.value, row.name, row.kind, row.description),
        '16:9'
      )
      row.step = 'reading'
      const reading = await readMapSpots(picture.asset_id)
      batchCost.value += Number(reading.cost_usd) || 0
      const spots = spotsFromReading(reading.places)
      if (!spots.some((s) => s.keep)) throw new Error('no spots found in the picture')
      row.step = 'saving'
      const board: SpotBoard = {
        assetId: picture.asset_id,
        width: picture.width,
        height: picture.height,
        spots
      }
      detail.value = await savePlaceMap(
        presetId.value,
        row.key,
        placeMapRequest(board, detail.value!.version)
      )
      row.step = 'done'
      row.note = `${keptSpots(board).length} spots`
    } catch (err) {
      row.step = 'failed'
      row.note = message(err, 'something went wrong')
    }
  }
  batchRunning.value = false
  showPlace()
  notice.value = null
}

function message(err: unknown, fallback: string): string {
  return err instanceof Error && err.message ? err.message : fallback
}

/** Show the chosen place's saved map (a fresh copy, so edits can be discarded). */
function showPlace(): void {
  const saved = place.value?.map ?? null
  board.value = saved ? JSON.parse(JSON.stringify(saved)) : null
  baseline.value = snapshot.value
  selected.value = null
  placing.value = false
  notice.value = null
  showPaint.value = false
  paintPrompt.value = placePrompt(
    worldName.value,
    place.value?.name ?? 'this place',
    '',
    place.value?.description ?? ''
  )
}

async function load(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    detail.value = await getPreset(presetId.value, undefined)
    if (!place.value && places.value.length) {
      await router.replace({
        name: 'library-place-maps',
        params: { id: presetId.value, key: places.value[0]!.key }
      })
    }
    showPlace()
  } catch (err) {
    error.value = message(err, 'Could not load this world.')
  } finally {
    loading.value = false
  }
}

watch(placeKey, showPlace)

function choose(key: string): void {
  if (dirty.value || key === placeKey.value) return
  void router.replace({ name: 'library-place-maps', params: { id: presetId.value, key } })
}

function newBoard(view: { asset_id: string; width: number; height: number }): void {
  board.value = { assetId: view.asset_id, width: view.width, height: view.height, spots: [] }
  selected.value = null
  notice.value = 'Now find the spots in it, or add them by hand.'
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
    error.value = message(err, 'Could not upload that picture.')
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
    error.value = message(err, 'Could not paint a picture.')
  } finally {
    busy.value = ''
  }
}

async function findSpots(): Promise<void> {
  if (!board.value) return
  busy.value = 'spots'
  error.value = null
  try {
    const reading = await readMapSpots(board.value.assetId)
    board.value.spots = spotsFromReading(reading.places)
    selected.value = null
    notice.value =
      `Found ${reading.places.length} spots in ${Math.round(Number(reading.seconds))} s ` +
      `($${Number(reading.cost_usd).toFixed(4)}). ${keptCount.value} are kept; ` +
      'roads and rivers running through are left off (grey). Rename, move or add any.'
  } catch (err) {
    error.value = message(err, 'The map reader could not find the spots.')
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
  const spot: BoardSpot = {
    id: `added-${Date.now()}`,
    name: 'New spot',
    kind: 'house',
    point,
    keep: true
  }
  board.value.spots.push(spot)
  selected.value = spot.id
  placing.value = false
}

function startDrag(event: PointerEvent, spot: BoardSpot): void {
  selected.value = spot.id
  dragging.value = spot.id
  ;(event.currentTarget as HTMLElement).setPointerCapture(event.pointerId)
}

function onDrag(event: PointerEvent, spot: BoardSpot): void {
  if (dragging.value !== spot.id) return
  const point = pointFrom(event)
  if (point) spot.point = point
}

/* ————— motion: what just arrived announces itself ————— */
const saveBtn = ref<HTMLElement | null>(null)
const alertEl = ref<HTMLElement | null>(null)
/** A fresh batch of spots (read or loaded) drops in one after another. */
const freshPins = ref(false)
let freshTimer: ReturnType<typeof setTimeout> | undefined
watch(
  () => board.value?.spots,
  (now, before) => {
    if (!now || now === before || now.length < 2 || busy.value === 'save') return
    freshPins.value = false
    requestAnimationFrame(() => {
      freshPins.value = true
      clearTimeout(freshTimer)
      freshTimer = setTimeout(() => (freshPins.value = false), 1600)
    })
  }
)
watch(error, (now) => {
  if (now) requestAnimationFrame(() => shake(alertEl.value))
})
onBeforeUnmount(() => clearTimeout(freshTimer))
const WORKING = new Set(['painting', 'reading', 'saving'])

function adopt(saved: PresetDetail, said: string): void {
  detail.value = saved
  showPlace()
  notice.value = said
  burst(saveBtn.value, { count: 18, spread: 90 })
  savedFlash.value = true
  setTimeout(() => (savedFlash.value = false), 1400)
}

async function save(): Promise<void> {
  if (!board.value || !detail.value || problem.value || !dirty.value) return
  busy.value = 'save'
  error.value = null
  try {
    const saved = await savePlaceMap(
      presetId.value,
      placeKey.value,
      placeMapRequest(board.value, detail.value.version)
    )
    adopt(saved, 'Saved. New stories in this world show who is where inside this place.')
  } catch (err) {
    error.value = isVersionConflict(err)
      ? 'This world changed elsewhere. Reload the page to see the latest.'
      : message(err, 'Could not save the map.')
  } finally {
    busy.value = ''
  }
}

async function removeMap(): Promise<void> {
  if (!detail.value) return
  busy.value = 'save'
  error.value = null
  try {
    const saved = await savePlaceMap(
      presetId.value,
      placeKey.value,
      placeMapRequest(null, detail.value.version)
    )
    adopt(saved, 'This place has no map of its own now.')
  } catch (err) {
    error.value = message(err, 'Could not take the map away.')
  } finally {
    busy.value = ''
  }
}

async function makeCopy(): Promise<void> {
  busy.value = 'copy'
  error.value = null
  try {
    const copy = await duplicatePreset(presetId.value)
    await router.replace({
      name: 'library-place-maps',
      params: { id: copy.id, key: placeKey.value }
    })
    await load()
  } catch (err) {
    error.value = message(err, 'Could not copy this world.')
  } finally {
    busy.value = ''
  }
}

onMounted(load)
</script>

<template>
  <main class="pmap ev-rise">
    <header class="pmap__head">
      <RouterLink
        class="pmap__back"
        :to="{ name: 'library-world-studio', params: { id: presetId } }">
        <IconArrowLeft :size="14" /> Back to the world
      </RouterLink>
      <PageIntro
        :title="`Inside the places${detail ? ` · ${worldName}` : ''}`"
        sub="Give a place its own closer map: the inn, the market, the smithy. While a story plays you can look inside and see who is where." />
    </header>

    <Transition name="ev-rise">
      <p v-if="error" ref="alertEl" class="pmap__alert" role="alert">{{ error }}</p>
    </Transition>
    <p v-if="loading" class="ev-info pmap__loading">
      <span class="spin ev-progress-spin" aria-hidden="true" /> Loading<span
        class="ev-dots"
        aria-hidden="true"
        ><span>.</span><span>.</span><span>.</span></span
      >
    </p>

    <template v-else-if="detail">
      <section v-if="readonly" class="card ev-card">
        <p class="card__sub">
          <strong>{{ worldName }}</strong> is a built-in world and can't change. Make your own copy
          to draw inside its places.
        </p>
        <div>
          <button type="button" class="cta cta--sm" :disabled="busy !== ''" @click="makeCopy">
            {{ busy === 'copy' ? 'Copying…' : 'Make my own copy' }}
          </button>
        </div>
      </section>

      <template v-else>
        <!-- which place ------------------------------------------------------- -->
        <section class="card ev-card">
          <header class="card__head">
            <span class="card__icon"><IconGlobe :size="20" /></span>
            <div>
              <h2 class="card__title">Which place</h2>
              <p class="card__sub">
                <template v-if="dirty">Save or discard this place's changes first.</template>
                <template v-else>A tick means the place already has a map of its own.</template>
              </p>
            </div>
          </header>
          <div class="chips ev-pop-stagger" role="group" aria-label="Places">
            <button
              v-for="p in places"
              :key="p.key"
              type="button"
              class="chip"
              :class="{ 'chip--on': p.key === placeKey }"
              :aria-pressed="p.key === placeKey"
              :disabled="dirty && p.key !== placeKey"
              @click="choose(p.key)">
              <IconCheck v-if="p.map" :size="12" />
              {{ p.name }}
            </button>
          </div>
        </section>

        <!-- inside every place at once ------------------------------------------ -->
        <section class="card ev-card">
          <header class="card__head">
            <span class="card__icon"><IconSparkle :size="20" /></span>
            <div>
              <h2 class="card__title">Inside every place at once</h2>
              <p class="card__sub">
                Paint a close-up of each place that has none yet, read its spots and save it. About
                half a minute a place; pictures you made yourself are never replaced.
              </p>
            </div>
          </header>
          <Transition name="ev-swap" mode="out-in">
            <div v-if="!offered" class="row">
              <button
                type="button"
                class="ghost"
                :disabled="busy !== '' || dirty"
                @click="offerBatch">
                Choose places to paint
              </button>
            </div>
            <div v-else class="batchwrap">
              <ul v-if="batch.length" class="batch ev-rise">
                <li
                  v-for="row in batch"
                  :key="row.key"
                  :class="`batch__row batch__row--${row.step}`">
                  <label class="check">
                    <input v-model="row.tick" type="checkbox" :disabled="batchRunning" />
                    {{ row.name }} <small v-if="row.kind">({{ row.kind }})</small>
                  </label>
                  <Transition name="ev-swap" mode="out-in">
                    <span :key="row.step" class="batch__step">
                      <span
                        v-if="WORKING.has(row.step)"
                        class="spin spin--sm ev-progress-spin"
                        aria-hidden="true" />
                      {{ STEP_TEXT[row.step]
                      }}<template v-if="row.note"> · {{ row.note }}</template>
                    </span>
                  </Transition>
                </li>
              </ul>
              <p v-else class="card__note">Every place already has a map of its own.</p>
              <div class="row">
                <button
                  v-if="!batchRunning"
                  type="button"
                  class="cta cta--sm"
                  :disabled="ticked === 0 || busy !== '' || dirty"
                  @click="runBatch">
                  {{
                    ticked === 0
                      ? 'Tick the places to paint'
                      : `Paint ${ticked} ${ticked === 1 ? 'place' : 'places'}`
                  }}
                </button>
                <button
                  v-else
                  type="button"
                  class="ghost"
                  :disabled="batchStop"
                  @click="batchStop = true">
                  {{ batchStop ? 'Stopping after this place…' : 'Stop' }}
                </button>
                <span v-if="batchCost > 0" class="card__note">
                  Reading cost so far ${{ batchCost.toFixed(4) }} (painting is free).
                </span>
              </div>
            </div>
          </Transition>
        </section>

        <Transition name="ev-swap" mode="out-in">
          <div v-if="place" :key="placeKey" class="pmap__place">
            <!-- picture ------------------------------------------------------------ -->
            <section class="card ev-card">
              <header class="card__head">
                <span class="card__icon"><IconImage :size="20" /></span>
                <div>
                  <h2 class="card__title">{{ place.name }}, up close</h2>
                  <p class="card__sub">
                    Upload a picture of {{ place.name }} seen from above, or paint one. Labelled
                    buildings and open spaces help the map reader.
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
                    busy === 'upload'
                      ? 'Uploading…'
                      : board
                        ? 'Upload a different picture'
                        : 'Upload a picture'
                  }}
                </label>
                <button
                  type="button"
                  class="ghost"
                  :disabled="busy !== ''"
                  @click="showPaint = !showPaint">
                  <IconSparkle :size="14" /> Paint one
                </button>
                <button
                  v-if="place.map"
                  type="button"
                  class="ghost danger"
                  :disabled="busy !== '' || dirty"
                  @click="removeMap">
                  Take this place's map away
                </button>
              </div>
              <Transition name="ev-rise">
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
                    <button
                      type="button"
                      class="cta cta--sm"
                      :disabled="busy !== ''"
                      @click="paint">
                      <span
                        v-if="busy === 'paint'"
                        class="spin ev-progress-spin"
                        aria-hidden="true" />
                      {{ busy === 'paint' ? 'Painting… (up to a minute)' : 'Paint the picture' }}
                    </button>
                  </div>
                </div>
              </Transition>
            </section>

            <!-- spots --------------------------------------------------------------- -->
            <Transition name="ev-rise">
              <section v-if="board" class="card ev-card">
                <header class="card__head">
                  <span class="card__icon"><IconGlobe :size="20" /></span>
                  <div>
                    <h2 class="card__title">Spots in {{ place.name }}</h2>
                    <p class="card__sub">
                      Where people can be. Drag a pin to move it, click one to rename it. Characters
                      rest at inns and houses, work at markets and workshops, train in yards and
                      patrol gates and towers.
                    </p>
                  </div>
                </header>
                <div class="row">
                  <button
                    type="button"
                    class="cta cta--sm"
                    :disabled="busy !== ''"
                    @click="findSpots">
                    <span
                      v-if="busy === 'spots'"
                      class="spin ev-progress-spin"
                      aria-hidden="true" />
                    {{
                      busy === 'spots'
                        ? 'Reading the picture… (about 10 s)'
                        : board.spots.length
                          ? 'Find the spots again'
                          : 'Find the spots'
                    }}
                  </button>
                  <button
                    type="button"
                    class="ghost"
                    :class="{ 'is-on': placing }"
                    :disabled="busy !== ''"
                    @click="placing = !placing">
                    <IconPlus :size="14" />
                    {{ placing ? 'Click the picture to place it' : 'Add a spot' }}
                  </button>
                </div>
                <Transition name="ev-rise" mode="out-in">
                  <p v-if="notice" :key="notice" class="card__note">
                    <IconInfo :size="14" /> {{ notice }}
                  </p>
                </Transition>

                <div class="boardwrap">
                  <div
                    class="mapframe"
                    :class="{ 'mapframe--placing': placing, 'mapframe--fresh-pins': freshPins }"
                    :style="{ aspectRatio: aspect }"
                    @pointerup="dragging = null"
                    @click="onFrameClick($event as PointerEvent)">
                    <img
                      :key="pictureUrl"
                      class="mapframe__pic"
                      :src="pictureUrl"
                      :alt="`${place.name} up close`"
                      draggable="false" />
                    <button
                      v-for="(s, i) in board.spots"
                      :key="s.id"
                      type="button"
                      class="pin"
                      :class="{ 'pin--off': !s.keep, 'pin--on': s.id === selected }"
                      :style="{
                        left: `${s.point[0] / 10}%`,
                        top: `${s.point[1] / 10}%`,
                        '--i': Math.min(i, 16)
                      }"
                      :title="s.name"
                      @click.stop="selected = s.id"
                      @pointerdown.stop="startDrag($event, s)"
                      @pointermove="onDrag($event, s)"
                      @pointerup="dragging = null">
                      <span class="pin__dot"></span>
                      <span class="pin__label">{{ s.name }}</span>
                    </button>
                  </div>

                  <aside class="side">
                    <Transition name="ev-swap" mode="out-in">
                      <div v-if="selectedSpot" :key="selectedSpot.id" class="inspect">
                        <label class="field">
                          <span class="field__label">Name</span>
                          <input v-model="selectedSpot.name" class="ev-input" maxlength="128" />
                        </label>
                        <label class="field">
                          <span class="field__label">Kind</span>
                          <input
                            v-model="selectedSpot.kind"
                            class="ev-input"
                            maxlength="32"
                            list="spot-kinds" />
                        </label>
                        <label class="check">
                          <input v-model="selectedSpot.keep" type="checkbox" /> A spot people can be
                          at
                        </label>
                      </div>
                      <p v-else key="none" class="card__note">
                        <IconInfo :size="14" /> Click a pin to edit it.
                      </p>
                    </Transition>
                    <p class="card__note">
                      {{ keptCount }} of {{ board.spots.length }} spots kept.
                    </p>
                  </aside>
                </div>
                <datalist id="spot-kinds">
                  <option
                    v-for="k in [
                      'inn',
                      'tavern',
                      'house',
                      'hall',
                      'market',
                      'square',
                      'smithy',
                      'workshop',
                      'mill',
                      'farm',
                      'chapel',
                      'temple',
                      'yard',
                      'barracks',
                      'gate',
                      'tower',
                      'dock',
                      'well',
                      'garden'
                    ]"
                    :key="k"
                    :value="k" />
                </datalist>
              </section>
            </Transition>
          </div>
          <p v-else key="missing" class="card__note">
            <IconInfo :size="14" /> This world has no place called “{{ placeKey }}”.
          </p>
        </Transition>
      </template>
    </template>

    <SaveBar
      v-if="board && !readonly && place"
      :dirty="dirty"
      :saved="savedFlash"
      secondary-label="Discard"
      @secondary="showPlace">
      <template #end>
        <span v-if="problem && dirty" class="problem">{{ problem }}</span>
        <button
          ref="saveBtn"
          type="button"
          class="cta cta--foot"
          :disabled="!dirty || !!problem || busy !== ''"
          @click="save">
          <span v-if="busy === 'save'" class="spin ev-progress-spin" aria-hidden="true" />
          {{ busy === 'save' ? 'Saving…' : `Save ${place.name}'s map` }}
        </button>
      </template>
    </SaveBar>
  </main>
</template>

<style scoped>
.pmap {
  max-width: 1200px;
  margin: 0 auto;
  padding: 14px 16px 40px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.pmap__back {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 14.5px;
  color: var(--teal-ink);
  margin-bottom: 8px;
}
.pmap__alert {
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
.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  border-radius: 999px;
  border: 1px solid var(--line-strong);
  background: var(--surface);
  color: var(--ink-2);
  font: 600 14.5px var(--font-body);
  cursor: pointer;
  transition:
    background-color var(--dur) ease,
    border-color var(--dur) ease,
    color var(--dur) ease,
    translate var(--dur) var(--ease-settle),
    scale var(--dur-quick) var(--ease-out),
    box-shadow var(--dur) ease;
}
.chip:hover:not(:disabled) {
  translate: 0 -2px;
  box-shadow: 0 6px 12px -8px rgba(46, 39, 24, 0.5);
}
.chip:active:not(:disabled) {
  translate: 0 0;
  scale: 0.95;
}
.chip--on {
  background: var(--teal);
  border-color: var(--teal);
  color: var(--cream-on-teal);
}
.pmap__place {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.pmap__loading {
  align-items: center;
}
.batch__step {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.batch__row--done .batch__step {
  animation: ev-flash 1.4s var(--ease-out);
  border-radius: 6px;
}
.spin {
  display: inline-block;
  width: 13px;
  height: 13px;
  flex: none;
  border-radius: 50%;
  border: 2px solid currentColor;
  border-right-color: transparent;
  opacity: 0.85;
  animation: pmap-spin 0.8s linear infinite;
}
.spin--sm {
  width: 11px;
  height: 11px;
}
@keyframes pmap-spin {
  to {
    transform: rotate(360deg);
  }
}
.batch {
  list-style: none;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 6px 18px;
}
.batch__row {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 10px;
  min-width: 0;
}
.batch__row .check small {
  color: var(--muted);
}
.batch__step {
  font-size: 13.5px;
  color: var(--muted);
  white-space: nowrap;
}
.batch__row--done .batch__step {
  color: var(--teal-ink);
}
.batch__row--failed .batch__step {
  color: #b3542e;
  white-space: normal;
}
.chip:disabled {
  opacity: 0.5;
  cursor: not-allowed;
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
  animation: pmap-toggle 0.36s var(--ease-spring);
}
@keyframes pmap-toggle {
  40% {
    scale: 1.05;
  }
}
.danger {
  color: #b3542e;
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
.boardwrap {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 260px;
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
.mapframe img {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
}
/* a new picture develops in place, like a print coming up */
.mapframe__pic {
  animation: ev-push-in 0.9s var(--ease-settle) both;
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
/* a spot drops onto the picture with a small bounce */
.pin__dot {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: #6fcf97;
  border: 2px solid #2e2718;
  flex: none;
  animation: pmap-drop 0.5s var(--ease-spring) both;
  transition:
    scale 0.28s var(--ease-spring),
    box-shadow var(--dur) ease;
}
.pin__label {
  animation: ev-fade 0.4s var(--ease-out) 0.15s both;
  transition: translate var(--dur) var(--ease-settle);
}
.mapframe--fresh-pins .pin__dot {
  animation-delay: calc(var(--i, 0) * 0.04s);
}
.mapframe--fresh-pins .pin__label {
  animation-delay: calc(0.15s + var(--i, 0) * 0.04s);
}
.pin:hover .pin__dot {
  scale: 1.3;
}
.pin:hover .pin__label {
  translate: 2px 0;
}
@keyframes pmap-drop {
  from {
    opacity: 0;
    translate: 0 -16px;
    scale: 0.4;
  }
}
@keyframes pmap-ring {
  0%,
  100% {
    box-shadow: 0 0 0 4px rgba(31, 106, 94, 0.55);
  }
  50% {
    box-shadow: 0 0 0 7px rgba(31, 106, 94, 0.25);
  }
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
  animation:
    pmap-drop 0.5s var(--ease-spring) both,
    pmap-ring 1.8s var(--ease-sine) 0.5s infinite;
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
.problem {
  color: #b3542e;
  font-weight: 600;
  font-size: 14px;
}
@media (max-width: 900px) {
  .boardwrap {
    grid-template-columns: 1fr;
  }
}
</style>
