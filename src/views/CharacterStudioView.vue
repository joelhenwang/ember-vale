<!--
  CharacterStudioView — make or change a character, step by step:
    1 Overview      their name and the player's own overview; the writing
                    helper can improve it and fill every empty field from it
    2 Appearance    age, race, sex, hair, eyes, height, body, extra; a picture
                    painted from those words or imported
    3 Background & personality
    4 Voice         tone, speaking style, lines they would say
    5 Review        what they wear and carry and how they are, then create
                    (new) or publish (existing)
  Reached from /library/character/:id and /new-story/character/:id, told
  apart by route meta.from (where to return). Shared studio chrome lives in
  src/styles/studio.css; the right column is CharacterPreviewPanel.

  Drafts live in src/game/studio.ts keyed by id and persist across routes, so
  "Save draft"/dirty state survive navigating to the Library and back.
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
import { loadCreateRequest, usePresetCreation } from '../composables/usePresetCreation'
import { ensureCharDraft, isCharDirty, saveCharDraft, STRANGER_STANCES } from '../game/studio'
import { packCharacter, unpackCharacter } from '../game/studioFields'
import {
  CHARACTER_FIELDS,
  CHARACTER_STEPS,
  DEEPER_KEYS,
  emptyCount,
  fieldsOnStep,
  stepSummaries,
  portraitPrompt,
  writingContext,
  writingFields,
  type FieldSpec,
  type WritableKey
} from '../game/characterForm'
import { fillFields } from '../api/worldsim'
import CharacterPreviewPanel from '../components/studio/CharacterPreviewPanel.vue'
import CharacterSidePanel from '../components/studio/CharacterSidePanel.vue'
import { burst } from '../composables/useEffects'
import CollapseBox from '../components/studio/CollapseBox.vue'
import OverviewCard from '../components/studio/OverviewCard.vue'
import InlineStepper from '../components/studio/InlineStepper.vue'
import ChipEditor from '../components/studio/ChipEditor.vue'
import StudioSelect from '../components/studio/StudioSelect.vue'
import SaveBar from '../components/ui/SaveBar.vue'
import MenuButton from '../components/MenuButton.vue'
import IconSparkle from '../components/icons/IconSparkle.vue'
import IconArrowLeft from '../components/icons/IconArrowLeft.vue'
import IconArrowRight from '../components/icons/IconArrowRight.vue'

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
    // New presets store the raw form (not packed fields); only known form
    // keys are restored, never stray storage content.
    const kept = loadLocalPreset('character', id.value)
    if (kept) {
      for (const key of [
        'overview',
        'age',
        'race',
        'sex',
        'hair',
        'eyes',
        'height',
        'body',
        'marks',
        'history',
        'traits',
        'habits',
        'tone',
        'wears',
        'carries',
        'condition',
        'appearanceExtra',
        'portraitAssetId',
        'portraitFrames',
        'want',
        'avoid',
        'pressure',
        'contradiction',
        'styleTags',
        'withStrangers',
        'whenTheyCare',
        'exampleLine',
        'boundaries',
        'secretFear',
        'pronouns',
        'presetName',
        'personalityExtra',
        'backgroundExtra'
      ] as const) {
        if (key in kept) (draft.value[key] as unknown) = kept[key]
      }
      saveCharDraft(id.value)
    }
  }
})
onUnmounted(() => presetAbort?.abort())
/* New/existing comes from the route, never from catalog membership:
   a server preset absent from the mock catalog is still existing. */
const isNew = computed(() => id.value === 'new')
const serverCharacter = computed(() => presets.characters.value.find((c) => c.id === id.value))
const character = computed(() => catalog.characters.find((c) => c.id === id.value))
const record = computed(() => serverCharacter.value ?? character.value ?? null)
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
const displayName = computed(() => record.value?.name ?? 'the new character')

function retryPresets(): void {
  presetAbort?.abort()
  presetAbort = new AbortController()
  void presets.load(presetAbort.signal)
}

/* The return target depends on which flow opened the studio. */
const fromLibrary = computed(() => route.meta.from === 'library')
const originRoute = computed(() => (fromLibrary.value ? '/library?tab=characters' : '/new-story'))

const draft = computed(() => ensureCharDraft(id.value))

/* Five steps, each its own part of the form; any step can be opened. */
const step = ref(1)
const stepInfo = computed(() => CHARACTER_STEPS[step.value - 1]!)
const lastStep = CHARACTER_STEPS.length
function goStep(n: number): void {
  step.value = Math.min(lastStep, Math.max(1, n))
  window.scrollTo({ top: 0, behavior: 'smooth' })
}
/* Steps slide the way you are going: forward from the right, back from the left. */
const stepMotion = ref<'ev-step-next' | 'ev-step-prev'>('ev-step-next')
watch(step, (now, was) => {
  stepMotion.value = now >= was ? 'ev-step-next' : 'ev-step-prev'
})

/* ————— save / dirty ————— */
const dirty = computed(() => isCharDirty(id.value))
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
const creationSlot = `character-${id.value}`
const creation = usePresetCreation(creationSlot)

/** True when the live form has moved past the unresolved frozen request. */
const creationFormDiffers = computed(() => {
  void creation.pending.value
  void creation.status.value
  const frozen = loadCreateRequest(creationSlot)
  if (!frozen) return false
  const current = { kind: 'character', name: draft.value.presetName, ...packCharacter(draft.value) }
  return !(
    frozen.kind === 'character' && JSON.stringify(frozen.payload) === JSON.stringify(current)
  )
})

async function goToCreatedPreset(presetId: string): Promise<void> {
  // The receipt is durable: hand off to the real studio at revision 1
  // (library origin) or return to the wizard with an adoption offer for
  // revision 1 bound to the calling draft (wizard origin). The wizard
  // applies it only on explicit accept — never automatically.
  if (fromLibrary.value) {
    await router.push(`/library/character/${presetId}`)
  } else {
    const storyDraft =
      typeof route.query.draft === 'string' && route.query.draft ? route.query.draft : null
    await router.push({
      path: '/new-story',
      query: {
        ...(storyDraft
          ? {
              draft: storyDraft,
              adopt_kind: 'character',
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

async function createCharacter(): Promise<void> {
  if (!isNew.value) return
  const packed = packCharacter(draft.value)
  const presetId = await creation.submit('character', {
    kind: 'character',
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
async function createSeparateCharacter(): Promise<void> {
  if (!isNew.value) return
  const packed = packCharacter(draft.value)
  const presetId = await creation.submitFresh('character', {
    kind: 'character',
    name: draft.value.presetName,
    ...packed
  })
  if (!presetId) return
  await goToCreatedPreset(presetId)
}

async function openRecoveredCharacter(): Promise<void> {
  const presetId = creation.recoveredId.value
  if (!presetId) return
  await goToCreatedPreset(presetId)
}

function hydrateFromEditor(): void {
  const restored = unpackCharacter(editor.fields.value)
  Object.assign(draft.value, restored)
  // Hydration is the clean baseline: entering the studio is not an edit.
  saveCharDraft(id.value)
}

watch(serverCharacter, (rec) => {
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
  const rec = serverCharacter.value
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
  saveCharDraft(id.value)
  unsavedAfterPublish.value = false
  savedFlash.value = true
  clearTimeout(saveTimer)
  saveTimer = setTimeout(() => (savedFlash.value = false), 1400)
}

async function save(): Promise<boolean> {
  if (isNew.value) {
    const kept = storeLocalPreset('character', id.value, { ...draft.value })
    // Durable creation identity, minted once: stored, not yet sent.
    stableCreateKey(`character-${id.value}`)
    deviceStorageFailed.value = !kept
    if (!kept) return false
    saveCharDraft(id.value)
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
    ...packCharacter(draft.value, editor.fields.value)
  }
  const ok = await editor.save(id.value)
  // A delayed success must not mark newer edits clean: only the
  // acknowledged snapshot goes clean.
  if (ok) markSaved(before)
  return ok
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

/* A publish that lands throws sparks from the button that asked for it. */
const nextBtn = ref<{ $el?: Element } | null>(null)
watch(
  () => editor.status.value,
  (now, was) => {
    if (now === 'published' && was !== 'published') burst(nextBtn.value?.$el, { count: 22 })
  }
)

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
      ...packCharacter(draft.value, editor.fields.value)
    }
    acked = before
    view = await editor.saveAndPublish(id.value, { ...editor.fields.value }, before)
  }
  if (!view) return
  // A replay publishes Older content: only a form still matching the
  // acknowledged snapshot goes clean and returns. Newer edits stay
  // dirty, recoverable, and right here.
  const coversCurrent = acked !== '' && JSON.stringify(draft.value) === acked
  if (coversCurrent) saveCharDraft(id.value)
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
        adopt_kind: 'character',
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

/* ————— advance ————— */
const nextLabel = computed(() => CHARACTER_STEPS[step.value]?.title ?? '')
const nameMissing = computed(() => isNew.value && !draft.value.presetName.trim())
async function advance(): Promise<void> {
  if (step.value < lastStep) return goStep(step.value + 1)
  if (isNew.value) await createCharacter()
  else await publish()
}

/* ————— writing help: fill what is empty from the overview ————— */
const filling = ref(false)
const fillNote = ref<string | null>(null)
/** Fields the helper wrote, marked until the player edits them. */
const helped = ref(new Set<WritableKey>())
const displayNameForm = computed(() =>
  isNew.value ? draft.value.presetName.trim() : (record.value?.name ?? '')
)

async function fill(onStep?: number): Promise<void> {
  if (filling.value) return
  const asker = document.activeElement
  filling.value = true
  fillNote.value = null
  const only = onStep ? (f: FieldSpec) => f.step === onStep : undefined
  try {
    const made = await fillFields({
      kind: 'character',
      overview: draft.value.overview,
      name: displayNameForm.value,
      fields: [...writingFields(draft.value, only), ...writingContext(draft.value)],
      places: [],
      add_places: 0
    })
    let count = 0
    for (const [key, value] of Object.entries(made.values)) {
      const k = key as WritableKey
      // Written while the player waited? Theirs wins.
      if (k in draft.value && !draft.value[k].trim()) {
        draft.value[k] = value
        helped.value.add(k)
        count++
      }
    }
    if (count) burst(asker, { count: 16, spread: 80 })
    fillNote.value = count
      ? `Filled ${count} field${count === 1 ? '' : 's'} for $${Number(made.cost_usd).toFixed(4)} — they are marked; look them over and change anything.`
      : 'Nothing new to fill.'
  } catch (err) {
    fillNote.value = err instanceof Error ? err.message : 'Could not fill the fields this time.'
  } finally {
    filling.value = false
  }
}

function edited(key: WritableKey): void {
  helped.value.delete(key)
}

/** A choice button: picking the chosen one again clears it. */
function choose(key: WritableKey, option: string): void {
  draft.value[key] = draft.value[key].toLowerCase() === option.toLowerCase() ? '' : option
  edited(key)
}

const SEXES = ['Male', 'Female', 'Other']
const HEIGHTS = ['Tall', 'Average', 'Short']
const paintWords = computed(() => portraitPrompt(draft.value))

function setPortrait(assetId: string | null, frames: typeof draft.value.portraitFrames): void {
  draft.value.portraitAssetId = assetId
  draft.value.portraitFrames = frames
}

/* Each step's fields in named groups, beside the panel that helps with them. */
interface FieldGroup {
  kind: string
  title: string
  sub?: string
  fields: FieldSpec[]
}
const byKey = (keys: WritableKey[]): FieldSpec[] =>
  keys.flatMap((k) => CHARACTER_FIELDS.filter((f) => f.key === k))
/** Fields that take the whole row. */
const WIDE = new Set<WritableKey>(['history', 'exampleLine', 'marks', 'condition'])
const DEEPER_FIELDS = byKey(DEEPER_KEYS)
const deeperFilled = computed(() => DEEPER_KEYS.filter((k) => draft.value[k].trim()).length)
const groups = computed<FieldGroup[]>(() => {
  const short = (displayNameForm.value || 'they').split(/\s+/)[0]
  switch (step.value) {
    case 2:
      return [
        { kind: 'basics', title: 'Basics', fields: byKey(['age', 'race', 'sex']) },
        { kind: 'features', title: 'Features', fields: byKey(['hair', 'eyes', 'height', 'body']) },
        { kind: 'details', title: 'Distinctive details', fields: byKey(['marks']) }
      ]
    case 3:
      return [
        {
          kind: 'origins',
          title: 'Origins',
          sub: 'Where they come from.',
          fields: byKey(['history'])
        },
        {
          kind: 'personality',
          title: 'Personality',
          sub: 'How they meet the world.',
          fields: byKey(['traits', 'habits'])
        },
        {
          kind: 'motives',
          title: 'Motivations',
          sub: 'What they want, and what they avoid.',
          fields: byKey(['want', 'avoid'])
        }
      ]
    case 4:
      return [
        {
          kind: 'voice',
          title: `How ${short} speaks`,
          sub: 'Their voice, and a few things they would say.',
          fields: byKey(['tone', 'whenTheyCare', 'exampleLine'])
        }
      ]
    case 5:
      return [
        {
          kind: 'gear',
          title: 'Gear & condition',
          sub: 'What they carry, and how they are as the story begins.',
          fields: fieldsOnStep(5)
        }
      ]
    default:
      return []
  }
})
const summaries = computed(() => stepSummaries(draft.value))
</script>

<template>
  <main class="studio cstudio">
    <!-- the title and the step bar run across the page, above both columns -->
    <div class="cstudio__top">
      <div class="studio__head">
        <h1 class="studio__title">
          <span class="cstudio__eyebrow">Character studio</span>
          {{ isNew ? draft.presetName.trim() || 'New character' : displayName }}
        </h1>
        <span v-if="!isNew" class="cstudio__mode">Editing character</span>
        <span v-if="dirty" class="draft-badge ev-pop-once"
          ><span class="draft-badge__dot"></span>Unsaved</span
        >
      </div>
      <p v-if="recordLoading" class="studio__state" role="status">
        Reading the archive<span class="ev-dots" aria-hidden="true"
          ><span>.</span><span>.</span><span>.</span></span
        >
      </p>
      <p v-else-if="recordFailed" class="studio__state" role="alert">
        The archive did not answer ({{ presets.error.value }}) —
        <button type="button" class="studio__link" @click="retryPresets()">retry</button>
      </p>
      <p v-else-if="recordMissing" class="studio__state" role="alert">
        No character answers to that id.
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
        :steps="CHARACTER_STEPS.map((s) => s.title)"
        :current="step"
        @go="goStep" />
      <p v-if="step === 1" class="cstudio__sub">{{ stepInfo.sub }}</p>
    </div>

    <div class="studio__body">
      <!-- ————————————————— form column ————————————————— -->
      <div class="studio__left">
        <div class="cstudio__stage">
          <Transition :name="stepMotion">
            <div :key="step" class="cstudio__step">
              <!-- 1 · overview -->
              <template v-if="step === 1">
                <section class="card ev-card">
                  <div class="grid2">
                    <div>
                      <label class="ev-field-label" for="c-name">Name</label>
                      <input
                        v-if="isNew"
                        id="c-name"
                        v-model="draft.presetName"
                        class="ev-input"
                        maxlength="64"
                        placeholder="What are they called?" />
                      <p v-else id="c-name" class="cstudio__fixed">{{ displayName }}</p>
                    </div>
                    <div>
                      <label class="ev-field-label" for="c-pronouns">Pronouns</label>
                      <input
                        id="c-pronouns"
                        v-model="draft.pronouns"
                        class="ev-input"
                        maxlength="40"
                        placeholder="she/her, he/him, they/them… (optional)" />
                    </div>
                  </div>
                </section>
                <OverviewCard
                  v-model="draft.overview"
                  kind="character"
                  :name="displayNameForm"
                  placeholder="Who are they? e.g. A young tinker from the hill villages, cheerful and nosy, who ran away after breaking her master's best clock. Good with her hands, bad with secrets."
                  :empty="emptyCount(draft)"
                  :filling="filling"
                  :fill-note="fillNote"
                  @fill="fill()" />
              </template>

              <!-- 2–5 · the fields in named groups; 3 folds its deeper ones away -->
              <section v-else class="card ev-card">
                <div
                  v-for="group in groups"
                  :key="group.title"
                  class="grp"
                  :class="`grp--${group.kind}`">
                  <header class="grp__head">
                    <h2 class="grp__title">{{ group.title }}</h2>
                    <p v-if="group.sub" class="grp__sub">{{ group.sub }}</p>
                  </header>
                  <div class="cstudio__grid">
                    <div
                      v-for="f in group.fields"
                      :key="f.key"
                      class="cf"
                      :class="[`cf--${f.key}`, { 'cf--wide': WIDE.has(f.key) }]">
                      <label class="ev-field-label" :for="`c-${f.key}`">{{ f.label }}</label>
                      <div
                        v-if="f.key === 'sex' || f.key === 'height'"
                        class="seg"
                        :class="{ 'seg--helped': helped.has(f.key) }"
                        role="group"
                        :aria-label="f.label">
                        <button
                          v-for="opt in f.key === 'sex' ? SEXES : HEIGHTS"
                          :key="opt"
                          type="button"
                          class="seg__opt"
                          :class="{
                            'seg__opt--on': draft[f.key].toLowerCase() === opt.toLowerCase()
                          }"
                          :aria-pressed="draft[f.key].toLowerCase() === opt.toLowerCase()"
                          @click="choose(f.key, opt)">
                          {{ opt }}
                        </button>
                      </div>
                      <input
                        v-else-if="f.max <= 150"
                        :id="`c-${f.key}`"
                        v-model="draft[f.key]"
                        class="ev-input"
                        :class="{ 'is-helped': helped.has(f.key) }"
                        :maxlength="f.max"
                        :placeholder="f.hint"
                        @input="edited(f.key)" />
                      <textarea
                        v-else
                        :id="`c-${f.key}`"
                        v-model="draft[f.key]"
                        class="ev-input"
                        :class="{ 'is-helped': helped.has(f.key) }"
                        :maxlength="f.max"
                        :placeholder="f.hint"
                        :rows="f.key === 'exampleLine' ? 4 : f.max > 500 ? 3 : 2"
                        @input="edited(f.key)" />
                    </div>
                    <template v-if="group.kind === 'voice'">
                      <div class="cf">
                        <span class="ev-field-label">Speaking style</span>
                        <ChipEditor v-model="draft.styleTags" />
                      </div>
                      <div class="cf">
                        <label class="ev-field-label" for="c-strangers">With strangers</label>
                        <StudioSelect
                          id="c-strangers"
                          v-model="draft.withStrangers"
                          :options="STRANGER_STANCES" />
                      </div>
                    </template>
                  </div>
                </div>

                <CollapseBox
                  v-if="step === 3"
                  class="grp__more"
                  :title="`More about them · ${deeperFilled} of ${DEEPER_FIELDS.length} written`">
                  <div class="cstudio__grid">
                    <div v-for="f in DEEPER_FIELDS" :key="f.key" class="cf">
                      <label class="ev-field-label" :for="`c-${f.key}`">{{ f.label }}</label>
                      <textarea
                        :id="`c-${f.key}`"
                        v-model="draft[f.key]"
                        class="ev-input"
                        :class="{ 'is-helped': helped.has(f.key) }"
                        :maxlength="f.max"
                        :placeholder="f.hint"
                        rows="2"
                        @input="edited(f.key)" />
                    </div>
                  </div>
                </CollapseBox>

                <div v-if="step === 2 && draft.appearanceExtra" class="cf">
                  <label class="ev-field-label" for="c-appx">Earlier description</label>
                  <textarea
                    id="c-appx"
                    v-model="draft.appearanceExtra"
                    class="ev-input"
                    rows="2"
                    maxlength="1500" />
                </div>
                <template v-if="step === 3 && (draft.backgroundExtra || draft.personalityExtra)">
                  <div v-if="draft.backgroundExtra" class="cf">
                    <label class="ev-field-label" for="c-bgx">Earlier background notes</label>
                    <textarea
                      id="c-bgx"
                      v-model="draft.backgroundExtra"
                      class="ev-input"
                      rows="2"
                      maxlength="3000" />
                  </div>
                  <div v-if="draft.personalityExtra" class="cf">
                    <label class="ev-field-label" for="c-psx">Earlier personality notes</label>
                    <textarea
                      id="c-psx"
                      v-model="draft.personalityExtra"
                      class="ev-input"
                      rows="2"
                      maxlength="1500" />
                  </div>
                </template>

                <div class="cstudio__fill">
                  <button
                    type="button"
                    class="cstudio__fillbtn"
                    :class="{ 'is-writing': filling }"
                    :disabled="filling || emptyCount(draft, step) === 0"
                    @click="fill(step)">
                    <IconSparkle :size="14" />
                    {{
                      filling
                        ? 'Writing…'
                        : emptyCount(draft, step) === 0
                          ? 'All filled on this step'
                          : step === 5
                            ? 'Suggest from everything above'
                            : `Fill the ${emptyCount(draft, step)} empty here from the overview`
                    }}
                  </button>
                  <span v-if="fillNote" class="cstudio__fillnote" role="status">{{
                    fillNote
                  }}</span>
                </div>
              </section>

              <!-- 5 · each step at a glance, one click from changing it -->
              <section v-if="step === 5" class="card ev-card">
                <header class="grp__head">
                  <h2 class="grp__title">Review your character</h2>
                  <p class="grp__sub">Each step at a glance; open one to change it.</p>
                </header>
                <ul class="recap ev-rise">
                  <li v-for="line in summaries" :key="line.step" class="recap__row">
                    <span class="recap__step">{{ CHARACTER_STEPS[line.step - 1]!.title }}</span>
                    <span class="recap__text" :class="{ 'recap__text--empty': !line.text }">
                      {{ line.text || 'Nothing written yet' }}
                    </span>
                    <button type="button" class="recap__edit" @click="goStep(line.step)">
                      Edit <IconArrowRight :size="12" />
                    </button>
                  </li>
                </ul>
              </section>
            </div>
          </Transition>
        </div>

        <!-- the last step makes it real: create, or publish the changes -->
        <section v-if="step === lastStep" class="cstudio__finish">
          <template v-if="isNew">
            <p v-if="nameMissing" class="studio__state" role="status">
              Give them a name on the Overview step to create them.
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
                This draft already created a character.
                <template v-if="creation.supersededEdits.value">
                  Newer edits are still in the form — open it to apply them there, or create a
                  separate one.
                </template>
              </p>
              <button type="button" class="cta cta--sm" @click="openRecoveredCharacter">
                Open the character
              </button>
              <button type="button" class="ghost ghost--sm" @click="createSeparateCharacter">
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
            <p v-else class="cstudio__finishnote">
              Creating puts them in your library, ready for any story. Until then they are kept on
              this device whenever you save the draft.
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
            <p class="cstudio__finishnote">
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

      <CharacterPreviewPanel
        v-if="step === lastStep"
        title="Character sheet"
        :draft="draft"
        :name="displayNameForm" />
      <CharacterSidePanel
        v-else
        :step="step"
        :draft="draft"
        :name="displayNameForm"
        :paint-words="paintWords"
        @go="goStep"
        @portrait="setPortrait" />
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
          class="cstudio__next"
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
                  : 'Create character'
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
.cstudio__top {
  container-type: inline-size;
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-bottom: 14px;
}
.cstudio .studio__body {
  align-items: stretch;
}
.cstudio .studio__left {
  container-type: normal;
}
.cstudio__step {
  flex: 1;
}
.cstudio__step > .card:last-child {
  flex: 1;
}
.cstudio__eyebrow {
  display: block;
  margin-bottom: 4px;
  font-family: var(--font-ui);
  font-size: 15px;
  font-weight: 500;
  color: var(--ink-3);
}
.cstudio__mode {
  align-self: flex-end;
  padding-left: 14px;
  border-left: 1px solid var(--line);
  font-family: var(--font-ui);
  font-size: 15.5px;
  color: var(--ink-3);
}
.cstudio__sub {
  margin: 2px 0 12px;
  font-size: 17px;
  color: var(--ink-3);
}
.cstudio__step {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.cstudio__fixed {
  padding: 10px 2px;
  font-family: var(--font-display);
  font-size: 24px;
  font-weight: 600;
  color: var(--ink);
}
.cstudio__grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px 18px;
}
.cf {
  min-width: 0;
}
.cf--wide {
  grid-column: 1 / -1;
}
/* named groups of fields, divided by a hairline */
.grp + .grp {
  margin-top: 20px;
  padding-top: 18px;
  border-top: 1px solid var(--line-soft);
}
.grp__head {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 4px 12px;
  margin-bottom: 12px;
}
.grp__title {
  font-family: var(--font-display);
  font-size: 24px;
  font-weight: 600;
  color: var(--ink);
}
.grp__sub {
  font-family: var(--font-ui);
  font-size: 14.5px;
  color: var(--ink-3);
}
.grp--basics .cstudio__grid {
  grid-template-columns: minmax(80px, 0.5fr) minmax(0, 1fr) minmax(0, 1.4fr);
}
.grp__more {
  margin-top: 20px;
}
.grp__more .cstudio__grid {
  padding: 4px 2px 6px;
}
.recap {
  list-style: none;
  display: grid;
  gap: 8px;
}
.recap__row {
  display: grid;
  grid-template-columns: 190px minmax(0, 1fr) auto;
  align-items: center;
  gap: 14px;
  padding: 11px 14px;
  border-radius: 10px;
  background: #f6eedb;
}
.recap__step {
  font-family: var(--font-ui);
  font-weight: 700;
  font-size: 15px;
  color: var(--ink);
}
.recap__text {
  min-width: 0;
  font-size: 15.5px;
  line-height: 1.4;
  color: var(--ink-2);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.recap__text--empty {
  font-style: italic;
  color: var(--muted);
}
.recap__edit {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-family: var(--font-ui);
  font-size: 15px;
  color: var(--teal-ink);
}
.recap__edit:hover {
  text-decoration: underline;
  text-underline-offset: 3px;
}
.is-helped {
  border-color: #e0b07a !important;
  background: linear-gradient(180deg, #fff8ec, #fdf1de) !important;
  box-shadow: inset 3px 0 0 var(--ember) !important;
}
/* two or three choices side by side */
.seg {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  padding: 3px;
  margin: -3px;
  border-radius: 12px;
}
.seg--helped {
  box-shadow: inset 3px 0 0 var(--ember);
  background: #fdf1de;
}
.seg__opt {
  flex: 1 1 0;
  min-width: 72px;
  height: 42px;
  border-radius: 9px;
  border: 1px solid #b9cfd1;
  background: #f7faf8;
  font-size: 16px;
  color: var(--ink-2);
  transition:
    background-color 0.15s ease,
    color 0.15s ease,
    border-color 0.15s ease,
    transform 0.2s var(--ease-spring);
}
.seg__opt:hover {
  border-color: #5f9488;
}
.seg__opt--on {
  background: linear-gradient(180deg, var(--teal-hi), var(--teal));
  border-color: #0c3f46;
  color: var(--cream-on-teal);
  transform: scale(1.02);
}
.cstudio__fill {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
  margin-top: 18px;
}
.cstudio__fillbtn {
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
.cstudio__fillbtn svg {
  color: var(--ember);
}
.cstudio__fillbtn:hover:not(:disabled) {
  transform: translateY(-1px);
}
.cstudio__fillbtn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}
.cstudio__fillnote {
  font-family: var(--font-ui);
  font-size: 15px;
  color: var(--ink-3);
}
/* the last step's note: a quiet line under the review, not a card of its own */
.cstudio__finish {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px 16px;
  border-radius: 10px;
  background: #efe6d1;
  border: 1px solid var(--line-soft);
}
.cstudio__finishnote {
  font-family: var(--font-ui);
  font-size: 15px;
  color: var(--ink-3);
}
.cstudio__next {
  width: auto;
  min-width: 240px;
}
/* the old step and the new share one cell while they swap: nothing jumps */
.cstudio__stage {
  flex: 1;
  display: grid;
  overflow-x: clip;
}
.cstudio__stage > .cstudio__step {
  grid-area: 1 / 1;
  min-width: 0;
}
/* fields the writing helper filled glow as they arrive */
.is-helped {
  animation: cs-helped 1.4s var(--ease-out);
}
@keyframes cs-helped {
  from {
    outline: 3px solid rgba(220, 122, 60, 0.6);
    outline-offset: 5px;
  }
  to {
    outline: 3px solid rgba(220, 122, 60, 0);
    outline-offset: 0;
  }
}
.cstudio__fillbtn:active:not(:disabled) {
  transform: scale(0.97);
}
.cstudio__fillbtn.is-writing svg {
  animation: cs-twinkle 1.1s var(--ease-io) infinite;
}
@keyframes cs-twinkle {
  50% {
    transform: rotate(180deg) scale(1.3);
    opacity: 0.6;
  }
}
.recap__edit svg {
  transition: transform 0.25s var(--ease-settle);
}
.recap__edit:hover svg {
  transform: translateX(3px);
}
@media (max-width: 760px) {
  .cstudio__grid,
  .grp--basics .cstudio__grid {
    grid-template-columns: minmax(0, 1fr);
  }
  .recap__row {
    grid-template-columns: minmax(0, 1fr) auto;
  }
  .recap__text {
    grid-column: 1 / -1;
    grid-row: 2;
    white-space: normal;
  }
  .cstudio__next {
    min-width: 0;
    flex: 1 1 100%;
  }
}
</style>
