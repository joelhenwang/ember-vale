<!--
  CharacterStudioView — the "Character studio" screen (mockup: Give {name} a
  voice). Reached from two origins, told apart only by route meta.from:
    · /library/character/:id     (editing a catalogued character)
    · /new-story/character/new   (creating one from the wizard)

  Layout contract:
    · This file owns the form column (identity/personality cards) and the
      save/continue footer. Everything shared with WorldStudioView — crumbs,
      card chrome, tabs, .cta/.ghost, stepper spacing — is styled once in
      src/styles/studio.css. Do not redeclare those classes in a scoped block.
    · The right-hand preview column lives in CharacterPreviewPanel.vue and
      pulls its own state from the draft store; the two halves never pass
      props, they just watch the same reactive draft.

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
import {
  ensureCharDraft,
  isCharDirty,
  saveCharDraft,
  STRANGER_STANCES,
  suggestCharacter
} from '../game/studio'
import { packCharacter, unpackCharacter } from '../game/studioFields'
import CharacterPreviewPanel from '../components/studio/CharacterPreviewPanel.vue'
import InlineStepper from '../components/studio/InlineStepper.vue'
import ChipEditor from '../components/studio/ChipEditor.vue'
import CollapseBox from '../components/studio/CollapseBox.vue'
import SuggestButton from '../components/studio/SuggestButton.vue'
import StudioSelect from '../components/studio/StudioSelect.vue'
import SaveBar from '../components/ui/SaveBar.vue'
import IconSparkle from '../components/icons/IconSparkle.vue'
import IconBook from '../components/icons/IconBook.vue'
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

/* The breadcrumb + return target depend on which flow opened the studio. */
const fromLibrary = computed(() => route.meta.from === 'library')
const originCrumb = computed(() => (fromLibrary.value ? 'Library' : 'New Story'))
const originRoute = computed(() => (fromLibrary.value ? '/library?tab=characters' : '/new-story'))

const draft = computed(() => ensureCharDraft(id.value))

// DEMO: the 4-step stepper is cosmetic for now — production will gate
// Continue on per-step validation and route each step (…/step/:n).
const step = ref(2)

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
    .catch(() => {})
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
const nextLabel = computed(() =>
  step.value <= 2 ? 'Background' : step.value === 3 ? 'Review' : 'Finish'
)
async function advance(): Promise<void> {
  if (step.value < 4) {
    step.value++
    return
  }
  // Navigation waits for persistence: a failed save keeps the user here
  // with their edits intact instead of leaving anyway.
  if (await save()) router.push(originRoute.value)
}

/* ————— suggest ————— */
function suggest(): void {
  suggestCharacter(draft.value)
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
          <router-link :to="originRoute">Characters</router-link>
          <span class="crumbs__sep">/</span>
          <span class="crumbs__here">{{ isNew ? 'New character' : displayName }}</span>
        </nav>

        <div class="studio__head">
          <h1 class="studio__title">
            {{ isNew ? 'Give them a voice' : `Give ${displayName} a voice` }}
          </h1>
          <span class="draft-badge"><span class="draft-badge__dot"></span>Draft</span>
        </div>
        <p class="studio__sub">Shape how they think, react, and speak.</p>
        <p v-if="recordLoading" class="studio__state" role="status">Reading the archive…</p>
        <p v-else-if="recordFailed" class="studio__state" role="alert">
          The archive did not answer ({{ presets.error.value }}) —
          <button type="button" class="studio__link" @click="retryPresets()">retry</button>
        </p>
        <p v-else-if="recordMissing" class="studio__state" role="alert">
          No character answers to that id.
        </p>

        <InlineStepper
          class="studio__stepper"
          :steps="[
            'Identity & appearance',
            'Personality & voice',
            'Background & connections',
            'Review'
          ]"
          :current="step"
          @go="step = $event" />

        <section class="card ev-card">
          <header class="card__head">
            <h2 class="card__title"><IconSparkle :size="15" /> What drives {{ displayName }}?</h2>
            <SuggestButton @suggest="suggest" />
          </header>
          <div class="grid2">
            <div>
              <label class="ev-field-label" for="c-want">What do they want?</label>
              <textarea
                id="c-want"
                v-model="draft.want"
                class="ev-input"
                placeholder="The want under the want…" />
            </div>
            <div>
              <label class="ev-field-label" for="c-avoid">What do they avoid?</label>
              <textarea
                id="c-avoid"
                v-model="draft.avoid"
                class="ev-input"
                placeholder="The thing they’ll never say out loud…" />
            </div>
            <div>
              <label class="ev-field-label" for="c-pressure">Under pressure</label>
              <textarea
                id="c-pressure"
                v-model="draft.pressure"
                class="ev-input"
                placeholder="How the mask slips…" />
            </div>
            <div>
              <label class="ev-field-label" for="c-contradiction">A defining contradiction</label>
              <textarea
                id="c-contradiction"
                v-model="draft.contradiction"
                class="ev-input"
                placeholder="Two truths that don’t fit…" />
            </div>
          </div>
        </section>

        <section class="card ev-card">
          <header class="card__head">
            <h2 class="card__title"><IconBook :size="19" /> How they speak</h2>
          </header>
          <div class="grid2">
            <div>
              <span class="ev-field-label">Speaking style</span>
              <ChipEditor v-model="draft.styleTags" />
            </div>
            <div>
              <label class="ev-field-label" for="c-strangers">With strangers</label>
              <StudioSelect
                id="c-strangers"
                v-model="draft.withStrangers"
                :options="STRANGER_STANCES" />
            </div>
            <div>
              <label class="ev-field-label" for="c-care">When they care</label>
              <input
                id="c-care"
                v-model="draft.whenTheyCare"
                class="ev-input"
                placeholder="Care looks like…" />
            </div>
            <div>
              <label class="ev-field-label" for="c-line">Example line</label>
              <input id="c-line" v-model="draft.exampleLine" class="ev-input" placeholder="“…”" />
            </div>
          </div>
          <CollapseBox title="Boundaries & deeper motivations" class="card__more">
            <div class="grid2">
              <div>
                <label class="ev-field-label" for="c-bounds">Will not cross</label>
                <textarea
                  id="c-bounds"
                  v-model="draft.boundaries"
                  class="ev-input"
                  placeholder="Even for someone they love…" />
              </div>
              <div>
                <label class="ev-field-label" for="c-fear">Secret fear</label>
                <textarea
                  id="c-fear"
                  v-model="draft.secretFear"
                  class="ev-input"
                  placeholder="The one that gets quieter, not louder…" />
              </div>
            </div>
          </CollapseBox>
        </section>

        <section class="card ev-card" aria-label="Publication">
          <header class="card__head">
            <h2 class="card__title">Publication</h2>
          </header>
          <div v-if="isNew">
            <p class="studio__state" role="status">
              New characters live on this device until first publication.
            </p>
            <div>
              <span class="ev-field-label">Name</span>
              <input
                v-model="draft.presetName"
                class="ev-input"
                maxlength="64"
                placeholder="Name this character" />
            </div>
            <p v-if="creation.status.value === 'failed'" class="studio__state" role="alert">
              {{ creation.error.value }}
            </p>
            <p
              v-if="creation.pending.value && creationFormDiffers"
              class="studio__state"
              role="status">
              An earlier creation is still unresolved — retrying replays the original request under
              its original key. Newer edits stay in the form and are never sent implicitly.
            </p>
            <p
              v-if="creation.pending.value && !creation.requestPersisted.value"
              class="studio__state"
              role="alert">
              The creation request is in memory only (storage unavailable) — retry works in this
              tab, but a reload before the receipt lands may create a duplicate. Keep this tab open.
            </p>
            <div v-if="creation.recoveredId.value" class="preview__actions">
              <p v-if="!creation.noticeDismissed.value" class="studio__state" role="status">
                Recovered preset {{ creation.recoveredId.value }} from the original request.
                <template v-if="creation.supersededEdits.value">
                  Newer edits are still in the form — open the preset to apply them there, or create
                  a separate preset explicitly.
                </template>
              </p>
              <p v-else class="studio__state" role="status">
                This draft already created preset {{ creation.recoveredId.value }}.
              </p>
              <button type="button" class="cta cta--sm" @click="openRecoveredCharacter">
                Open preset
              </button>
              <button type="button" class="ghost ghost--sm" @click="createSeparateCharacter">
                Create a separate preset
              </button>
              <button
                v-if="creation.supersededEdits.value"
                type="button"
                class="ghost ghost--sm"
                title="Forget the set-aside edits. The created preset stays associated with this draft."
                @click="creation.discardNewerEdits()">
                Discard newer edits
              </button>
              <button
                v-if="!creation.noticeDismissed.value"
                type="button"
                class="ghost ghost--sm"
                title="Hide this notice. The created preset and any set-aside edits are kept."
                @click="creation.dismissRecovery()">
                Dismiss
              </button>
            </div>
            <div v-else class="preview__actions">
              <button
                type="button"
                class="cta cta--sm"
                :disabled="creation.status.value === 'creating'"
                @click="createCharacter">
                {{
                  creation.status.value === 'creating'
                    ? 'Creating…'
                    : creation.pending.value
                      ? 'Retry creation'
                      : 'Create preset'
                }}
              </button>
              <button
                v-if="creation.pending.value && creationFormDiffers"
                type="button"
                class="ghost ghost--sm"
                title="The unresolved request may already have created a preset; use only if you intend a second one."
                @click="createSeparateCharacter">
                Create a separate preset instead
              </button>
            </div>
            <p v-if="deviceSavedFlash" class="studio__state" role="status">Saved on this device.</p>
            <p v-if="deviceStorageFailed" class="studio__state" role="alert">
              This device would not keep the draft (storage unavailable) — keep this tab open until
              you can save elsewhere.
            </p>
          </div>
          <div v-else>
            <p v-if="pubStatus" class="studio__state" role="status">{{ pubStatus }}</p>
            <p v-if="unsavedAfterPublish" class="studio__state" role="status">
              Newer edits are still unsaved — save or publish again before leaving, or finish from
              the button below once everything is saved.
            </p>
            <p v-if="editor.status.value === 'failed'" class="studio__state" role="alert">
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
            <div class="preview__actions">
              <button
                type="button"
                class="cta cta--sm"
                :disabled="
                  editor.status.value === 'publishing' || editor.status.value === 'loading'
                "
                @click="publish">
                {{
                  editor.status.value === 'publishing'
                    ? 'Publishing…'
                    : editor.pendingPublication.value
                      ? 'Retry publish'
                      : 'Publish new revision'
                }}
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

      <CharacterPreviewPanel />
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
