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
import { computed, onBeforeUnmount, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { catalog } from '../game/catalog'
import {
  ensureCharDraft,
  isCharDirty,
  saveCharDraft,
  STRANGER_STANCES,
  suggestCharacter
} from '../game/studio'
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
const character = computed(() => catalog.characters.find((c) => c.id === id.value))
const displayName = computed(() => character.value?.name ?? 'the new character')

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
let saveTimer: ReturnType<typeof setTimeout> | undefined
function save(): void {
  saveCharDraft(id.value)
  savedFlash.value = true
  clearTimeout(saveTimer)
  saveTimer = setTimeout(() => (savedFlash.value = false), 1400)
}
onBeforeUnmount(() => clearTimeout(saveTimer))

/* ————— advance ————— */
const nextLabel = computed(() =>
  step.value <= 2 ? 'Background' : step.value === 3 ? 'Review' : 'Finish'
)
function advance(): void {
  if (step.value < 4) {
    step.value++
    return
  }
  save()
  router.push(originRoute.value)
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
          <span class="crumbs__here">{{ character ? displayName : 'New character' }}</span>
        </nav>

        <div class="studio__head">
          <h1 class="studio__title">
            {{ character ? `Give ${displayName} a voice` : 'Give them a voice' }}
          </h1>
          <span class="draft-badge"><span class="draft-badge__dot"></span>Draft</span>
        </div>
        <p class="studio__sub">Shape how they think, react, and speak.</p>

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
