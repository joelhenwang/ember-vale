<!--
  WorldStudioView — make or change a world, step by step:
    1 Overview   its name and the player's own overview (the world's
                 description); the writing helper can improve it and fill the
                 empty fields, describe places and add new ones
    2 The world  terrain, climate, architecture, peoples, history, details,
                 what it never contains
    3 Places     each place: name, type, what it is like, landmark, road to;
                 the helper adds and describes places
    4 Review     where stories start, then create (new) or publish (existing)
  The right column is WorldPreviewPanel (the world's picture, each place's
  picture, the summary). Shared studio chrome lives in src/styles/studio.css.
  Drafts persist in the studio store keyed by id, shared with the Library.
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
import { loadCreateRequest } from '../composables/usePresetCreation'
import { usePresetCreation } from '../composables/usePresetCreation'
import {
  CLIMATES,
  ensureWorldDraft,
  isWorldDirty,
  PLACE_TYPES,
  saveWorldDraft,
  type WorldDraft
} from '../game/studio'
import {
  isWorldFieldEmpty,
  placeForWriting,
  setWorldField,
  WORLD_FIELDS,
  WORLD_STEPS,
  worldEmptyCount,
  worldWritingFields,
  WRITABLE_PLACE_TYPES,
  type WorldKey
} from '../game/worldForm'
import { fillFields } from '../api/worldsim'
import {
  connectionLabel,
  connectionOptions,
  normalizePlaceKey,
  packWorld,
  placeForConnectionLabel,
  removeWorldPlace,
  renamePlaceReferences,
  resolveConnectionKeys,
  unpackWorld
} from '../game/studioFields'
import InlineStepper from '../components/studio/InlineStepper.vue'
import ChipEditor from '../components/studio/ChipEditor.vue'
import CollapseBox from '../components/studio/CollapseBox.vue'
import StudioSelect from '../components/studio/StudioSelect.vue'
import OverviewCard from '../components/studio/OverviewCard.vue'
import WorldPreviewPanel from '../components/studio/WorldPreviewPanel.vue'
import { burst } from '../composables/useEffects'
import SaveBar from '../components/ui/SaveBar.vue'
import MenuButton from '../components/MenuButton.vue'
import IconSparkle from '../components/icons/IconSparkle.vue'
import IconArrowLeft from '../components/icons/IconArrowLeft.vue'
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
      const rawPlaces = Array.isArray(kept['places']) ? kept['places'] : undefined
      const places = rawPlaces?.map((raw, i) => coercePlace(raw, i))
      const ids = new Set(places?.map((p) => p.id) ?? [])
      const pickId = (v: unknown, fallback: string | undefined): string | undefined => {
        if (typeof v === 'string' && ids.has(v)) return v
        return fallback
      }
      applyWorldRestore({
        presetName: typeof kept['presetName'] === 'string' ? kept['presetName'] : undefined,
        terrain: Array.isArray(kept['terrain']) ? kept['terrain'].map(String) : undefined,
        climate: typeof kept['climate'] === 'string' ? kept['climate'] : undefined,
        architecture: typeof kept['architecture'] === 'string' ? kept['architecture'] : undefined,
        details: typeof kept['details'] === 'string' ? kept['details'] : undefined,
        exclusions: typeof kept['exclusions'] === 'string' ? kept['exclusions'] : undefined,
        peoples: typeof kept['peoples'] === 'string' ? kept['peoples'] : undefined,
        history: typeof kept['history'] === 'string' ? kept['history'] : undefined,
        distinct: typeof kept['distinct'] === 'string' ? kept['distinct'] : undefined,
        cover:
          kept['cover'] && typeof kept['cover'] === 'object'
            ? (kept['cover'] as WorldDraft['cover'])
            : undefined,
        loreExtra: typeof kept['loreExtra'] === 'string' ? kept['loreExtra'] : undefined,
        travelExtra: Array.isArray(kept['travelExtra'])
          ? (kept['travelExtra'] as unknown[]).filter(
              (leg): leg is string[] =>
                Array.isArray(leg) &&
                leg.length === 2 &&
                typeof leg[0] === 'string' &&
                typeof leg[1] === 'string'
            )
          : undefined,
        places,
        activePlace: pickId(kept['activePlace'], places?.[0]?.id),
        startPlace: pickId(kept['startPlace'], pickId(kept['activePlace'], places?.[0]?.id))
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
const originRoute = computed(() => (fromLibrary.value ? '/library?tab=worlds' : '/new-story'))
const draft = computed(() => ensureWorldDraft(id.value))
const place = computed(() => {
  const d = draft.value
  return d.places.find((p) => p.id === d.activePlace) ?? d.places[0]!
})

/* Four steps, each its own part of the form; any step can be opened. */
const step = ref(1)
const stepInfo = computed(() => WORLD_STEPS[step.value - 1]!)
const lastStep = WORLD_STEPS.length
function goStep(n: number): void {
  step.value = Math.min(lastStep, Math.max(1, n))
  window.scrollTo({ top: 0, behavior: 'smooth' })
}
/* Steps slide the way you are going: forward from the right, back from the left. */
const stepMotion = ref<'ev-step-next' | 'ev-step-prev'>('ev-step-next')
watch(step, (now, was) => {
  stepMotion.value = now >= was ? 'ev-step-next' : 'ev-step-prev'
})

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

/* First-preset creation (E3): local drafts only. The frozen request and
   its key survive reloads. While a submission is unresolved, retries
   replay the ORIGINAL frozen request under its original key; newer edits
   are set aside as superseded, and a second preset needs the explicit
   separate action. A memory-only freeze is flagged, never reload-safe. */
const creationSlot = `world-${id.value}`
const creation = usePresetCreation(creationSlot)

/** True when the live form has moved past the unresolved frozen request. */
const creationFormDiffers = computed(() => {
  void creation.pending.value
  void creation.status.value
  const frozen = loadCreateRequest(creationSlot)
  if (!frozen) return false
  const current = { kind: 'world', name: draft.value.presetName, ...packWorld(draft.value) }
  return !(frozen.kind === 'world' && JSON.stringify(frozen.payload) === JSON.stringify(current))
})

async function goToCreatedPreset(presetId: string): Promise<void> {
  // The receipt is durable: hand off to the real studio at revision 1
  // (library origin) or return to the wizard with an adoption offer for
  // revision 1 bound to the calling draft (wizard origin). The wizard
  // applies it only on explicit accept — never automatically.
  if (fromLibrary.value) {
    await router.push(`/library/world/${presetId}`)
  } else {
    const storyDraft =
      typeof route.query.draft === 'string' && route.query.draft ? route.query.draft : null
    await router.push({
      path: '/new-story',
      query: {
        ...(storyDraft
          ? {
              draft: storyDraft,
              adopt_kind: 'world',
              adopt_preset: presetId,
              adopt_revision: '1',
              adopt_draft: storyDraft,
              adopt_created: '1'
            }
          : {})
      }
    })
  }
}

async function createWorld(): Promise<void> {
  if (!isNew.value) return
  const packed = packWorld(draft.value)
  const presetId = await creation.submit('world', {
    kind: 'world',
    name: draft.value.presetName,
    ...packed
  })
  if (!presetId) return
  // A replay that set newer edits aside stays put: the recovered panel
  // keeps those edits available instead of abandoning them by leaving.
  if (creation.supersededEdits.value) return
  await goToCreatedPreset(presetId)
}

/** Explicit second-preset action: never taken implicitly by a retry. */
async function createSeparateWorld(): Promise<void> {
  if (!isNew.value) return
  const packed = packWorld(draft.value)
  const presetId = await creation.submitFresh('world', {
    kind: 'world',
    name: draft.value.presetName,
    ...packed
  })
  if (!presetId) return
  await goToCreatedPreset(presetId)
}

async function openRecoveredWorld(): Promise<void> {
  const presetId = creation.recoveredId.value
  if (!presetId) return
  await goToCreatedPreset(presetId)
}

/** Coerce one stored place into a valid form place (stable key included). */
function coercePlace(raw: unknown, i: number): WorldDraft['places'][number] {
  const r = (typeof raw === 'object' && raw !== null ? raw : {}) as Record<string, unknown>
  const str = (v: unknown, fallback = ''): string => (typeof v === 'string' ? v : fallback)
  const name = str(r['name'], 'New place')
  return {
    id: str(r['id'], `place-${i}`),
    key: normalizePlaceKey(name, r['key'], `place-${i + 1}`),
    name,
    type: str(r['type'], 'Other'),
    purpose: str(r['purpose']),
    appearance: str(r['appearance']),
    landmark: str(r['landmark']),
    connectedTo: str(r['connectedTo']),
    connectedKey: str(r['connectedKey']),
    sounds: str(r['sounds']),
    detailExtra: str(r['detailExtra']),
    detailBase: str(r['detailBase']),
    detailBaseCanonical: str(r['detailBaseCanonical'])
  }
}

function applyWorldRestore(restored: ReturnType<typeof unpackWorld>): void {
  const d = draft.value
  if (restored.presetName !== undefined) d.presetName = restored.presetName
  if (restored.terrain !== undefined) d.terrain = [...restored.terrain]
  if (restored.climate !== undefined) d.climate = restored.climate
  if (restored.architecture !== undefined) d.architecture = restored.architecture
  if (restored.details !== undefined) d.details = restored.details
  if (restored.exclusions !== undefined) d.exclusions = restored.exclusions
  if (restored.peoples !== undefined) d.peoples = restored.peoples
  if (restored.history !== undefined) d.history = restored.history
  if (restored.distinct !== undefined) d.distinct = restored.distinct
  if (restored.loreExtra !== undefined) d.loreExtra = restored.loreExtra
  if (restored.cover !== undefined) d.cover = restored.cover
  if (restored.travelExtra !== undefined) {
    d.travelExtra = restored.travelExtra.map((leg) => [...leg])
  }
  if (restored.places !== undefined) {
    d.places.splice(0, d.places.length, ...restored.places)
    // Legacy local saves carry display names only; resolve them once so
    // every in-session link is key-stable from here on.
    resolveConnectionKeys(d.places)
    const ids = new Set(d.places.map((p) => p.id))
    const fallback = d.places[0]?.id ?? d.activePlace
    d.startPlace =
      restored.startPlace !== undefined && ids.has(restored.startPlace)
        ? restored.startPlace
        : fallback
    d.activePlace =
      restored.activePlace !== undefined && ids.has(restored.activePlace)
        ? restored.activePlace
        : fallback
  } else if (restored.startPlace !== undefined) {
    if (d.places.some((p) => p.id === restored.startPlace)) d.startPlace = restored.startPlace
  }
}

/**
 * Links are key-stable, but the display-name mirror must follow renames.
 * placeNamesById tracks the last seen name per tab: bulk replacements
 * (hydrate/restore/add/remove) resync it silently, while a pure rename
 * of one tab repairs references through renamePlaceReferences.
 */
const placeNamesById = new Map<string, string>()

function syncPlaceNameMap(): void {
  placeNamesById.clear()
  for (const p of draft.value.places) placeNamesById.set(p.id, p.name)
}

watch(
  () => JSON.stringify(draft.value.places.map((p) => [p.id, p.name])),
  () => {
    const current = draft.value.places
    const currentIds = new Set(current.map((p) => p.id))
    if (
      currentIds.size !== placeNamesById.size ||
      [...currentIds].some((id) => !placeNamesById.has(id))
    ) {
      syncPlaceNameMap()
      return
    }
    for (const p of current) {
      const prev = placeNamesById.get(p.id)
      if (prev !== undefined && prev !== p.name) {
        renamePlaceReferences(current, p.id, prev, p.name)
        placeNamesById.set(p.id, p.name)
      }
    }
  }
)

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
    // A draft saved earlier sits on an older revision (a map or a place
    // picture moved the head since): carry on with it. Publishing keeps
    // the newer maps.
    .catch(() => {
      if (editor.openConflict.value) void resumeSavedDraft()
    })
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

/**
 * Re-enter the saved draft at its own base revision after an open
 * conflict: unpublished work stays accessible without deletion.
 */
async function resumeSavedDraft(): Promise<void> {
  if (isNew.value) return
  editorOpenedFor.value = id.value
  if (await editor.resumeStaleDraft(id.value)) hydrateFromEditor()
}

/**
 * Retry exactly the failed operation: a failed save re-sends the current
 * form (never a server re-hydrate, which would overwrite it), an
 * ambiguous publish replays the frozen request without another save,
 * and only a failed open reopens and hydrates.
 */
async function retryLast(): Promise<void> {
  if (isNew.value) return
  const op = editor.lastFailedOp.value
  if (op === 'save') {
    await save()
  } else if (op === 'publish') {
    await publish()
  } else if (op === 'complete') {
    await editor.complete(id.value)
  } else if (op === 'discard') {
    await editor.discard(id.value)
  } else {
    retryEditor()
  }
}

/** Snapshot the form so a delayed success marks clean only what it saved. */
function formSnapshot(): string {
  return JSON.stringify(draft.value)
}

function markSaved(before: string): void {
  if (JSON.stringify(draft.value) !== before) return
  saveWorldDraft(id.value)
  unsavedAfterPublish.value = false
  savedFlash.value = true
  clearTimeout(saveTimer)
  saveTimer = setTimeout(() => (savedFlash.value = false), 1400)
}

async function save(): Promise<boolean> {
  if (isNew.value) {
    const kept = storeLocalPreset('world', id.value, {
      presetName: draft.value.presetName,
      terrain: draft.value.terrain,
      climate: draft.value.climate,
      architecture: draft.value.architecture,
      details: draft.value.details,
      exclusions: draft.value.exclusions,
      peoples: draft.value.peoples,
      history: draft.value.history,
      distinct: draft.value.distinct,
      cover: draft.value.cover,
      loreExtra: draft.value.loreExtra,
      travelExtra: draft.value.travelExtra,
      places: draft.value.places,
      activePlace: draft.value.activePlace,
      startPlace: draft.value.startPlace
    })
    // Durable creation identity, minted once: stored, not yet sent.
    stableCreateKey(`world-${id.value}`)
    deviceStorageFailed.value = !kept
    if (!kept) return false
    saveWorldDraft(id.value)
    deviceSavedFlash.value = true
    savedFlash.value = true
    clearTimeout(saveTimer)
    saveTimer = setTimeout(() => {
      savedFlash.value = false
      deviceSavedFlash.value = false
    }, 1400)
    return true
  }
  const before = formSnapshot()
  editor.fields.value = {
    ...editor.fields.value,
    ...packWorld(draft.value, editor.fields.value)
  }
  const ok = await editor.save(id.value)
  // A delayed success must not mark newer edits clean: only the
  // acknowledged snapshot goes clean.
  if (ok) markSaved(before)
  return ok
}

/* A publish that lands throws sparks from the button that asked for it. */
const nextBtn = ref<{ $el?: Element } | null>(null)
watch(
  () => editor.status.value,
  (now, was) => {
    if (now === 'published' && was !== 'published') burst(nextBtn.value?.$el, { count: 22 })
  }
)

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

/** Set when a publish lands while newer edits remain: the studio stays put. */
const unsavedAfterPublish = ref(false)

async function publish(): Promise<void> {
  if (isNew.value) return
  unsavedAfterPublish.value = false
  const before = formSnapshot()
  const pending = editor.pendingPublication.value
  let view
  let acked: string
  if (pending && pending.draftId === editor.draft.value?.id) {
    // An ambiguous publication is still outstanding: replay it frozen
    // instead of saving again. A fresh save would mint a new version and
    // risk a duplicate revision next to the already-committed one. Only
    // the acknowledged snapshot may go clean — never the current form.
    acked = pending.formSnapshot
    view = await editor.retryPublish(id.value)
  } else {
    editor.fields.value = {
      ...editor.fields.value,
      ...packWorld(draft.value, editor.fields.value)
    }
    acked = before
    view = await editor.saveAndPublish(id.value, { ...editor.fields.value }, before)
  }
  if (!view) return
  // A replay publishes Older content: only a form still matching the
  // acknowledged snapshot goes clean and returns. Newer edits stay
  // dirty, recoverable, and right here.
  const coversCurrent = acked !== '' && JSON.stringify(draft.value) === acked
  if (coversCurrent) saveWorldDraft(id.value)
  else unsavedAfterPublish.value = true
  if (!fromLibrary.value && coversCurrent) {
    // Nested return: the wizard offers deliberate adoption of the exact
    // published revision — never an automatic switch. The originating
    // story draft rides along so the offer binds to it, never to
    // whatever the wizard recalls later.
    const storyDraft =
      typeof route.query.draft === 'string' && route.query.draft ? route.query.draft : null
    await router.push({
      path: '/new-story',
      query: {
        adopt_kind: 'world',
        adopt_preset: id.value,
        adopt_revision: String(view.published_revision),
        ...(storyDraft ? { adopt_draft: storyDraft } : {})
      }
    })
  }
}

async function finishAndReturn(): Promise<void> {
  // Never abandon unsaved edits: persist first, then complete.
  if (dirty.value && !(await save())) return
  if (!isNew.value && editor.draft.value) {
    if (!(await editor.complete(id.value))) return
  }
  router.push(originRoute.value)
}

onBeforeUnmount(() => {
  clearTimeout(saveTimer)
  editor.dispose()
})

const nextLabel = computed(() => WORLD_STEPS[step.value]?.title ?? '')
const nameMissing = computed(() => isNew.value && !draft.value.presetName.trim())
async function advance(): Promise<void> {
  if (step.value < lastStep) return goStep(step.value + 1)
  if (isNew.value) await createWorld()
  else await publish()
}
const displayNameForm = computed(() =>
  isNew.value ? draft.value.presetName.trim() : (record.value?.name ?? '')
)

/* places ----------------------------------------------------------------- */

/** A fresh place mints a unique stable key once; renames never re-key it. */
function freshPlaceKey(name: string): string {
  const taken = new Set(draft.value.places.map((p) => p.key))
  const base = normalizePlaceKey(name, undefined, 'place')
  if (!taken.has(base)) return base
  let n = 2
  while (taken.has(`${base}-${n}`)) n += 1
  return `${base}-${n}`
}

let placeSerial = 0
function addPlace(): void {
  const d = draft.value
  const p = {
    // Unique even when several are added in the same millisecond.
    id: `place-${Date.now()}-${(placeSerial += 1)}`,
    key: freshPlaceKey('New place'),
    name: 'New place',
    type: 'Village square',
    purpose: '',
    appearance: '',
    landmark: '',
    connectedTo: d.places[0]?.name ?? '',
    connectedKey: d.places[0]?.key ?? '',
    sounds: '',
    detailExtra: '',
    detailBase: '',
    detailBaseCanonical: ''
  }
  d.places.push(p)
  d.activePlace = p.id
}

function removeActivePlace(): void {
  removeWorldPlace(draft.value, draft.value.activePlace)
}

/** The configured starting place, independent of the inspected tab. */
const startPlaceName = computed({
  get: () => draft.value.places.find((p) => p.id === draft.value.startPlace)?.name ?? '',
  set: (name: string) => {
    const found = draft.value.places.find((p) => p.name === name)
    if (found) draft.value.startPlace = found.id
  }
})
/**
 * The connection picker stores the destination KEY while showing the
 * display name: duplicate names gain their key as a label suffix, so a
 * picked route always resolves to exactly one place.
 */
function setConnection(place: WorldDraft['places'][number], label: string): void {
  const found = placeForConnectionLabel(draft.value.places, label)
  place.connectedKey = found?.key ?? ''
  place.connectedTo = found?.name ?? ''
}

/* writing help ------------------------------------------------------------ */
const filling = ref(false)
const fillNote = ref<string | null>(null)
const helped = ref(new Set<WorldKey>())
const addCount = ref(3)

/** A world fresh from the form still has only its one untouched place. */
const onlyBlankPlace = computed(() => {
  const ps = draft.value.places
  return ps.length === 1 && ps[0]!.name === 'New place' && !placeForWriting(ps[0]!).description
})
const emptyTotal = computed(
  () => worldEmptyCount(draft.value) + (onlyBlankPlace.value ? addCount.value : 0)
)

/**
 * Ask the writing helper for what is empty: the world's fields, words for
 * places nobody described, and new places. Only empty things are written.
 */
async function fill(opts: { fields: boolean; places: boolean; add: number }): Promise<void> {
  if (filling.value) return
  const asker = document.activeElement
  filling.value = true
  fillNote.value = null
  try {
    const fields = worldWritingFields(draft.value).filter((f) => opts.fields || f.value.trim())
    const add = opts.add || (opts.fields && onlyBlankPlace.value ? addCount.value : 0)
    const known = onlyBlankPlace.value && add ? [] : draft.value.places.map(placeForWriting)
    const made = await fillFields({
      kind: 'world',
      overview: draft.value.details,
      name: displayNameForm.value,
      fields,
      places: opts.places || add ? known : [],
      add_places: add,
      place_kinds: WRITABLE_PLACE_TYPES
    })
    let count = 0
    for (const [key, value] of Object.entries(made.values)) {
      const k = key as WorldKey
      if (WORLD_FIELDS.some((f) => f.key === k) && isWorldFieldEmpty(draft.value, k)) {
        setWorldField(draft.value, k, value)
        helped.value.add(k)
        count++
      }
    }
    let added = 0
    for (const written of made.places) {
      if (written.new) {
        if (added === 0 && onlyBlankPlace.value) draft.value.places.splice(0, 1)
        addPlace()
        const fresh = draft.value.places[draft.value.places.length - 1]!
        fresh.name = written.name
        fresh.key = freshPlaceKey(written.name)
        fresh.type = written.kind || 'Other'
        fresh.appearance = written.description
        added++
      } else {
        const old = draft.value.places.find(
          (p) => p.name.trim().toLowerCase() === written.name.toLowerCase()
        )
        if (old && !old.appearance.trim()) {
          old.appearance = written.description
          count++
        }
      }
    }
    if (added) {
      // New places start with a road to the first place, so none is cut off.
      const [first, second] = draft.value.places
      for (const p of draft.value.places) {
        if (p.connectedKey) continue
        const to = p === first ? second : first
        if (to) setConnection(p, connectionLabel(draft.value.places, to.key))
      }
      resolveConnectionKeys(draft.value.places)
    }
    const startOk = draft.value.places.some((p) => p.id === draft.value.startPlace)
    if (!startOk && draft.value.places[0]) draft.value.startPlace = draft.value.places[0].id
    const parts = [
      count ? `filled ${count} field${count === 1 ? '' : 's'}` : '',
      added ? `added ${added} place${added === 1 ? '' : 's'}` : ''
    ].filter(Boolean)
    if (parts.length) burst(asker, { count: 16, spread: 80 })
    fillNote.value = parts.length
      ? `${parts.join(' and ')} for $${Number(made.cost_usd).toFixed(4)} — look them over and change anything.`.replace(
          /^./,
          (c) => c.toUpperCase()
        )
      : 'Nothing new to fill.'
  } catch (err) {
    fillNote.value = err instanceof Error ? err.message : 'Could not fill the fields this time.'
  } finally {
    filling.value = false
  }
}

const climateOptions = computed(() =>
  CLIMATES.includes(draft.value.climate) || !draft.value.climate
    ? CLIMATES
    : [...CLIMATES, draft.value.climate]
)
const typeOptions = computed(() =>
  PLACE_TYPES.includes(place.value.type) ? PLACE_TYPES : [...PLACE_TYPES, place.value.type]
)
const placesUndescribed = computed(
  () => draft.value.places.filter((p) => !placeForWriting(p).description).length
)
</script>

<template>
  <main class="studio wstudio">
    <!-- the title and the step bar run across the page, above both columns -->
    <div class="wstudio__top">
      <div class="studio__head">
        <h1 class="studio__title">
          <span class="wstudio__eyebrow">World studio</span>
          {{ isNew ? draft.presetName.trim() || 'New world' : worldName }}
        </h1>
        <span v-if="!isNew" class="wstudio__mode">Editing world</span>
        <span v-if="dirty" class="draft-badge"><span class="draft-badge__dot"></span>Unsaved</span>
      </div>
      <p v-if="recordLoading" class="studio__state" role="status">Reading the archive…</p>
      <p v-else-if="recordFailed" class="studio__state" role="alert">
        The archive did not answer ({{ presets.error.value }}) —
        <button type="button" class="studio__link" @click="retryPresets()">retry</button>
      </p>
      <p v-else-if="recordMissing" class="studio__state" role="alert">
        No world answers to that id.
      </p>
      <p v-if="!isNew && editor.status.value === 'failed'" class="studio__state" role="alert">
        {{ editor.error.value ?? 'Something went wrong.' }} —
        <button type="button" class="studio__link" @click="retryLast()">
          retry {{ editor.lastFailedOp.value ?? 'operation' }}
        </button>
        <button
          v-if="editor.openConflict.value"
          type="button"
          class="studio__link"
          @click="resumeSavedDraft()">
          Resume saved draft
        </button>
      </p>

      <InlineStepper
        class="studio__stepper"
        stretch
        :steps="WORLD_STEPS.map((s) => s.title)"
        :current="step"
        @go="goStep" />
      <p class="wstudio__sub">{{ stepInfo.sub }}</p>
    </div>

    <div class="studio__body">
      <!-- ————————————————— form column ————————————————— -->
      <div class="studio__left">
        <div class="wstudio__stage">
          <Transition :name="stepMotion">
            <div :key="step" class="wstudio__step">
              <!-- 1 · overview -->
              <template v-if="step === 1">
                <section class="card ev-card">
                  <label class="ev-field-label" for="w-name">Name</label>
                  <input
                    v-if="isNew"
                    id="w-name"
                    v-model="draft.presetName"
                    class="ev-input"
                    maxlength="128"
                    placeholder="What is this world called?" />
                  <p v-else id="w-name" class="wstudio__fixed">{{ worldName }}</p>
                </section>
                <OverviewCard
                  v-model="draft.details"
                  kind="world"
                  :name="displayNameForm"
                  placeholder="What is it? e.g. A ring of salt-marsh islands where ferry clans keep the old roads of water, the tide decides the calendar, and the drowned city under the bay still rings its bells."
                  :empty="emptyTotal"
                  :filling="filling"
                  :fill-note="fillNote"
                  @fill="fill({ fields: true, places: true, add: 0 })" />
              </template>

              <!-- 2 · the world -->
              <section v-else-if="step === 2" class="card ev-card">
                <div class="wstudio__grid">
                  <div class="wf">
                    <span class="ev-field-label">Terrain</span>
                    <ChipEditor
                      v-model="draft.terrain"
                      :class="{ 'is-helped': helped.has('terrain') }" />
                  </div>
                  <div class="wf">
                    <label class="ev-field-label" for="w-climate">Climate</label>
                    <StudioSelect
                      id="w-climate"
                      v-model="draft.climate"
                      :class="{ 'is-helped': helped.has('climate') }"
                      :options="climateOptions" />
                  </div>
                  <div
                    v-for="f in WORLD_FIELDS.filter(
                      (x) => x.key !== 'terrain' && x.key !== 'climate'
                    )"
                    :key="f.key"
                    class="wf"
                    :class="{ 'wf--wide': f.max > 400 }">
                    <label class="ev-field-label" :for="`w-${f.key}`">{{ f.label }}</label>
                    <textarea
                      :id="`w-${f.key}`"
                      v-model="draft[f.key as 'architecture']"
                      class="ev-input"
                      :class="{ 'is-helped': helped.has(f.key) }"
                      :maxlength="f.max"
                      :placeholder="f.hint"
                      :rows="f.max > 400 ? 3 : 2"
                      @input="helped.delete(f.key)" />
                  </div>
                </div>
                <div class="wstudio__fill">
                  <button
                    type="button"
                    class="wstudio__fillbtn"
                    :disabled="filling"
                    @click="fill({ fields: true, places: false, add: 0 })">
                    <IconSparkle :size="14" />
                    {{ filling ? 'Writing…' : 'Fill the empty ones from the overview' }}
                  </button>
                  <span v-if="fillNote" class="wstudio__fillnote" role="status">{{
                    fillNote
                  }}</span>
                </div>
              </section>

              <!-- 3 · places -->
              <section v-else-if="step === 3" class="card ev-card">
                <div class="wstudio__helper">
                  <span class="wstudio__helper-text">
                    <IconSparkle :size="14" /> Let the helper add
                  </span>
                  <select v-model.number="addCount" class="wstudio__count" aria-label="How many">
                    <option v-for="n in 6" :key="n" :value="n">{{ n }}</option>
                  </select>
                  <span class="wstudio__helper-text">
                    {{ addCount === 1 ? 'place' : 'places' }} from the overview
                  </span>
                  <button
                    type="button"
                    class="wstudio__fillbtn"
                    :disabled="filling"
                    @click="fill({ fields: false, places: true, add: addCount })">
                    {{ filling ? 'Writing…' : 'Add them' }}
                  </button>
                  <button
                    v-if="placesUndescribed"
                    type="button"
                    class="wstudio__fillbtn"
                    :disabled="filling"
                    @click="fill({ fields: false, places: true, add: 0 })">
                    Describe the {{ placesUndescribed }} without words
                  </button>
                </div>
                <p v-if="fillNote" class="wstudio__fillnote" role="status">{{ fillNote }}</p>

                <div class="places">
                  <TransitionGroup name="ev-list" tag="div" class="places__tabs">
                    <button
                      v-for="p in draft.places"
                      :key="p.id"
                      type="button"
                      class="places__tab"
                      :class="{ 'places__tab--on': p.id === draft.activePlace }"
                      @click="draft.activePlace = p.id">
                      {{ p.name }}
                    </button>
                    <button key="add" type="button" class="places__add" @click="addPlace">
                      <IconPlus :size="12" /> Add a place
                    </button>
                  </TransitionGroup>

                  <div class="places__fields grid2">
                    <div>
                      <label class="ev-field-label" for="p-name">Name</label>
                      <input id="p-name" v-model="place.name" class="ev-input" />
                    </div>
                    <div>
                      <label class="ev-field-label" for="p-type">Type</label>
                      <StudioSelect id="p-type" v-model="place.type" :options="typeOptions" />
                    </div>
                    <div class="grid2__wide">
                      <label class="ev-field-label" for="p-look">What it is like</label>
                      <textarea
                        id="p-look"
                        v-model="place.appearance"
                        class="ev-input"
                        rows="3"
                        placeholder="One honest paragraph of stone, cloth and light…" />
                    </div>
                    <div>
                      <label class="ev-field-label" for="p-purpose">What it is for</label>
                      <input
                        id="p-purpose"
                        v-model="place.purpose"
                        class="ev-input"
                        placeholder="Trade, rest, worship…" />
                    </div>
                    <div>
                      <label class="ev-field-label" for="p-landmark">Landmark</label>
                      <input
                        id="p-landmark"
                        v-model="place.landmark"
                        class="ev-input"
                        placeholder="The thing everyone navigates by" />
                    </div>
                    <div>
                      <label class="ev-field-label" for="p-conn">Road to</label>
                      <StudioSelect
                        id="p-conn"
                        :model-value="connectionLabel(draft.places, place.connectedKey)"
                        :options="connectionOptions(draft.places, place.id)"
                        @update:model-value="setConnection(place, $event)" />
                    </div>
                    <div class="grid2__wide">
                      <CollapseBox title="Sounds, scents & hidden details">
                        <textarea
                          v-model="place.sounds"
                          class="ev-input"
                          aria-label="Sounds, scents and hidden details"
                          placeholder="What does it sound like at dusk?" />
                      </CollapseBox>
                    </div>
                  </div>
                  <div class="places__foot">
                    <span class="places__count"
                      >{{ draft.places.length }} place{{
                        draft.places.length === 1 ? '' : 's'
                      }}</span
                    >
                    <button
                      type="button"
                      class="ghost ghost--sm"
                      :disabled="draft.places.length <= 1"
                      @click="removeActivePlace">
                      Remove {{ place.name }}
                    </button>
                  </div>
                </div>
              </section>

              <!-- 4 · review -->
              <section v-else class="card ev-card">
                <div class="grid2">
                  <div>
                    <label class="ev-field-label" for="w-start">Stories start at</label>
                    <StudioSelect
                      id="w-start"
                      v-model="startPlaceName"
                      :options="draft.places.map((p) => p.name)" />
                  </div>
                </div>
                <ul class="wstudio__checks ev-rise">
                  <li :class="{ 'is-ok': !!displayNameForm }">
                    {{
                      displayNameForm ? `Named ${displayNameForm}` : 'No name yet (Overview step)'
                    }}
                  </li>
                  <li :class="{ 'is-ok': !!draft.details.trim() }">
                    {{ draft.details.trim() ? 'Has an overview' : 'No overview yet' }}
                  </li>
                  <li :class="{ 'is-ok': draft.places.length > 1 }">
                    {{ draft.places.length }} place{{ draft.places.length === 1 ? '' : 's' }}
                  </li>
                  <li :class="{ 'is-ok': !!draft.cover }">
                    {{ draft.cover ? 'Has its own picture' : 'No picture yet (see the preview)' }}
                  </li>
                </ul>
              </section>
            </div>
          </Transition>
        </div>

        <!-- the last step makes it real: create, or publish the changes -->
        <section v-if="step === lastStep" class="card ev-card wstudio__finish">
          <template v-if="isNew">
            <p v-if="nameMissing" class="studio__state" role="status">
              Give the world a name on the Overview step to create it.
            </p>
            <p v-if="creation.status.value === 'failed'" class="studio__state" role="alert">
              {{ creation.error.value }}
            </p>
            <p
              v-if="creation.pending.value && creationFormDiffers"
              class="studio__state"
              role="status">
              An earlier creation is still unresolved — creating again replays the original request,
              so it never makes a duplicate. Newer edits stay in the form.
            </p>
            <p
              v-if="creation.pending.value && !creation.requestPersisted.value"
              class="studio__state"
              role="alert">
              The creation request is in memory only (storage unavailable) — keep this tab open
              until it lands.
            </p>
            <div v-if="creation.recoveredId.value" class="preview__actions">
              <p class="studio__state" role="status">
                This draft already created a world.
                <template v-if="creation.supersededEdits.value">
                  Newer edits are still in the form — open it to apply them there, or create a
                  separate one.
                </template>
              </p>
              <button type="button" class="cta cta--sm" @click="openRecoveredWorld">
                Open the world
              </button>
              <button type="button" class="ghost ghost--sm" @click="createSeparateWorld">
                Create a separate one
              </button>
              <button
                v-if="creation.supersededEdits.value"
                type="button"
                class="ghost ghost--sm"
                @click="creation.discardNewerEdits()">
                Discard newer edits
              </button>
            </div>
            <p v-else class="wstudio__finishnote">
              Creating puts the world in your library, ready for any story; then you can pin its
              places on a map and give each place its own picture. Until then it is kept on this
              device whenever you save the draft.
            </p>
            <p v-if="deviceStorageFailed" class="studio__state" role="alert">
              This device would not keep the draft (storage unavailable) — keep this tab open.
            </p>
          </template>
          <template v-else>
            <Transition name="ev-rise" mode="out-in">
              <p v-if="pubStatus" :key="pubStatus" class="studio__state" role="status">
                {{ pubStatus }}
              </p>
            </Transition>
            <p v-if="unsavedAfterPublish" class="studio__state" role="status">
              Newer edits are still unsaved — save or publish again before leaving.
            </p>
            <p class="wstudio__finishnote">
              Publishing makes these changes the version new stories use. Stories already under way
              keep the version they started with.
            </p>
            <button
              v-if="editor.status.value === 'published'"
              type="button"
              class="ghost ghost--sm"
              @click="finishAndReturn">
              Back to the {{ fromLibrary ? 'library' : 'new story' }}
            </button>
          </template>
        </section>
      </div>

      <WorldPreviewPanel
        :draft="draft"
        :name="displayNameForm"
        :preset-id="isNew ? null : id"
        @cover="draft.cover = $event"
        @saved="editor.adoptHead($event)" />
    </div>

    <!-- ————————————————— footer ————————————————— -->
    <SaveBar :dirty="dirty" :saved="savedFlash" secondary-label="Save draft" @secondary="save">
      <template #start>
        <button
          type="button"
          class="ghost"
          @click="step > 1 ? goStep(step - 1) : router.push(originRoute)">
          <IconArrowLeft :size="15" /> {{ step > 1 ? 'Back' : 'Leave' }}
        </button>
      </template>
      <template #end>
        <MenuButton
          ref="nextBtn"
          class="wstudio__next"
          :disabled="
            step === lastStep &&
            (isNew
              ? nameMissing || creation.status.value === 'creating' || !!creation.recoveredId.value
              : editor.status.value === 'publishing' || editor.status.value === 'loading')
          "
          @click="advance">
          {{
            step < lastStep
              ? `Continue to ${nextLabel}`
              : isNew
                ? creation.status.value === 'creating'
                  ? 'Creating…'
                  : 'Create world'
                : editor.status.value === 'publishing'
                  ? 'Publishing…'
                  : editor.pendingPublication.value
                    ? 'Retry publish'
                    : 'Publish changes'
          }}
        </MenuButton>
      </template>
    </SaveBar>
  </main>
</template>

<style scoped>
/* both columns start on one line and end on one line: no gap under either */
.wstudio__top {
  container-type: inline-size;
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-bottom: 14px;
}
.wstudio .studio__body {
  align-items: stretch;
}
.wstudio .studio__left {
  container-type: normal;
}
.wstudio__step {
  flex: 1;
}
.wstudio__step > .card:last-child,
.wstudio__step > :last-child {
  flex: 1;
}
.wstudio__mode {
  align-self: flex-end;
  padding-left: 14px;
  border-left: 1px solid var(--line);
  font-family: var(--font-ui);
  font-size: 15.5px;
  color: var(--ink-3);
}
.wstudio__eyebrow {
  display: block;
  margin-bottom: 4px;
  font-family: var(--font-ui);
  font-size: 15px;
  font-weight: 500;
  color: var(--ink-3);
}
.wstudio__sub {
  margin: 2px 0 12px;
  font-size: 17px;
  color: var(--ink-3);
}
.wstudio__step {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.wstudio__fixed {
  padding: 6px 2px;
  font-family: var(--font-display);
  font-size: 26px;
  font-weight: 600;
  color: var(--ink);
}
.wstudio__grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px 18px;
}
.wf {
  min-width: 0;
}
.wf--wide {
  grid-column: 1 / -1;
}
.is-helped,
.is-helped :deep(.ev-input) {
  border-color: #e0b07a !important;
  background: linear-gradient(180deg, #fff8ec, #fdf1de) !important;
  box-shadow: inset 3px 0 0 var(--ember) !important;
}
.wstudio__fill {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
  margin-top: 18px;
}
.wstudio__helper {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 10px;
  padding: 12px 14px;
  margin-bottom: 14px;
  border-radius: 12px;
  border: 1px dashed #e0c9a0;
  background: #fdf6ea;
}
.wstudio__helper-text {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  font-family: var(--font-ui);
  font-size: 16px;
  color: #7a3f17;
}
.wstudio__helper-text svg {
  color: var(--ember);
}
.wstudio__count {
  height: 36px;
  padding: 0 8px;
  border-radius: 8px;
  border: 1px solid #d9b48a;
  background: #fffaf0;
  font: inherit;
  font-family: var(--font-ui);
  font-size: 16px;
}
.wstudio__fillbtn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  height: 38px;
  padding: 0 15px;
  border-radius: 9px;
  border: 1px solid #d9b48a;
  background: linear-gradient(180deg, #fdf3e6, #f8e6cf);
  color: #7a3f17;
  font-size: 15px;
  font-weight: 500;
  transition: transform 0.18s var(--ease-out);
}
.wstudio__fillbtn svg {
  color: var(--ember);
}
.wstudio__fillbtn:hover:not(:disabled) {
  transform: translateY(-1px);
}
.wstudio__fillbtn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}
.wstudio__fillnote {
  font-family: var(--font-ui);
  font-size: 15px;
  color: var(--ink-3);
}
.wstudio__checks {
  list-style: none;
  display: grid;
  gap: 8px;
  margin-top: 18px;
}
.wstudio__checks li {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 16px;
  color: var(--muted);
}
.wstudio__checks li::before {
  content: '';
  width: 10px;
  height: 10px;
  border-radius: 50%;
  border: 2px solid var(--faint);
}
.wstudio__checks li.is-ok {
  color: var(--ink-2);
}
.wstudio__checks li.is-ok::before {
  border-color: #3f8f6b;
  background: #3f8f6b;
}
.wstudio__finish {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.wstudio__finishnote {
  font-size: 16px;
  color: var(--ink-2);
}
.wstudio__next {
  width: auto;
  min-width: 220px;
}

/* places tab strip ---------------------------------------------------------- */
.places__tabs {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  border-bottom: 1px solid #e6d9bb;
  margin-bottom: 15px;
}
.places__tab {
  height: 36px;
  padding: 0 16px;
  border-radius: 9px 9px 0 0;
  border: 1px solid transparent;
  border-bottom: 0;
  font-size: 15.5px;
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
  height: 36px;
  padding: 0 12px;
  font-size: 15px;
  font-weight: 500;
  color: var(--teal-ink);
  border-radius: 8px;
}
.places__add:hover {
  color: var(--ember);
}
.places__fields {
  gap: 15px 18px;
}
.places__foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  margin-top: 15px;
  padding-top: 15px;
  border-top: 1px solid #e6d9bb;
}
.places__count {
  font-family: var(--font-ui);
  font-size: 15px;
  color: var(--muted);
}
/* the old step and the new share one cell while they swap: nothing jumps */
.wstudio__stage {
  flex: 1;
  display: grid;
  overflow-x: clip;
}
.wstudio__stage > .wstudio__step {
  grid-area: 1 / 1;
  min-width: 0;
}
/* fields the writing helper filled glow as they arrive */
.is-helped {
  animation: ws-helped 1.4s var(--ease-out);
}
@keyframes ws-helped {
  from {
    outline: 3px solid rgba(220, 122, 60, 0.6);
    outline-offset: 5px;
  }
  to {
    outline: 3px solid rgba(220, 122, 60, 0);
    outline-offset: 0;
  }
}
.wstudio__fillbtn:active:not(:disabled) {
  transform: scale(0.97);
}
/* a ticked check pops as it turns green */
.wstudio__checks li::before {
  transition:
    background-color 0.25s ease,
    border-color 0.25s ease,
    transform 0.35s var(--ease-spring);
}
.wstudio__checks li.is-ok::before {
  transform: scale(1.15);
}
/* place tabs: a new place pops in; the chosen tab lifts */
.places__tab {
  transition:
    color 0.14s ease,
    background-color 0.2s ease,
    transform 0.25s var(--ease-settle);
}
.places__tab:hover:not(.places__tab--on) {
  transform: translateY(-2px);
}
.places__tabs > .ev-list-leave-active {
  display: none;
}
.places__add svg {
  transition: transform 0.35s var(--ease-settle);
}
.places__add:hover svg {
  transform: rotate(90deg);
}
@media (max-width: 760px) {
  .wstudio__grid {
    grid-template-columns: minmax(0, 1fr);
  }
  .wstudio__next {
    min-width: 0;
    flex: 1 1 100%;
  }
}
</style>
