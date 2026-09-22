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
        'secretFear'
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

async function save(): Promise<void> {
  if (isNew.value) {
    const kept = storeLocalPreset('character', id.value, { ...draft.value })
    // Durable creation identity, minted once: stored, not yet sent. First
    // publication stays unwired until the server receipt lands.
    stableCreateKey(`character-${id.value}`)
    deviceStorageFailed.value = !kept
    if (!kept) return
    saveCharDraft(id.value)
    deviceSavedFlash.value = true
    savedFlash.value = true
    clearTimeout(saveTimer)
    saveTimer = setTimeout(() => {
      savedFlash.value = false
      deviceSavedFlash.value = false
    }, 1400)
    return
  }
  editor.fields.value = { ...editor.fields.value, ...packCharacter(draft.value) }
  const ok = await editor.save(id.value)
  if (ok) {
    saveCharDraft(id.value)
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
  editor.fields.value = { ...editor.fields.value, ...packCharacter(draft.value) }
  const presetVersion = editor.baseDetail.value?.version ?? 0
  const view = await editor.publish(id.value, presetVersion)
  if (!view) return
  saveCharDraft(id.value)
  if (!fromLibrary.value) {
    // Nested return: the wizard offers deliberate adoption of the exact
    // published revision — never an automatic switch.
    await router.push({
      path: '/new-story',
      query: {
        adopt_kind: 'character',
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

/* ————— advance ————— */
const nextLabel = computed(() =>
  step.value <= 2 ? 'Background' : step.value === 3 ? 'Review' : 'Finish'
)
function advance(): void {
  if (step.value < 4) {
    step.value++
    return
  }
  void save().then(() => {
    router.push(originRoute.value)
  })
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
