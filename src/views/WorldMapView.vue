<!--
  WorldMapView — draw a world from its map: bring a picture (upload, paint
  or a blank parchment), let the map reader find the places and trace the
  roads or put them down by hand, fix what it got wrong, then say how long
  the shortest and the longest road take. Roads are drawn stretch by
  stretch: click a place, click each bend, click the place it reaches.
  Saving pins the places, adds new ones and times every road (a new world
  revision). Pure board logic: src/game/worldMap.ts.
-->
<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
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
  readTerrain,
  paintMap,
  readMapPlaces,
  readMapRoads,
  saveWorldMap,
  uploadMap
} from '../api/worldsim'
import { isVersionConflict } from '../api/http'
import { burst, shake } from '../composables/useEffects'
import type { PresetDetail } from '../../content/clients/worldsim'
import { parchmentDataUrl } from '../game/parchment'
import {
  blankTerrain,
  paintTerrain,
  TERRAIN_KINDS,
  terrainKind,
  terrainShares
} from '../game/terrain'
import {
  MAX_BENDS,
  PHASES_PER_DAY,
  SNAP,
  boardFromPreset,
  describePhases,
  keptPlaces,
  liveRoads,
  mapPrompt,
  nearestPlace,
  placesFromReading,
  roadLine,
  roadProblem,
  roadsFromReading,
  saveProblem,
  saveRequest,
  savedScale,
  stretchMiddles,
  timedRoads,
  toPhases,
  withBend,
  worldPlaces,
  type Board,
  type BoardPlace,
  type BoardRoad,
  type Point,
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
const busy = ref<
  '' | 'upload' | 'paint' | 'parchment' | 'places' | 'roads' | 'terrain' | 'save' | 'copy'
>('')
const error = ref<string | null>(null)
const notice = ref<string | null>(null)
const savedFlash = ref(false)
const selected = ref<string | null>(null)
/** What a click on the map does: pick, put down a place, or draw a road. */
const tool = ref<'select' | 'place' | 'road' | 'terrain'>('select')
const placing = computed(() => tool.value === 'place')
/** The road being drawn: the place it starts at and its bends so far. */
const drawing = ref<{ from: string; bends: Point[] } | null>(null)
/** Where the pointer is over the map, for the stretch being drawn. */
const cursor = ref<Point | null>(null)
const roadNote = ref<string | null>(null)
const selectedRoad = ref<BoardRoad | null>(null)
/** The bend being dragged on the selected road. */
const draggingBend = ref<number | null>(null)
const frameEl = ref<HTMLElement | null>(null)
const dragging = ref<string | null>(null)
const showPaint = ref(false)
const paintPrompt = ref('')
const paintRatio = ref('16:9')
const connectTo = ref('')
const connectBy = ref('road')
const ROAD_KINDS = ['road', 'path', 'sea', 'river', 'bridge', 'pass']

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
/** The place a click would reach while drawing (snapped). */
const snapTarget = computed(() =>
  board.value && drawing.value && cursor.value
    ? nearestPlace(board.value, cursor.value, SNAP, drawing.value.from)
    : null
)
/** The road being drawn, up to the pointer (or the place it would snap to). */
const drawnLine = computed(() => {
  if (!board.value || !drawing.value) return ''
  const from = board.value.places.find((p) => p.id === drawing.value!.from)
  if (!from) return ''
  const end = snapTarget.value?.point ?? cursor.value
  return [from.point, ...drawing.value.bends, ...(end ? [end] : [])]
    .map(([x, y]) => `${x},${y}`)
    .join(' ')
})
const selectedLine = computed<Point[]>(() =>
  board.value && selectedRoad.value ? roadLine(board.value, selectedRoad.value) : []
)
const selectedMiddles = computed(() =>
  selectedRoad.value && selectedRoad.value.points.length < MAX_BENDS
    ? stretchMiddles(selectedLine.value)
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

function resetTools(): void {
  tool.value = 'select'
  drawing.value = null
  selectedRoad.value = null
  roadNote.value = null
}

function adopt(view: PresetDetail): void {
  resetTools()
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
  resetTools()
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

/** The world's own picture (from the studio), when it has one. */
const worldPicture = computed(() => {
  const cover = (detail.value?.revision as Record<string, unknown> | undefined)?.['cover'] as
    { asset_id?: unknown } | null | undefined
  return typeof cover?.asset_id === 'string' ? cover.asset_id : null
})

/** Start from the world's own picture: kept again as a map the reader can read. */
async function useWorldPicture(): Promise<void> {
  if (!worldPicture.value) return
  busy.value = 'upload'
  error.value = null
  try {
    const blob = await (await fetch(libraryAssetUrl(worldPicture.value))).blob()
    const dataUrl = await new Promise<string>((resolve, reject) => {
      const reader = new FileReader()
      reader.onload = () => resolve(String(reader.result))
      reader.onerror = () => reject(new Error('Could not read the picture.'))
      reader.readAsDataURL(blob)
    })
    newBoard(await uploadMap(dataUrl))
    notice.value =
      'The world’s picture is the map now. Find the places on it, or put them down yourself.'
  } catch (err) {
    error.value = message(err, 'Could not use the world’s picture.')
  } finally {
    busy.value = ''
  }
}

/** No picture: start on an empty parchment and put everything down by hand. */
async function blankParchment(): Promise<void> {
  busy.value = 'parchment'
  error.value = null
  try {
    newBoard(await uploadMap(parchmentDataUrl()))
    notice.value =
      'A blank parchment. Add the places where you want them, then draw the roads between them.'
  } catch (err) {
    error.value = message(err, 'Could not lay out a parchment.')
  } finally {
    busy.value = ''
  }
}

async function findPlaces(): Promise<void> {
  if (!board.value) return
  busy.value = 'places'
  error.value = null
  try {
    const reading = await readMapPlaces(
      board.value.assetId,
      places.value.map((p) => p.name)
    )
    board.value.places = placesFromReading(reading.places, places.value)
    board.value.roads = []
    selected.value = null
    resetTools()
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
    selectedRoad.value = null
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

/* terrain ------------------------------------------------------------------- */
/** The terrain shows over the map while painting it, or when asked to. */
const showTerrain = ref(false)
const brush = ref('f')
const brushSize = ref(0)
let paintingTerrain = false
const terrainCells = computed(() => {
  const t = board.value?.terrain
  if (!t || !(showTerrain.value || tool.value === 'terrain')) return []
  const w = 1000 / t.cols
  const h = 1000 / t.rows
  return t.cells.split('').map((letter, i) => ({
    x: (i % t.cols) * w,
    y: Math.floor(i / t.cols) * h,
    w,
    h,
    fill: terrainKind(letter).colour
  }))
})
const terrainLegend = computed(() =>
  board.value?.terrain ? terrainShares(board.value.terrain).filter((s) => s.share >= 0.01) : []
)

/** The map reader drafts the terrain: about 24 cells across, as tall as the map is. */
async function readTheTerrain(): Promise<void> {
  if (!board.value) return
  busy.value = 'terrain'
  error.value = null
  const shape = blankTerrain(board.value.width, board.value.height)
  try {
    const read = await readTerrain(board.value.assetId, shape.cols, shape.rows)
    if (!read.terrain) throw new Error('The map reader saw no terrain on this picture.')
    board.value.terrain = read.terrain
    showTerrain.value = true
    notice.value =
      `Read the terrain in ${Math.round(Number(read.seconds))} s ($${Number(read.cost_usd).toFixed(4)}). ` +
      'It is a first draft: paint over what it got wrong.'
  } catch (err) {
    error.value = message(err, 'The map reader could not read the terrain.')
  } finally {
    busy.value = ''
  }
}

function blankTheTerrain(): void {
  if (!board.value) return
  board.value.terrain = blankTerrain(board.value.width, board.value.height)
  showTerrain.value = true
  if (tool.value !== 'terrain') setTool('terrain')
}

function clearTheTerrain(): void {
  if (!board.value) return
  board.value.terrain = null
  if (tool.value === 'terrain') setTool('terrain')
}

function paintAt(event: PointerEvent): void {
  const t = board.value?.terrain
  const point = pointFrom(event)
  if (!board.value || !t || !point) return
  board.value.terrain = paintTerrain(t, point, brush.value, brushSize.value)
}

function onFrameDown(event: PointerEvent): void {
  if (tool.value !== 'terrain' || !board.value?.terrain) return
  paintingTerrain = true
  frameEl.value?.setPointerCapture(event.pointerId)
  paintAt(event)
}

function onFrameClick(event: PointerEvent): void {
  if (!board.value) return
  if (tool.value === 'terrain') return
  const point = pointFrom(event)
  if (!point) return
  if (tool.value === 'road') {
    roadClick(point)
    return
  }
  if (draggedBend) {
    draggedBend = false
    return
  }
  if (tool.value === 'select') {
    selected.value = null
    selectedRoad.value = null
    return
  }
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
  tool.value = 'select'
}

/* drawing roads ------------------------------------------------------------ */
function setTool(next: 'select' | 'place' | 'road' | 'terrain'): void {
  tool.value = tool.value === next ? 'select' : next
  drawing.value = null
  roadNote.value =
    tool.value === 'road'
      ? 'Click the place the road starts at, then each bend, then the place it reaches.'
      : null
  if (tool.value !== 'select') selectedRoad.value = null
}

/** A click on the map while drawing: start, bend, or reach a place. */
function roadClick(point: Point): void {
  if (!board.value) return
  const near = nearestPlace(board.value, point, SNAP, drawing.value?.from ?? null)
  if (near) {
    roadAt(near)
    return
  }
  if (!drawing.value) {
    roadNote.value = 'A road starts at a place: click one of the pins.'
    return
  }
  if (drawing.value.bends.length >= MAX_BENDS) {
    roadNote.value = `A road has at most ${MAX_BENDS} bends: finish it at a place.`
    return
  }
  drawing.value.bends.push(point)
  roadNote.value = 'Keep clicking bends, or click the place it reaches. Backspace undoes a bend.'
}

/** A place clicked while drawing: the start, or the end of the road. */
function roadAt(place: BoardPlace): void {
  if (!board.value) return
  if (!place.keep) {
    roadNote.value = `${place.name} is left off the world: tick "A place to go" first.`
    return
  }
  if (!drawing.value) {
    drawing.value = { from: place.id, bends: [] }
    roadNote.value = `From ${place.name}: click each bend, then the place it reaches.`
    return
  }
  if (place.id === drawing.value.from) return
  const { from, bends } = drawing.value
  const problem = roadProblem(board.value, from, place.id, bends.length)
  if (problem) {
    roadNote.value = problem
    return
  }
  const road: BoardRoad = { a: from, b: place.id, by: connectBy.value, points: [...bends] }
  board.value.roads.push(road)
  drawing.value = null
  roadNote.value =
    `Road drawn: ${nameOf(from)} to ${place.name}` +
    (bends.length ? ` with ${bends.length} bend${bends.length === 1 ? '' : 's'}.` : '.') +
    ' Click a place to start the next one.'
}

/** Backspace takes back the last bend (or the start); Escape stops drawing. */
function onKey(event: KeyboardEvent): void {
  const target = event.target as HTMLElement | null
  if (target && ['INPUT', 'SELECT', 'TEXTAREA'].includes(target.tagName)) return
  if (tool.value !== 'road') return
  if (event.key === 'Escape') {
    event.preventDefault()
    if (drawing.value) {
      drawing.value = null
      roadNote.value = 'Stopped. Click a place to start a road.'
    } else setTool('road')
  } else if (event.key === 'Backspace' && drawing.value) {
    event.preventDefault()
    if (drawing.value.bends.length) drawing.value.bends.pop()
    else drawing.value = null
  }
}

/* editing a drawn road ------------------------------------------------------ */
function pickRoad(road: BoardRoad): void {
  if (tool.value !== 'select') return
  selectedRoad.value = road
  selected.value = null
}

/** Whether the grabbed bend has moved (a still press is a click, or half a double-click). */
let bendMoved = false

function grabBend(index: number): void {
  draggingBend.value = index
  bendMoved = false
}

/** Pull a new bend out of a stretch's middle and keep dragging it. */
function grabMiddle(event: PointerEvent, stretch: number): void {
  const road = selectedRoad.value
  const point = selectedMiddles.value[stretch]
  if (!road || !point) return
  road.points = withBend(road.points, stretch, point)
  grabBend(stretch)
  // The dot pressed is gone (it became the bend): the map takes the pointer now.
  bendMoved = true
  frameEl.value?.setPointerCapture(event.pointerId)
}

function removeBend(index: number): void {
  const road = selectedRoad.value
  if (!road) return
  road.points = road.points.filter((_, i) => i !== index)
}

function removeSelectedRoad(): void {
  if (!board.value || !selectedRoad.value) return
  const road = selectedRoad.value
  board.value.roads = board.value.roads.filter((r) => r !== road)
  selectedRoad.value = null
}

function onFrameMove(event: PointerEvent): void {
  if (paintingTerrain) return paintAt(event)
  if (tool.value === 'road' && drawing.value) cursor.value = pointFrom(event)
  if (draggingBend.value === null || !selectedRoad.value) return
  const point = pointFrom(event)
  if (!point) return
  if (!bendMoved) {
    // Only a real drag takes the pointer: a still press stays a click on the bend.
    bendMoved = true
    frameEl.value?.setPointerCapture(event.pointerId)
  }
  const at = draggingBend.value
  selectedRoad.value.points = selectedRoad.value.points.map((p, i) => (i === at ? point : p))
}

/** The click that ends a bend drag lands on the map: it must not deselect. */
let draggedBend = false

function onFrameUp(): void {
  paintingTerrain = false
  dragging.value = null
  if (draggingBend.value !== null && bendMoved) draggedBend = true
  draggingBend.value = null
}

function onPinClick(place: BoardPlace): void {
  if (tool.value === 'road') roadAt(place)
  else {
    selected.value = place.id
    selectedRoad.value = null
  }
}

function startDrag(event: PointerEvent, place: BoardPlace): void {
  if (tool.value === 'road') return
  selected.value = place.id
  selectedRoad.value = null
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
  if (selectedRoad.value === road) selectedRoad.value = null
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

/* ————— motion: what just arrived on the map announces itself ————— */
const saveBtn = ref<HTMLElement | null>(null)
const alertEl = ref<HTMLElement | null>(null)
/** A fresh batch of pins (read or loaded) drops in one after another. */
const freshPins = ref(false)
/** Fresh roads spread out over the map; fresh terrain washes across it. */
const freshRoads = ref(false)
const freshTerrain = ref(false)
const timers: ReturnType<typeof setTimeout>[] = []
function fresh(flag: typeof freshPins, ms: number): void {
  flag.value = false
  requestAnimationFrame(() => {
    flag.value = true
    timers.push(setTimeout(() => (flag.value = false), ms))
  })
}
watch(
  () => board.value?.places,
  (now, before) => {
    if (now && now !== before && now.length > 1 && busy.value !== 'save') fresh(freshPins, 1600)
  }
)
watch(
  () => board.value?.roads,
  (now, before) => {
    if (now && now !== before && now.length && busy.value !== 'save') fresh(freshRoads, 1600)
  }
)
watch(
  () => board.value?.terrain,
  (now, before) => {
    if (now && now !== before && busy.value !== 'save') fresh(freshTerrain, 1400)
  }
)
watch(error, (now) => {
  if (now) requestAnimationFrame(() => shake(alertEl.value))
})
onBeforeUnmount(() => timers.forEach(clearTimeout))

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
    burst(saveBtn.value, { count: 18, spread: 90 })
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

onMounted(() => {
  void load()
  window.addEventListener('keydown', onKey)
})
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))
</script>

<template>
  <main class="wmap ev-rise">
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

    <Transition name="ev-rise">
      <p v-if="error" ref="alertEl" class="wmap__alert" role="alert">{{ error }}</p>
    </Transition>
    <p v-if="loading" class="ev-info wmap__loading">
      <span class="spin ev-progress-spin" aria-hidden="true" /> Loading…
    </p>

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
                Upload a map you made, or paint one. Clear roads and labels help the map reader. No
                picture? Start on a blank parchment and draw the places and roads yourself.
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
            <button
              v-if="worldPicture && board?.assetId !== worldPicture"
              type="button"
              class="ghost"
              :disabled="busy !== ''"
              @click="useWorldPicture">
              <IconImage :size="14" /> Use the world’s picture
            </button>
            <button type="button" class="ghost" :disabled="busy !== ''" @click="blankParchment">
              {{ busy === 'parchment' ? 'Laying it out…' : 'Blank parchment' }}
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
                <button type="button" class="cta cta--sm" :disabled="busy !== ''" @click="paint">
                  <span v-if="busy === 'paint'" class="spin ev-progress-spin" aria-hidden="true" />
                  {{ busy === 'paint' ? 'Painting… (up to a minute)' : 'Paint the map' }}
                </button>
              </div>
            </div>
          </Transition>
        </section>

        <!-- board -------------------------------------------------------------- -->
        <Transition name="ev-rise">
          <section v-if="board" class="card ev-card">
            <header class="card__head">
              <span class="card__icon"><IconGlobe :size="20" /></span>
              <div>
                <h2 class="card__title">2 · Places and roads</h2>
                <p class="card__sub">
                  Drag a pin to move it, click one to rename it. Draw a road by clicking a place,
                  each bend, then the place it reaches; click a road to move its bends.
                  <template v-if="board.places.length === 0">
                    Start by finding the places, or add them by hand.
                  </template>
                </p>
              </div>
            </header>
            <div class="row">
              <button type="button" class="cta cta--sm" :disabled="busy !== ''" @click="findPlaces">
                <span v-if="busy === 'places'" class="spin ev-progress-spin" aria-hidden="true" />
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
                <span v-if="busy === 'roads'" class="spin ev-progress-spin" aria-hidden="true" />
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
                :aria-pressed="placing"
                :disabled="busy !== ''"
                @click="setTool('place')">
                <IconPlus :size="14" /> {{ placing ? 'Click the map to place it' : 'Add a place' }}
              </button>
              <button
                type="button"
                class="ghost"
                :class="{ 'is-on': tool === 'road' }"
                :aria-pressed="tool === 'road'"
                :disabled="busy !== '' || keptCount < 2"
                @click="setTool('road')">
                <IconBranch :size="14" /> {{ tool === 'road' ? 'Done drawing' : 'Draw a road' }}
              </button>
              <select
                v-if="tool === 'road'"
                v-model="connectBy"
                class="ev-input small"
                aria-label="Kind of road to draw">
                <option v-for="k in ROAD_KINDS" :key="k" :value="k">{{ k }}</option>
              </select>
              <button
                type="button"
                class="ghost"
                :class="{ 'is-on': tool === 'terrain' }"
                :aria-pressed="tool === 'terrain'"
                :disabled="busy !== ''"
                @click="board.terrain ? setTool('terrain') : blankTheTerrain()">
                <IconGlobe :size="14" />
                {{ tool === 'terrain' ? 'Done with the terrain' : 'Terrain' }}
              </button>
            </div>

            <Transition name="ev-swap" mode="out-in">
              <div v-if="tool === 'terrain'" class="terrainbar" role="group" aria-label="Terrain">
                <p class="terrainbar__lead">
                  What covers the land makes roads slower: a road over mountains takes about two and
                  a half times as long as one over plains. Paint by dragging over the map.
                </p>
                <div class="terrainbar__row">
                  <button
                    type="button"
                    class="cta cta--sm"
                    :disabled="busy !== ''"
                    @click="readTheTerrain">
                    <span
                      v-if="busy === 'terrain'"
                      class="spin ev-progress-spin"
                      aria-hidden="true" />
                    {{
                      busy === 'terrain' ? 'Reading the terrain… (about 10 s)' : 'Read the terrain'
                    }}
                  </button>
                  <button
                    type="button"
                    class="ghost ghost--sm"
                    :disabled="busy !== ''"
                    @click="blankTheTerrain">
                    Start blank
                  </button>
                  <button
                    v-if="board.terrain"
                    type="button"
                    class="ghost ghost--sm"
                    :disabled="busy !== ''"
                    @click="clearTheTerrain">
                    No terrain
                  </button>
                </div>
                <div
                  v-if="board.terrain"
                  class="terrainbar__row"
                  role="radiogroup"
                  aria-label="Paint with">
                  <button
                    v-for="k in TERRAIN_KINDS"
                    :key="k.letter"
                    type="button"
                    role="radio"
                    class="swatch"
                    :class="{ 'swatch--on': brush === k.letter }"
                    :aria-checked="brush === k.letter"
                    :title="`${k.name}: roads ×${k.cost}`"
                    @click="brush = k.letter">
                    <span class="swatch__colour" :style="{ background: k.colour }"></span>
                    {{ k.name }}
                  </button>
                  <label class="terrainbar__size">
                    Brush
                    <select
                      v-model.number="brushSize"
                      class="ev-input small"
                      aria-label="Brush size">
                      <option :value="0">1 cell</option>
                      <option :value="1">3 × 3</option>
                      <option :value="2">5 × 5</option>
                    </select>
                  </label>
                </div>
              </div>
              <label v-else-if="board.terrain" class="terrainbar__show">
                <input v-model="showTerrain" type="checkbox" /> Show the terrain
              </label>
            </Transition>
            <Transition name="ev-rise" mode="out-in">
              <p v-if="notice" :key="notice" class="card__note">
                <IconInfo :size="14" /> {{ notice }}
              </p>
            </Transition>
            <Transition name="ev-rise">
              <p v-if="roadNote" class="card__note card__note--road" role="status">
                <IconBranch :size="14" /> {{ roadNote }}
                <span v-if="tool === 'road'" class="keys">Backspace undoes a bend · Esc stops</span>
              </p>
            </Transition>

            <div class="boardwrap">
              <div
                ref="frameEl"
                class="mapframe"
                :class="{
                  'mapframe--placing': placing || tool === 'road',
                  'mapframe--painting': tool === 'terrain',
                  'mapframe--fresh-pins': freshPins,
                  'mapframe--fresh-roads': freshRoads,
                  'mapframe--fresh-terrain': freshTerrain
                }"
                :style="{ aspectRatio: aspect }"
                @pointerdown="onFrameDown"
                @pointermove="onFrameMove"
                @pointerup="onFrameUp"
                @pointerleave="cursor = null"
                @click="onFrameClick($event as PointerEvent)">
                <img :src="pictureUrl" :alt="`Map of ${worldName}`" draggable="false" />
                <svg
                  v-if="terrainCells.length"
                  class="terrain"
                  viewBox="0 0 1000 1000"
                  preserveAspectRatio="none"
                  aria-hidden="true">
                  <rect
                    v-for="(c, i) in terrainCells"
                    :key="i"
                    :x="c.x"
                    :y="c.y"
                    :width="c.w + 0.5"
                    :height="c.h + 0.5"
                    :fill="c.fill" />
                </svg>
                <svg
                  class="roads"
                  viewBox="0 0 1000 1000"
                  preserveAspectRatio="none"
                  aria-hidden="true">
                  <polyline
                    v-if="selectedLine.length"
                    :points="selectedLine.map(([x, y]) => `${x},${y}`).join(' ')"
                    class="road-halo"
                    fill="none"
                    stroke-width="10"
                    stroke-linejoin="round"
                    vector-effect="non-scaling-stroke" />
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
                  <!-- wide, invisible: what a click on a road lands on -->
                  <polyline
                    v-for="(line, i) in linesFor"
                    :key="`hit-${i}`"
                    :points="line.points"
                    class="road-hit"
                    :class="{ 'road-hit--live': tool === 'select' }"
                    fill="none"
                    stroke="transparent"
                    stroke-width="16"
                    vector-effect="non-scaling-stroke"
                    @click.stop="pickRoad(line.road)" />
                  <polyline
                    v-if="drawnLine"
                    class="road-drawing"
                    :points="drawnLine"
                    :stroke="colorOf(connectBy)"
                    stroke-dasharray="8 6"
                    fill="none"
                    stroke-width="4"
                    stroke-linejoin="round"
                    vector-effect="non-scaling-stroke" />
                </svg>
                <span
                  v-for="(b, i) in drawing?.bends ?? []"
                  :key="`drawn-${i}`"
                  class="bend bend--drawn"
                  :style="{ left: `${b[0] / 10}%`, top: `${b[1] / 10}%` }" />
                <template v-if="selectedRoad && tool === 'select'">
                  <button
                    v-for="(m, i) in selectedMiddles"
                    :key="`mid-${i}`"
                    type="button"
                    class="bend bend--middle"
                    :style="{ left: `${m[0] / 10}%`, top: `${m[1] / 10}%` }"
                    :aria-label="`Add a bend to this stretch`"
                    title="Drag to add a bend"
                    @click.stop
                    @pointerdown.stop.prevent="grabMiddle($event, i)" />
                  <button
                    v-for="(b, i) in selectedRoad.points"
                    :key="`bend-${i}`"
                    type="button"
                    class="bend"
                    :style="{ left: `${b[0] / 10}%`, top: `${b[1] / 10}%` }"
                    :aria-label="`Bend ${i + 1}: drag to move, double-click or Delete to remove`"
                    title="Drag to move · double-click to remove"
                    @click.stop
                    @dblclick.stop="removeBend(i)"
                    @keydown.delete.prevent="removeBend(i)"
                    @keydown.backspace.prevent="removeBend(i)"
                    @pointerdown.stop.prevent="grabBend(i)" />
                </template>
                <button
                  v-for="(p, i) in board.places"
                  :key="p.id"
                  type="button"
                  class="pin"
                  :class="{
                    'pin--off': !p.keep,
                    'pin--on': p.id === selected || p.id === drawing?.from,
                    'pin--new': p.keep && !p.key,
                    'pin--target': p.id === snapTarget?.id
                  }"
                  :style="{
                    left: `${p.point[0] / 10}%`,
                    top: `${p.point[1] / 10}%`,
                    '--i': Math.min(i, 14)
                  }"
                  :title="p.name"
                  @click.stop="onPinClick(p)"
                  @pointerdown.stop="startDrag($event, p)"
                  @pointermove="onDrag($event, p)"
                  @pointerup="dragging = null">
                  <span class="pin__dot"></span>
                  <span class="pin__label">{{ p.name }}</span>
                </button>
              </div>

              <aside class="side">
                <Transition name="ev-swap" mode="out-in">
                  <div
                    v-if="selectedRoad"
                    :key="`road-${selectedRoad.a}-${selectedRoad.b}`"
                    class="inspect">
                    <p class="field__label">
                      {{ nameOf(selectedRoad.a) }} — {{ nameOf(selectedRoad.b) }}
                    </p>
                    <label class="field">
                      <span class="field__label">By</span>
                      <select v-model="selectedRoad.by" class="ev-input">
                        <option v-for="k in ROAD_KINDS" :key="k" :value="k">{{ k }}</option>
                      </select>
                    </label>
                    <p class="card__note">
                      <IconInfo :size="14" />
                      {{ selectedRoad.points.length }} of {{ MAX_BENDS }} bends. Drag a bend to move
                      it, drag a hollow dot to add one, double-click a bend to remove it.
                    </p>
                    <div class="row">
                      <button
                        type="button"
                        class="ghost"
                        :disabled="!selectedRoad.points.length"
                        @click="selectedRoad.points = []">
                        Straighten
                      </button>
                      <button type="button" class="ghost danger" @click="removeSelectedRoad">
                        Remove this road
                      </button>
                    </div>
                  </div>
                  <div v-else-if="selectedPlace" :key="`place-${selectedPlace.id}`" class="inspect">
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
                  <p v-else key="none" class="card__note">
                    <IconInfo :size="14" /> Click a pin or a road to edit it.
                  </p>
                </Transition>

                <ul class="legend">
                  <li><span class="sw sw--new"></span> New place</li>
                  <li><span class="sw"></span> Already in the world</li>
                  <li><span class="sw sw--off"></span> Left off</li>
                </ul>
                <ul
                  v-if="terrainLegend.length && (showTerrain || tool === 'terrain')"
                  class="legend">
                  <li v-for="t in terrainLegend" :key="t.kind.letter">
                    <span class="sw" :style="{ background: t.kind.colour }"></span>
                    {{ t.kind.name }} · {{ Math.round(t.share * 100) }}%
                  </li>
                </ul>
              </aside>
            </div>
          </section>
        </Transition>

        <!-- travel -------------------------------------------------------------- -->
        <Transition name="ev-rise">
          <section v-if="board && board.places.length" class="card ev-card">
            <header class="card__head">
              <span class="card__icon"><IconClock :size="20" /></span>
              <div>
                <h2 class="card__title">3 · Travel time</h2>
                <p class="card__sub">
                  Say how long the shortest and the longest road take; every other road scales with
                  its length on the map{{
                    board.terrain ? ', weighed by the terrain it crosses' : ''
                  }}. A day has {{ PHASES_PER_DAY }} phases, dawn to midnight.
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
            <Transition name="ev-rise">
              <p v-if="scaleProblem" class="over">{{ scaleProblem }}</p>
            </Transition>
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
                <TransitionGroup name="ev-list" tag="tbody">
                  <tr v-for="(t, i) in timed" :key="`${t.road.a}-${t.road.b}`">
                    <td>
                      <button
                        type="button"
                        class="roadname"
                        :class="{ 'is-on': t.road === selectedRoad }"
                        @click="((tool = 'select'), pickRoad(t.road))">
                        <IconBranch :size="13" /> {{ nameOf(t.road.a) }} — {{ nameOf(t.road.b) }}
                      </button>
                    </td>
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
                </TransitionGroup>
              </table>
              <p v-else class="card__note">
                <IconInfo :size="14" /> No roads yet: trace them, or connect places by hand.
              </p>
            </div>
          </section>
        </Transition>
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
          ref="saveBtn"
          type="button"
          class="cta cta--foot"
          :disabled="!dirty || !!problem || busy !== ''"
          @click="save">
          <span v-if="busy === 'save'" class="spin ev-progress-spin" aria-hidden="true" />
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
/* fresh roads spread out from the middle of the map */
.mapframe--fresh-roads svg.roads {
  animation: wmap-roads-in 1.2s var(--ease-io) both;
}
/* fresh terrain washes across the map from west to east */
.mapframe--fresh-terrain svg.terrain {
  animation: wmap-wash 1.1s var(--ease-io) both;
}
/* the selected road glows, breathing */
.road-halo {
  stroke: rgba(255, 252, 240, 0.9);
  animation: wmap-halo 2s var(--ease-sine) infinite;
}
/* the road being drawn marches toward the pointer */
.road-drawing {
  animation: wmap-march 0.8s linear infinite;
}
.road-hit--live {
  pointer-events: stroke;
  cursor: pointer;
}
.bend {
  position: absolute;
  width: 14px;
  height: 14px;
  transform: translate(-50%, -50%);
  border-radius: 50%;
  background: #fff;
  border: 2px solid #2e2718;
  cursor: move;
  touch-action: none;
  padding: 0;
  animation: wmap-pop 0.4s var(--ease-spring) both;
  transition: scale var(--dur-quick) var(--ease-out);
}
.bend:hover {
  scale: 1.25;
}
.bend:focus-visible {
  outline: 3px solid var(--gold-soft);
}
.bend--middle {
  width: 11px;
  height: 11px;
  background: rgba(255, 255, 255, 0.35);
  border-style: dashed;
  cursor: copy;
}
.bend--drawn {
  width: 9px;
  height: 9px;
  pointer-events: none;
}
.pin--target .pin__dot {
  box-shadow: 0 0 0 5px rgba(242, 201, 76, 0.7);
}
.card__note--road {
  color: var(--teal-ink);
  flex-wrap: wrap;
}
.keys {
  color: var(--muted);
  font-size: 12.5px;
}
.roadname {
  display: inline-flex;
  gap: 6px;
  align-items: center;
  text-align: left;
  color: inherit;
  padding: 2px 4px;
  border-radius: 6px;
}
.roadname:hover,
.roadname.is-on {
  color: var(--teal-ink);
  background: rgba(31, 106, 94, 0.08);
}
.danger {
  color: #b3542e;
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
/* a pin drops onto the parchment with a small bounce */
.pin__dot {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: #f2c94c;
  border: 2px solid #2e2718;
  flex: none;
  animation: wmap-drop 0.5s var(--ease-spring) both;
  transition:
    scale 0.28s var(--ease-spring),
    box-shadow var(--dur) ease,
    background-color var(--dur) ease;
}
.pin__label {
  animation: ev-fade 0.4s var(--ease-out) 0.15s both;
  transition: translate var(--dur) var(--ease-settle);
}
/* a batch read from the map lands one pin after another */
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
.pin:active .pin__dot {
  scale: 1.1;
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
  animation:
    wmap-drop 0.5s var(--ease-spring) both,
    wmap-ring 1.8s var(--ease-sine) 0.5s infinite;
}
.pin--target .pin__dot {
  scale: 1.3;
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
  animation: wmap-spin 0.8s linear infinite;
}
.wmap__loading {
  align-items: center;
}
.is-on {
  animation: wmap-toggle 0.36s var(--ease-spring);
}
@keyframes wmap-spin {
  to {
    transform: rotate(360deg);
  }
}
@keyframes wmap-toggle {
  40% {
    scale: 1.05;
  }
}
@keyframes wmap-drop {
  from {
    opacity: 0;
    translate: 0 -16px;
    scale: 0.4;
  }
}
@keyframes wmap-pop {
  from {
    opacity: 0;
    scale: 0.3;
  }
}
@keyframes wmap-ring {
  0%,
  100% {
    box-shadow: 0 0 0 4px rgba(31, 106, 94, 0.55);
  }
  50% {
    box-shadow: 0 0 0 7px rgba(31, 106, 94, 0.25);
  }
}
@keyframes wmap-halo {
  0%,
  100% {
    stroke-opacity: 0.95;
  }
  50% {
    stroke-opacity: 0.55;
  }
}
@keyframes wmap-march {
  to {
    stroke-dashoffset: -28;
  }
}
@keyframes wmap-roads-in {
  from {
    clip-path: circle(0% at 50% 50%);
  }
  to {
    clip-path: circle(75% at 50% 50%);
  }
}
@keyframes wmap-wash {
  from {
    clip-path: inset(0 100% 0 0);
  }
  to {
    clip-path: inset(0 0 0 0);
  }
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
/* terrain -------------------------------------------------------------------- */
.mapframe svg.terrain {
  opacity: 0.5;
  pointer-events: none;
}
/* while painting, the colours are stronger and each cell shows its edge */
.mapframe--painting svg.terrain {
  opacity: 0.66;
}
.mapframe--painting svg.terrain rect {
  stroke: rgba(40, 30, 10, 0.28);
  stroke-width: 1;
  vector-effect: non-scaling-stroke;
}
.mapframe--painting {
  cursor: crosshair;
  touch-action: none;
}
.terrainbar {
  display: grid;
  gap: 10px;
  margin-top: 12px;
  padding: 12px 14px;
  border-radius: 12px;
  border: 1px dashed var(--line-strong);
  background: #fbf3e2;
}
.terrainbar__lead {
  font-size: 15px;
  color: var(--ink-2);
}
.terrainbar__row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}
.terrainbar__size,
.terrainbar__show {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-family: var(--font-ui);
  font-size: 15px;
}
.terrainbar__show {
  margin-top: 10px;
}
.swatch {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  height: 34px;
  padding: 0 11px 0 7px;
  border-radius: 999px;
  border: 1px solid var(--line);
  background: #fffaf0;
  font-size: 14.5px;
  color: var(--ink-2);
  transition:
    border-color 0.15s ease,
    box-shadow 0.15s ease;
}
.swatch__colour {
  width: 18px;
  height: 18px;
  border-radius: 50%;
  border: 1px solid rgba(0, 0, 0, 0.2);
}
.swatch--on {
  border-color: var(--teal-ink);
  box-shadow: 0 0 0 2px rgba(31, 106, 94, 0.25);
  color: var(--teal);
  font-weight: 700;
}
</style>
