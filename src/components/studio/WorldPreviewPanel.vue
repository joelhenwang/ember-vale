<!--
  WorldPreviewPanel — the world studio's right column.
    World    the world's own picture, painted as a map or imported, framed as
             the 16:7 banner cards show; and, once the world exists, its
             drawn map with links to pin places and draw roads
    Place    one picture per place, painted or imported; it becomes the
             place's own map (the inside of the place), so the world must
             exist and the place be published first
    Summary  the facts as they stand
-->
<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { PresetDetail } from '../../../content/clients/worldsim'
import {
  getPreset,
  libraryAssetUrl,
  paintMap,
  savePlaceMap,
  uploadCover,
  uploadMap
} from '../../api/worldsim'
import { fit, type Frame, type Size } from '../../game/framing'
import type { WorldCover, WorldDraft } from '../../game/studio'
import { placePrompt, worldMapPrompt } from '../../game/worldForm'
import FramedImage from '../ui/FramedImage.vue'
import PictureFramer, { type FrameStep, type PreviewShape } from '../ui/PictureFramer.vue'
import MapPreview from './MapPreview.vue'
import IconEmblem from '../icons/IconEmblem.vue'
import IconImage from '../icons/IconImage.vue'
import IconSparkle from '../icons/IconSparkle.vue'

const props = defineProps<{
  draft: WorldDraft
  name: string
  /** The saved world, once there is one. */
  presetId: string | null
}>()
const emit = defineEmits<{
  cover: [cover: WorldCover | null]
  /** A place picture made a new revision of the saved world. */
  saved: [head: PresetDetail]
}>()

const tab = ref<'world' | 'place' | 'summary'>('world')

function message(err: unknown, fallback: string): string {
  return err instanceof Error && err.message ? err.message : fallback
}
function readFile(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result))
    reader.onerror = () => reject(new Error('Could not read that file.'))
    reader.readAsDataURL(file)
  })
}
function sizeOf(url: string): Promise<Size> {
  return new Promise((resolve, reject) => {
    const img = new Image()
    img.onload = () => resolve({ width: img.naturalWidth, height: img.naturalHeight })
    img.onerror = () => reject(new Error('Could not open that picture.'))
    img.src = url
  })
}

/* ————— the world's picture ————— */
const worldBusy = ref<'' | 'paint' | 'import'>('')
const worldNote = ref<string | null>(null)
const worldError = ref<string | null>(null)
const framing = ref<{ assetId: string; src: string; size: Size } | null>(null)
const coverSrc = computed(() =>
  props.draft.cover ? libraryAssetUrl(props.draft.cover.assetId) : ''
)
const mapWords = computed(() => worldMapPrompt(props.draft, props.name))

const bannerSteps: FrameStep[] = [
  {
    key: 'banner',
    title: 'Banner',
    hint: 'Move the dashed frame over the part of the picture that says the most about this world, and drag its corners to size it.',
    ratio: 16 / 7
  }
]
const bannerPreviews: PreviewShape[] = [
  { label: 'Library card', step: 'banner', width: 240, height: 105 },
  { label: 'Story card', step: 'banner', width: 240, height: 141 }
]

async function paintWorld(): Promise<void> {
  if (worldBusy.value) return
  worldBusy.value = 'paint'
  worldError.value = null
  worldNote.value = null
  const started = performance.now()
  try {
    const made = await paintMap(mapWords.value, '16:9')
    const size = { width: made.width, height: made.height }
    emit('cover', { assetId: made.asset_id, frame: fit(16 / 7, size) })
    worldNote.value = `Painted in ${Math.round((performance.now() - started) / 1000)} s. Adjust the framing, or paint again.`
  } catch (err) {
    worldError.value = message(err, 'Could not paint the world this time.')
  } finally {
    worldBusy.value = ''
  }
}

async function importWorld(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  if (file.size > 16 * 1024 * 1024) {
    worldError.value = 'That picture is over 16 MB. Try a smaller one.'
    return
  }
  worldBusy.value = 'import'
  worldError.value = null
  try {
    const kept = await uploadCover(await readFile(file))
    framing.value = {
      assetId: kept.asset_id,
      src: libraryAssetUrl(kept.asset_id),
      size: { width: kept.width, height: kept.height }
    }
  } catch (err) {
    worldError.value = message(err, 'Could not import that picture.')
  } finally {
    worldBusy.value = ''
  }
}

async function adjustWorld(): Promise<void> {
  if (!props.draft.cover) return
  try {
    framing.value = {
      assetId: props.draft.cover.assetId,
      src: coverSrc.value,
      size: await sizeOf(coverSrc.value)
    }
  } catch (err) {
    worldError.value = message(err, 'Could not open the picture.')
  }
}

function framed(frames: Record<string, Frame>): void {
  if (!framing.value) return
  emit('cover', { assetId: framing.value.assetId, frame: frames['banner']! })
  framing.value = null
}
const bannerInitial = computed(() =>
  framing.value && props.draft.cover && framing.value.assetId === props.draft.cover.assetId
    ? { banner: props.draft.cover.frame }
    : null
)

/* ————— each place's picture ————— */
const saved = ref<PresetDetail | null>(null)
async function readSaved(): Promise<void> {
  if (!props.presetId) {
    saved.value = null
    return
  }
  try {
    saved.value = await getPreset(props.presetId, undefined)
  } catch {
    saved.value = null
  }
}
watch(() => props.presetId, readSaved, { immediate: true })

const placeId = ref<string | null>(null)
const place = computed(
  () => props.draft.places.find((p) => p.id === placeId.value) ?? props.draft.places[0] ?? null
)
const savedPlaces = computed(() => {
  const rev = (saved.value?.revision ?? {}) as Record<string, unknown>
  const list = (rev['locations'] as { key: string; map?: { asset_id?: string } | null }[]) ?? []
  return new Map(list.map((l) => [l.key, l.map?.asset_id ?? null]))
})
/** The place exists on the saved world (its picture can be kept). */
const placeSaved = computed(() => !!place.value && savedPlaces.value.has(place.value.key))
const placePicture = computed(() =>
  place.value ? (savedPlaces.value.get(place.value.key) ?? null) : null
)

const placeBusy = ref<'' | 'paint' | 'import' | 'remove'>('')
const placeNote = ref<string | null>(null)
const placeError = ref<string | null>(null)

async function keepPlacePicture(assetId: string | null): Promise<void> {
  if (!props.presetId || !place.value || !saved.value) return
  saved.value = await savePlaceMap(props.presetId, place.value.key, {
    asset_id: assetId,
    spots: [],
    expected_version: saved.value.version
  })
  emit('saved', saved.value)
}

async function paintPlace(): Promise<void> {
  if (!place.value || placeBusy.value) return
  placeBusy.value = 'paint'
  placeError.value = null
  placeNote.value = null
  const started = performance.now()
  try {
    const made = await paintMap(placePrompt(place.value, props.draft), '16:9')
    await keepPlacePicture(made.asset_id)
    placeNote.value = `Painted in ${Math.round((performance.now() - started) / 1000)} s and kept with the world.`
  } catch (err) {
    placeError.value = message(err, 'Could not paint the place this time.')
  } finally {
    placeBusy.value = ''
  }
}

async function importPlace(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file || !place.value) return
  placeBusy.value = 'import'
  placeError.value = null
  try {
    const kept = await uploadMap(await readFile(file))
    await keepPlacePicture(kept.asset_id)
    placeNote.value = 'Kept with the world.'
  } catch (err) {
    placeError.value = message(err, 'Could not import that picture.')
  } finally {
    placeBusy.value = ''
  }
}

async function removePlace(): Promise<void> {
  placeBusy.value = 'remove'
  placeError.value = null
  try {
    await keepPlacePicture(null)
    placeNote.value = null
  } catch (err) {
    placeError.value = message(err, 'Could not take the picture away.')
  } finally {
    placeBusy.value = ''
  }
}

/* ————— summary ————— */
const facts = computed(() => [
  { k: 'Terrain', v: props.draft.terrain.join(', ') },
  { k: 'Climate', v: props.draft.climate },
  { k: 'Architecture', v: props.draft.architecture },
  { k: 'Peoples', v: props.draft.peoples },
  { k: 'History', v: props.draft.history },
  { k: 'Distinctive details', v: props.draft.distinct },
  { k: 'Never here', v: props.draft.exclusions },
  { k: 'Places', v: props.draft.places.map((p) => p.name).join(' · ') }
])
</script>

<template>
  <aside class="card ev-card preview wpv" aria-label="World preview">
    <header class="wpv__head">
      <IconEmblem :size="22" class="wpv__emblem" />
      <h2 class="wpv__title">Preview</h2>
    </header>

    <div class="preview__tabs" role="tablist" aria-label="Preview sections">
      <button
        v-for="t in ['world', 'place', 'summary'] as const"
        :id="`wpanel-tab-${t}`"
        :key="t"
        type="button"
        role="tab"
        :aria-selected="tab === t"
        :aria-controls="`wpanel-panel-${t}`"
        :class="{ 'preview__tabs--on': tab === t }"
        @click="tab = t">
        {{ t === 'world' ? 'World' : t === 'place' ? 'Place' : 'Summary' }}
      </button>
    </div>

    <!-- world -->
    <div
      v-show="tab === 'world'"
      id="wpanel-panel-world"
      class="wpv__pane"
      role="tabpanel"
      aria-labelledby="wpanel-tab-world">
      <div class="wpv__pic" :class="{ 'wpv__pic--busy': worldBusy === 'paint' }">
        <FramedImage
          v-if="draft.cover"
          :src="coverSrc"
          :frame="draft.cover.frame"
          :alt="`${name}: the world`" />
        <span v-else class="wpv__nopic">
          <IconImage :size="30" />
          <span>No picture yet</span>
        </span>
      </div>
      <p class="wpv__lead">
        {{
          worldBusy === 'paint'
            ? 'Painting a map of the world… about fifteen seconds.'
            : 'A picture of the whole world: a map, painted from what you wrote, or one of your own.'
        }}
      </p>
      <div class="wpv__actions">
        <button
          type="button"
          class="cta"
          :disabled="!!worldBusy"
          :title="mapWords"
          @click="paintWorld">
          <IconSparkle :size="15" />
          {{
            worldBusy === 'paint' ? 'Painting…' : draft.cover ? 'Generate again' : 'Generate image'
          }}
        </button>
        <label class="ghost wpv__import">
          <input
            type="file"
            accept="image/png,image/jpeg,image/webp"
            :disabled="!!worldBusy"
            @change="importWorld" />
          <IconImage :size="15" /> Import image
        </label>
      </div>
      <div v-if="draft.cover" class="wpv__more">
        <button type="button" class="studio__link" @click="adjustWorld">Adjust the framing</button>
        <button type="button" class="studio__link wpv__remove" @click="emit('cover', null)">
          Remove the picture
        </button>
      </div>
      <p v-if="worldNote && !worldError" class="wpv__note" role="status">{{ worldNote }}</p>
      <p v-if="worldError" class="wpv__error" role="alert">{{ worldError }}</p>

      <template v-if="presetId">
        <div class="ev-divider wpv__rule" aria-hidden="true"><IconSparkle :size="11" /></div>
        <p class="ev-field-label">Its map</p>
        <MapPreview :preset-id="presetId" :revision="saved?.current_revision ?? null">
          <p class="wpv__lead">
            No places pinned yet. Pin them on a picture of the world and draw the roads between
            them, so travel takes the time the map says.
          </p>
        </MapPreview>
        <RouterLink
          class="ghost wpv__link"
          :to="{ name: 'library-world-map', params: { id: presetId } }">
          Pin the places and draw the roads
        </RouterLink>
      </template>
      <p v-else class="wpv__lead wpv__later">
        Once the world is created you can pin its places on a map and draw the roads.
      </p>
    </div>

    <!-- place -->
    <div
      v-show="tab === 'place'"
      id="wpanel-panel-place"
      class="wpv__pane"
      role="tabpanel"
      aria-labelledby="wpanel-tab-place">
      <div class="wpv__chips" role="group" aria-label="Places">
        <button
          v-for="p in draft.places"
          :key="p.id"
          type="button"
          class="wpv__chip"
          :class="{ 'wpv__chip--on': place?.id === p.id }"
          @click="placeId = p.id">
          {{ p.name }}
        </button>
      </div>
      <template v-if="place">
        <div class="wpv__pic" :class="{ 'wpv__pic--busy': placeBusy === 'paint' }">
          <img
            v-if="placePicture"
            class="wpv__img"
            :src="libraryAssetUrl(placePicture)"
            :alt="place.name" />
          <span v-else class="wpv__nopic">
            <IconImage :size="30" />
            <span>No picture of {{ place.name }} yet</span>
          </span>
        </div>
        <p v-if="place.appearance" class="wpv__desc">{{ place.appearance }}</p>
        <template v-if="placeSaved">
          <div class="wpv__actions">
            <button type="button" class="cta" :disabled="!!placeBusy" @click="paintPlace">
              <IconSparkle :size="15" />
              {{
                placeBusy === 'paint'
                  ? 'Painting…'
                  : placePicture
                    ? 'Generate again'
                    : 'Generate image'
              }}
            </button>
            <label class="ghost wpv__import">
              <input
                type="file"
                accept="image/png,image/jpeg,image/webp"
                :disabled="!!placeBusy"
                @change="importPlace" />
              <IconImage :size="15" /> Import image
            </label>
          </div>
          <div v-if="placePicture" class="wpv__more">
            <RouterLink
              class="studio__link"
              :to="{ name: 'library-place-maps', params: { id: presetId, key: place.key } }">
              Mark the spots inside
            </RouterLink>
            <button
              type="button"
              class="studio__link wpv__remove"
              :disabled="!!placeBusy"
              @click="removePlace">
              Remove the picture
            </button>
          </div>
          <p v-if="placeNote && !placeError" class="wpv__note" role="status">{{ placeNote }}</p>
          <p v-if="placeError" class="wpv__error" role="alert">{{ placeError }}</p>
        </template>
        <p v-else class="wpv__lead wpv__later">
          {{
            presetId
              ? `Publish the world with ${place.name} first; then it can have its own picture.`
              : 'Once the world is created, each place can have its own picture.'
          }}
        </p>
      </template>
    </div>

    <!-- summary -->
    <div
      v-show="tab === 'summary'"
      id="wpanel-panel-summary"
      class="wpv__pane"
      role="tabpanel"
      aria-labelledby="wpanel-tab-summary">
      <p v-if="draft.details" class="wpv__desc">{{ draft.details }}</p>
      <dl class="facts">
        <template v-for="row in facts" :key="row.k">
          <dt>{{ row.k }}</dt>
          <dd>{{ row.v || '—' }}</dd>
        </template>
      </dl>
    </div>

    <PictureFramer
      v-if="framing"
      :title="`Frame ${name || 'the world'}`"
      :src="framing.src"
      :size="framing.size"
      :steps="bannerSteps"
      :previews="bannerPreviews"
      :initial="bannerInitial"
      @done="framed"
      @cancel="framing = null" />
  </aside>
</template>

<style scoped>
.wpv {
  position: sticky;
  top: 76px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.wpv__head {
  display: flex;
  align-items: center;
  gap: 10px;
}
.wpv__emblem {
  color: var(--gold);
}
.wpv__title {
  font-family: var(--font-display);
  font-size: 25px;
  font-weight: 600;
  color: #26200f;
}
.wpv__pane {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.wpv__pic {
  position: relative;
  width: 100%;
  aspect-ratio: 16 / 7;
  border-radius: 12px;
  overflow: hidden;
  border: 1px solid var(--line);
  background: linear-gradient(180deg, #efe4c8, #e3d2aa);
  box-shadow: var(--card-shadow);
}
.wpv__pic--busy::after {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(
    110deg,
    transparent 20%,
    rgba(255, 240, 210, 0.65) 45%,
    transparent 70%
  );
  background-size: 250% 100%;
  animation: wpv-shimmer 1.4s linear infinite;
}
@keyframes wpv-shimmer {
  from {
    background-position: 120% 0;
  }
  to {
    background-position: -120% 0;
  }
}
.wpv__img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.wpv__nopic {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  height: 100%;
  color: #a98c55;
  font-family: var(--font-ui);
  font-size: 15px;
}
.wpv__lead {
  font-size: 15.5px;
  color: var(--ink-2);
}
.wpv__later {
  padding: 10px 14px;
  border-radius: 10px;
  background: #f6eedb;
}
.wpv__desc {
  font-size: 15.5px;
  line-height: 1.55;
  color: var(--ink-2);
}
.wpv__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}
.wpv__actions .cta svg {
  color: #ffd9a8;
}
.wpv__import {
  position: relative;
  cursor: pointer;
}
.wpv__import input {
  position: absolute;
  inset: 0;
  opacity: 0;
  cursor: pointer;
}
.wpv__more {
  display: flex;
  gap: 18px;
  font-family: var(--font-ui);
  font-size: 15px;
}
.wpv__remove {
  color: #b3542e;
}
.wpv__note {
  font-size: 14.5px;
  color: var(--ink-3);
}
.wpv__error {
  font-size: 14.5px;
  color: #b3542e;
}
.wpv__rule {
  margin: 6px 0;
}
.wpv__link {
  align-self: flex-start;
  height: auto;
  padding: 9px 15px;
  font-size: 15px;
}
.wpv__chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.wpv__chip {
  padding: 5px 12px;
  border-radius: 999px;
  border: 1px solid #dccfa9;
  background: #fcf7ea;
  font-size: 14.5px;
  color: var(--ink-2);
  transition:
    background-color 0.15s ease,
    color 0.15s ease;
}
.wpv__chip:hover {
  color: var(--teal-ink);
}
.wpv__chip--on {
  background: linear-gradient(180deg, var(--teal-hi), var(--teal));
  border-color: #0c3f46;
  color: var(--cream-on-teal);
}
@media (max-width: 1240px) {
  .wpv {
    position: static;
  }
}
</style>
