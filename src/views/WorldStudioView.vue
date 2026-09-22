<!--
  WorldStudioView — the "Shape your world" screen. Same split of concerns as
  CharacterStudioView: shared chrome is styled once in src/styles/studio.css;
  this file keeps the two form cards (look + places) and the footer, while the
  preview column (Scene / Map / Summary) lives inline because its panes are
  thin enough not to warrant their own component (the character preview owns
  render timers, lightbox and dialogue state — the world one does not).

  Mock copy pools (scene samples, suggest values) live in src/game/studio.ts.
  Drafts persist in the studio store keyed by id, shared with the Library.

  DEMO scope: the 4-step InlineStepper is visual state only; advancing just
  increments `step`. Production replaces it with per-step routes + validation.
-->
<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { catalog } from '../game/catalog'
import { usePresets } from '../composables/usePresets'
import {
  loadLocalPreset,
  stableCreateKey,
  storeLocalPreset,
  useEditorDraft
} from '../composables/useEditorDraft'
import { resolveImage, setGeneratedImage } from '../game/images'
import type { ImageSlot } from '../game/model'
import {
  CLIMATES,
  ensureWorldDraft,
  isWorldDirty,
  PLACE_TYPES,
  saveWorldDraft,
  suggestWorld,
  TIMES,
  WEATHERS,
  worldSample,
  type WorldDraft
} from '../game/studio'
import { packWorld, unpackWorld } from '../game/studioFields'
import InlineStepper from '../components/studio/InlineStepper.vue'
import ChipEditor from '../components/studio/ChipEditor.vue'
import CollapseBox from '../components/studio/CollapseBox.vue'
import SuggestButton from '../components/studio/SuggestButton.vue'
import StudioSelect from '../components/studio/StudioSelect.vue'
import SaveBar from '../components/ui/SaveBar.vue'
import IconSparkle from '../components/icons/IconSparkle.vue'
import IconBook from '../components/icons/IconBook.vue'
import IconEmblem from '../components/icons/IconEmblem.vue'
import IconArrowLeft from '../components/icons/IconArrowLeft.vue'
import IconArrowRight from '../components/icons/IconArrowRight.vue'
import IconInfo from '../components/icons/IconInfo.vue'
import IconImage from '../components/icons/IconImage.vue'
import IconPencil from '../components/icons/IconPencil.vue'
import IconPlus from '../components/icons/IconPlus.vue'

const route = useRoute()
const router = useRouter()

const id = computed(() => String(route.params.id ?? 'new'))
/* Server preset first (E3), then the local catalog, then the blank default. */
const presets = usePresets()
let presetAbort: AbortController | null = null
onMounted(() => {
  presetAbort = new AbortController()
  void presets.load(presetAbort.signal)
  if (isNew.value) {
    // Reload-persistent local draft: unfinished work survives navigation.
    // Only known form keys are restored, never stray storage content.
    const kept = loadLocalPreset('world', id.value)
    if (kept) {
      applyWorldRestore({
        terrain: Array.isArray(kept['terrain'])
          ? (kept['terrain'] as string[]).map(String)
          : undefined,
        climate: typeof kept['climate'] === 'string' ? kept['climate'] : undefined,
        architecture: typeof kept['architecture'] === 'string' ? kept['architecture'] : undefined,
        details: typeof kept['details'] === 'string' ? kept['details'] : undefined,
        exclusions: typeof kept['exclusions'] === 'string' ? kept['exclusions'] : undefined,
        places: Array.isArray(kept['places'])
          ? (kept['places'] as WorldDraft['places'])
          : undefined,
        activePlace: typeof kept['activePlace'] === 'string' ? kept['activePlace'] : undefined
      })
      saveWorldDraft(id.value)
    }
  }
})
onUnmounted(() => presetAbort?.abort())
/* New/existing comes from the route, never from catalog membership. */
const isNew = computed(() => id.value === 'new')
const serverWorld = computed(() => presets.worlds.value.find((w) => w.id === id.value))
const world = computed(() => catalog.worlds.find((w) => w.id === id.value))
const record = computed(() => serverWorld.value ?? world.value ?? null)
/* Loading, failed, missing, and loaded stay distinct: a failed lookup
   must surface Retry, never sit behind the loading line. */
const recordLoading = computed(() => !isNew.value && presets.loading.value && record.value === null)
const recordFailed = computed(
  () =>
    !isNew.value && !presets.loading.value && presets.error.value !== null && record.value === null
)
const recordMissing = computed(
  () =>
    !isNew.value && !presets.loading.value && presets.error.value === null && record.value === null
)
const worldName = computed(() => record.value?.name ?? 'your new world')

function retryPresets(): void {
  presetAbort?.abort()
  presetAbort = new AbortController()
  void presets.load(presetAbort.signal)
}
const fromLibrary = computed(() => route.meta.from === 'library')
const originCrumb = computed(() => (fromLibrary.value ? 'Library' : 'New Story'))
const originRoute = computed(() => (fromLibrary.value ? '/library?tab=worlds' : '/new-story'))
const draft = computed(() => ensureWorldDraft(id.value))
const place = computed(() => {
  const d = draft.value
  return d.places.find((p) => p.id === d.activePlace) ?? d.places[0]!
})

/** The Location condition picker is name-based; sync it to the id-keyed draft. */
const activePlaceName = computed({
  get: () => place.value.name,
  set: (name: string) => {
    const found = draft.value.places.find((p) => p.name === name)
    if (found) draft.value.activePlace = found.id
  }
})

const step = ref(2)

/* save / dirty ----------------------------------------------------------- */
const dirty = computed(() => isWorldDirty(id.value))
const savedFlash = ref(false)
/** New presets live on this device until first publication. */
const deviceSavedFlash = ref(false)
const deviceStorageFailed = ref(false)
let saveTimer: ReturnType<typeof setTimeout> | undefined

/* Server editor draft (E3): existing presets only. Every operation freezes
   its owning draft id and versions, so a late response for one editor can
   never alter another. Unmapped payload keys are never packed, so the
   server merge preserves them verbatim. */
const editor = useEditorDraft()
const editorOpenedFor = ref<string | null>(null)

function applyWorldRestore(restored: ReturnType<typeof unpackWorld>): void {
  const d = draft.value
  if (restored.terrain !== undefined) d.terrain = [...restored.terrain]
  if (restored.climate !== undefined) d.climate = restored.climate
  if (restored.architecture !== undefined) d.architecture = restored.architecture
  if (restored.details !== undefined) d.details = restored.details
  if (restored.exclusions !== undefined) d.exclusions = restored.exclusions
  if (restored.places !== undefined) {
    d.places.splice(0, d.places.length, ...restored.places)
    d.activePlace = restored.activePlace ?? restored.places[0]?.id ?? d.activePlace
  }
}

function hydrateFromEditor(): void {
  applyWorldRestore(unpackWorld(editor.fields.value))
  // Hydration is the clean baseline: entering the studio is not an edit.
  saveWorldDraft(id.value)
}

watch(serverWorld, (rec) => {
  if (isNew.value || !rec || editorOpenedFor.value === id.value) return
  editorOpenedFor.value = id.value
  void editor
    .open(id.value, rec.revision)
    .then(hydrateFromEditor)
    .catch(() => {})
})

function retryEditor(): void {
  const rec = serverWorld.value
  if (isNew.value || !rec) return
  editorOpenedFor.value = null
  editor.dispose()
  editorOpenedFor.value = id.value
  void editor
    .open(id.value, rec.revision)
    .then(hydrateFromEditor)
    .catch(() => {})
}

async function save(): Promise<void> {
  if (isNew.value) {
    const kept = storeLocalPreset('world', id.value, {
      terrain: draft.value.terrain,
      climate: draft.value.climate,
      architecture: draft.value.architecture,
      details: draft.value.details,
      exclusions: draft.value.exclusions,
      places: draft.value.places,
      activePlace: draft.value.activePlace
    })
    // Durable creation identity, minted once: stored, not yet sent. First
    // publication stays unwired until the server receipt lands.
    stableCreateKey(`world-${id.value}`)
    deviceStorageFailed.value = !kept
    if (!kept) return
    saveWorldDraft(id.value)
    deviceSavedFlash.value = true
    savedFlash.value = true
    clearTimeout(saveTimer)
    saveTimer = setTimeout(() => {
      savedFlash.value = false
      deviceSavedFlash.value = false
    }, 1400)
    return
  }
  editor.fields.value = { ...editor.fields.value, ...packWorld(draft.value) }
  const ok = await editor.save(id.value)
  if (ok) {
    saveWorldDraft(id.value)
    savedFlash.value = true
    clearTimeout(saveTimer)
    saveTimer = setTimeout(() => (savedFlash.value = false), 1400)
  }
}

const pubStatus = computed(() => {
  if (isNew.value) return null
  switch (editor.status.value) {
    case 'loading':
      return 'Reading the archive draft…'
    case 'saving':
      return 'Saving…'
    case 'saved':
      return 'Saved.'
    case 'publishing':
      return 'Publishing…'
    case 'published':
      return `Published revision ${editor.publishedRevision.value}.`
    case 'failed':
      return editor.error.value ?? 'Something failed.'
    default:
      return null
  }
})

async function publish(): Promise<void> {
  if (isNew.value) return
  editor.fields.value = { ...editor.fields.value, ...packWorld(draft.value) }
  const presetVersion = editor.baseDetail.value?.version ?? 0
  const view = await editor.publish(id.value, presetVersion)
  if (!view) return
  saveWorldDraft(id.value)
  if (!fromLibrary.value) {
    // Nested return: the wizard offers deliberate adoption of the exact
    // published revision — never an automatic switch.
    await router.push({
      path: '/new-story',
      query: {
        adopt_kind: 'world',
        adopt_preset: id.value,
        adopt_revision: String(view.published_revision)
      }
    })
  }
}

async function finishAndReturn(): Promise<void> {
  if (!isNew.value && editor.draft.value) {
    await editor.complete(id.value)
  }
  router.push(originRoute.value)
}

onBeforeUnmount(() => {
  clearTimeout(saveTimer)
  editor.dispose()
})

const nextLabel = computed(() =>
  step.value <= 2 ? 'Rules' : step.value === 3 ? 'Review' : 'Finish'
)
function advance(): void {
  // DEMO: stepper is cosmetic (see header note) — production gates by validation.
  if (step.value < 4) {
    step.value++
    return
  }
  void save().then(() => {
    router.push(originRoute.value)
  })
}

/* places ----------------------------------------------------------------- */
function addPlace(): void {
  const d = draft.value
  const p = {
    id: `place-${Date.now()}`,
    name: 'New place',
    type: 'Village square',
    purpose: '',
    appearance: '',
    landmark: '',
    connectedTo: d.places[0]?.name ?? '',
    sounds: ''
  }
  d.places.push(p)
  d.activePlace = p.id
}
function otherPlaceNames(): string[] {
  const d = draft.value
  return d.places.filter((p) => p.id !== d.activePlace).map((p) => p.name)
}

/* preview ------------------------------------------------------------------ */
const tab = ref<'scene' | 'map' | 'summary'>('scene')
const sceneSlot = computed<ImageSlot>(() =>
  id.value === 'ember-vale'
    ? 'scene.market'
    : id.value === 'silverleaf-coast'
      ? 'world.silverleaf'
      : 'world.emberVale'
)
const sceneUrl = computed(() => resolveImage(sceneSlot.value))
const mapUrl = computed(() => resolveImage('world.map'))

const time = ref('Morning')
const weather = ref('Clear')

/* Canned scene prose lives in game/studio.ts (worldSample), keyed by
   "Time|Weather", with a generated fallback for unauthored combinations. */
const sample = computed(() =>
  worldSample(time.value, weather.value, place.value.name, draft.value.details)
)

const generating = ref(false)
let genTimer: ReturnType<typeof setTimeout> | undefined
function generatePreview(): void {
  if (generating.value) return
  generating.value = true
  clearTimeout(genTimer)
  // DEMO: fake render latency + cache-busted placeholder URL; production
  // queues a real image task and swaps the slot once it resolves.
  genTimer = setTimeout(() => {
    setGeneratedImage(sceneSlot.value, `${resolveImage(sceneSlot.value)}?v=${Date.now()}`)
    generating.value = false
  }, 900)
}
onBeforeUnmount(() => clearTimeout(genTimer))

const refining = ref(false)
const refinedText = ref('')
function toggleRefine(): void {
  refining.value = !refining.value
  if (refining.value && !refinedText.value) refinedText.value = sample.value
}
function applyRefine(): void {
  if (refinedText.value.trim()) {
    // production: feed the refinement back into the world notes
    draft.value.details = refinedText.value.trim()
  }
  refining.value = false
}

/* suggest ------------------------------------------------------------------ */
function suggest(): void {
  suggestWorld(draft.value)
}
</script>

<template>
  <main class="studio">
    <div class="studio__body">
      <!-- ————————————————— form column ————————————————— -->
      <div class="studio__left">
        <nav class="crumbs" aria-label="Breadcrumb">
          <router-link :to="originRoute">{{ originCrumb }}</router-link>
          <span class="crumbs__sep">/</span>
          <router-link :to="originRoute">Worlds</router-link>
          <span class="crumbs__sep">/</span>
          <span class="crumbs__here">{{ isNew ? 'New world' : worldName }}</span>
        </nav>

        <div class="studio__head">
          <h1 class="studio__title">Shape your world</h1>
          <span class="draft-badge"><span class="draft-badge__dot"></span>Draft</span>
        </div>
        <p class="studio__sub">Define the places your stories will inhabit.</p>
        <p v-if="recordLoading" class="studio__state" role="status">Reading the archive…</p>
        <p v-else-if="recordFailed" class="studio__state" role="alert">
          The archive did not answer ({{ presets.error.value }}) —
          <button type="button" class="studio__link" @click="retryPresets()">retry</button>
        </p>
        <p v-else-if="recordMissing" class="studio__state" role="alert">
          No world answers to that id.
        </p>

        <InlineStepper
          class="studio__stepper"
          :steps="['Concept', 'Places & appearance', 'Rules & knowledge', 'Review']"
          :current="step"
          @go="step = $event" />

        <section class="card ev-card">
          <header class="card__head">
            <h2 class="card__title"><IconSparkle :size="15" /> The look of {{ worldName }}</h2>
            <SuggestButton @suggest="suggest" />
          </header>
          <div class="grid2">
            <div>
              <span class="ev-field-label">Terrain</span>
              <ChipEditor v-model="draft.terrain" />
            </div>
            <div>
              <span class="ev-field-label">Climate</span>
              <StudioSelect v-model="draft.climate" :options="CLIMATES" />
            </div>
            <div>
              <span class="ev-field-label">Architecture</span>
              <textarea
                v-model="draft.architecture"
                class="ev-input"
                placeholder="What do roofs remember?" />
            </div>
            <div>
              <span class="ev-field-label">Distinctive details</span>
              <textarea
                v-model="draft.details"
                class="ev-input"
                placeholder="The three glances that say “you’re here”" />
            </div>
            <div class="grid2__wide">
              <span class="ev-field-label">Exclusions</span>
              <input
                v-model="draft.exclusions"
                class="ev-input"
                placeholder="What this world will never contain" />
            </div>
          </div>
        </section>

        <section class="card ev-card">
          <header class="card__head">
            <h2 class="card__title"><IconBook :size="19" /> Places</h2>
          </header>

          <div class="places">
            <div class="places__tabs">
              <button
                v-for="p in draft.places"
                :key="p.id"
                type="button"
                class="places__tab"
                :class="{ 'places__tab--on': p.id === draft.activePlace }"
                @click="draft.activePlace = p.id">
                {{ p.name }}
              </button>
              <button type="button" class="places__add" @click="addPlace">
                <IconPlus :size="12" /> Add place
              </button>
            </div>

            <div class="places__fields grid2">
              <div>
                <span class="ev-field-label">Name</span>
                <input v-model="place.name" class="ev-input" />
              </div>
              <div>
                <span class="ev-field-label">Type</span>
                <StudioSelect v-model="place.type" :options="PLACE_TYPES" />
              </div>
              <div>
                <span class="ev-field-label">Purpose</span>
                <input v-model="place.purpose" class="ev-input" placeholder="What is it for?" />
              </div>
              <div>
                <span class="ev-field-label">Appearance</span>
                <textarea
                  v-model="place.appearance"
                  class="ev-input"
                  placeholder="One honest paragraph of stone, cloth and light…" />
              </div>
              <div>
                <span class="ev-field-label">Landmark</span>
                <input
                  v-model="place.landmark"
                  class="ev-input"
                  placeholder="The thing everyone navigates by" />
              </div>
              <div>
                <span class="ev-field-label">Connected to</span>
                <StudioSelect v-model="place.connectedTo" :options="otherPlaceNames()" />
              </div>
              <div class="grid2__wide">
                <CollapseBox title="Sounds, scents & hidden details">
                  <span class="ev-field-label">Texture</span>
                  <textarea
                    v-model="place.sounds"
                    class="ev-input"
                    placeholder="What does it sound like at dusk?" />
                </CollapseBox>
              </div>
            </div>
          </div>
        </section>

        <section class="card ev-card" aria-label="Publication">
          <header class="card__head">
            <h2 class="card__title">Publication</h2>
          </header>
          <div v-if="isNew">
            <p class="studio__state" role="status">
              New worlds live on this device until first publication.
            </p>
            <p v-if="deviceSavedFlash" class="studio__state" role="status">Saved on this device.</p>
            <p v-if="deviceStorageFailed" class="studio__state" role="alert">
              This device would not keep the draft (storage unavailable) — keep this tab open until
              you can save elsewhere.
            </p>
          </div>
          <div v-else>
            <p v-if="pubStatus" class="studio__state" role="status">{{ pubStatus }}</p>
            <p v-if="editor.status.value === 'failed'" class="studio__state" role="alert">
              <button type="button" class="studio__link" @click="retryEditor()">retry</button>
            </p>
            <div class="preview__actions">
              <button
                type="button"
                class="cta cta--sm"
                :disabled="
                  editor.status.value === 'publishing' || editor.status.value === 'loading'
                "
                @click="publish">
                {{ editor.status.value === 'publishing' ? 'Publishing…' : 'Publish new revision' }}
              </button>
              <button
                v-if="editor.status.value === 'published'"
                type="button"
                class="ghost ghost--sm"
                @click="finishAndReturn">
                Finish &amp; return
              </button>
            </div>
          </div>
        </section>
      </div>

      <!-- ————————————————— preview column ————————————————— -->
      <aside class="card ev-card preview" aria-label="World preview">
        <header class="preview__head">
          <IconEmblem :size="24" class="preview__emblem" />
          <h2 class="preview__title">World preview</h2>
        </header>

        <div class="preview__tabs" role="tablist" aria-label="Preview sections">
          <button
            v-for="t in ['scene', 'map', 'summary'] as const"
            :id="`wpanel-tab-${t}`"
            :key="t"
            type="button"
            role="tab"
            :aria-selected="tab === t"
            :aria-controls="`wpanel-panel-${t}`"
            :class="{ 'preview__tabs--on': tab === t }"
            @click="tab = t">
            {{ t === 'scene' ? 'Scene' : t === 'map' ? 'Map' : 'Summary' }}
          </button>
        </div>

        <div
          v-show="tab === 'scene'"
          id="wpanel-panel-scene"
          class="preview__pane"
          role="tabpanel"
          aria-labelledby="wpanel-tab-scene">
          <div class="scene-img" :class="{ 'is-rendering': generating }">
            <img :src="sceneUrl" :alt="`${worldName} scene preview`" />
          </div>

          <div class="conds">
            <div>
              <span class="conds__label">Location</span>
              <StudioSelect v-model="activePlaceName" :options="draft.places.map((p) => p.name)" />
            </div>
            <div>
              <span class="conds__label">Time</span>
              <StudioSelect v-model="time" :options="TIMES" />
            </div>
            <div>
              <span class="conds__label">Weather</span>
              <StudioSelect v-model="weather" :options="WEATHERS" />
            </div>
          </div>
          <p class="ev-info"><IconInfo :size="14" /> Preview conditions only</p>

          <div class="ev-divider preview__rule" aria-hidden="true"><IconSparkle :size="11" /></div>

          <span class="ev-field-label">Scene sample</span>
          <p class="sample">{{ sample }}</p>

          <div class="preview__actions">
            <button type="button" class="cta" :disabled="generating" @click="generatePreview">
              <IconImage :size="16" /> {{ generating ? 'Painting…' : 'Generate preview' }}
            </button>
            <button type="button" class="refine" @click="toggleRefine">
              <IconPencil :size="12" /> Refine description
            </button>
          </div>
          <div v-if="refining" class="refine-box">
            <textarea v-model="refinedText" class="ev-input" rows="3" />
            <div class="refine-box__row">
              <button type="button" class="ghost ghost--sm" @click="refining = false">
                Cancel
              </button>
              <button type="button" class="cta cta--sm" @click="applyRefine">Apply to notes</button>
            </div>
          </div>
          <p class="ev-info"><IconInfo :size="14" /> Preview art does not change world facts.</p>
        </div>

        <div
          v-show="tab === 'map'"
          id="wpanel-panel-map"
          class="preview__pane"
          role="tabpanel"
          aria-labelledby="wpanel-tab-map">
          <div class="scene-img scene-img--tall">
            <img :src="mapUrl" :alt="`${worldName} map`" />
          </div>
          <p class="ev-info">
            <IconInfo :size="14" />
            A cartographer’s pass over the valley floor — places you’ve defined appear here as you
            add them.
          </p>
          <ul class="maplegend">
            <li v-for="p in draft.places" :key="p.id">
              <span class="maplegend__dot"></span>{{ p.name }}
              <em v-if="p.landmark">· {{ p.landmark }}</em>
            </li>
          </ul>
        </div>

        <div
          v-show="tab === 'summary'"
          id="wpanel-panel-summary"
          class="preview__pane"
          role="tabpanel"
          aria-labelledby="wpanel-tab-summary">
          <dl class="facts">
            <template
              v-for="row in [
                { k: 'Terrain', v: draft.terrain.join(', ') || '—' },
                { k: 'Climate', v: draft.climate },
                { k: 'Architecture', v: draft.architecture || '—' },
                { k: 'Signature details', v: draft.details || '—' },
                { k: 'Exclusions', v: draft.exclusions || '—' },
                { k: 'Places', v: String(draft.places.length) }
              ]"
              :key="row.k">
              <dt>{{ row.k }}</dt>
              <dd>{{ row.v }}</dd>
            </template>
          </dl>
          <p class="ev-info">
            <IconInfo :size="14" />
            The narrator quotes these facts back to you in the Review step.
          </p>
        </div>
      </aside>
    </div>

    <!-- ————————————————— footer ————————————————— -->
    <SaveBar :dirty="dirty" :saved="savedFlash" secondary-label="Save draft" @secondary="save">
      <template #start>
        <button type="button" class="ghost" @click="router.back()">
          <IconArrowLeft :size="14" /> Back
        </button>
      </template>
      <template #end>
        <button type="button" class="cta cta--foot" @click="advance">
          {{ step < 4 ? `Continue to ${nextLabel}` : 'Finish & save' }}
          <IconArrowRight :size="14" />
        </button>
      </template>
    </SaveBar>
  </main>
</template>

<style scoped>
/* places tab strip ---------------------------------------------------------- */
.places {
  border-top: 1px solid transparent;
}
.places__tabs {
  display: flex;
  align-items: center;
  gap: 6px;
  border-bottom: 1px solid #e6d9bb;
  margin-bottom: 15px;
}
.places__tab {
  height: 34px;
  padding: 0 16px;
  border-radius: 9px 9px 0 0;
  border: 1px solid transparent;
  border-bottom: 0;
  font-size: 15px;
  font-weight: 500;
  color: #55482f;
  position: relative;
  top: 1px;
  transition:
    color 0.14s ease,
    background 0.14s ease;
}
.places__tab:hover {
  color: var(--teal-ink);
}
.places__tab--on {
  background: linear-gradient(180deg, #21655f, #175256);
  border-color: #0f4147;
  color: var(--cream-on-teal);
  box-shadow: inset 0 1px 0 rgba(255, 243, 214, 0.2);
}
.places__add {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  height: 34px;
  padding: 0 12px;
  font-size: 14.5px;
  font-weight: 500;
  color: var(--teal-ink);
  border-radius: 8px;
  transition: color 0.14s ease;
}
.places__add:hover {
  color: var(--teal);
}
.places__fields {
  gap: 15px 18px;
}
</style>
