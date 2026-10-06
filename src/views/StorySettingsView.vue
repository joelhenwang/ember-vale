<!--
  StorySettingsView — this story's own settings: the player's words around
  every storyteller prompt and every picture prompt, and per character
  around every picture of them. Saved per story (save), applied from the
  next turn / the next picture. Pure form logic: src/game/storyPrompts.ts.
-->
<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import SaveBar from '../components/ui/SaveBar.vue'
import PageIntro from '../components/ui/PageIntro.vue'
import IconArrowLeft from '../components/icons/IconArrowLeft.vue'
import IconFeather from '../components/icons/IconFeather.vue'
import IconImage from '../components/icons/IconImage.vue'
import IconUsers from '../components/icons/IconUsers.vue'
import IconInfo from '../components/icons/IconInfo.vue'
import { assetUrl, getStory, getStoryPrompts, saveStoryPrompts } from '../api/worldsim'
import { isVersionConflict } from '../api/http'
import {
  EXAMPLES,
  IMAGE_LIMIT,
  LLM_LIMIT,
  emptyStoryWords,
  storyWordsFrom,
  storyWordsRequest,
  validateStoryWords,
  type StoryWordsForm
} from '../game/storyPrompts'

const route = useRoute()
const storyId = computed(() => String(route.params.storyId ?? ''))

const title = ref<string>('')
const form = ref<StoryWordsForm>(emptyStoryWords())
const baseline = ref<StoryWordsForm>(emptyStoryWords())
const version = ref(0)
const loading = ref(true)
const saving = ref(false)
const error = ref<string | null>(null)
const savedFlash = ref(false)
let flashTimer: ReturnType<typeof setTimeout> | undefined

const errors = computed(() => validateStoryWords(form.value))
const valid = computed(() => Object.keys(errors.value).length === 0)
const dirty = computed(() => JSON.stringify(form.value) !== JSON.stringify(baseline.value))

async function load(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    const [story, words] = await Promise.all([
      getStory(storyId.value).catch(() => null),
      getStoryPrompts(storyId.value)
    ])
    title.value = story?.title ?? 'This story'
    version.value = words.version
    baseline.value = storyWordsFrom(words)
    form.value = storyWordsFrom(words)
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Could not load this story’s settings.'
  } finally {
    loading.value = false
  }
}

async function save(): Promise<void> {
  if (!dirty.value || !valid.value || saving.value) return
  saving.value = true
  error.value = null
  try {
    const saved = await saveStoryPrompts(
      storyId.value,
      storyWordsRequest(form.value, baseline.value, version.value)
    )
    version.value = saved.version
    baseline.value = storyWordsFrom(saved)
    form.value = storyWordsFrom(saved)
    savedFlash.value = true
    clearTimeout(flashTimer)
    flashTimer = setTimeout(() => (savedFlash.value = false), 1400)
  } catch (err) {
    error.value = isVersionConflict(err)
      ? 'These settings changed elsewhere. Reload the page to see the latest.'
      : err instanceof Error
        ? err.message
        : 'Could not save.'
  } finally {
    saving.value = false
  }
}

function discard(): void {
  form.value = structuredClone(baseline.value)
  error.value = null
}

type StoryField = 'llmPrefix' | 'llmSuffix' | 'imagePrefix' | 'imageSuffix'
function useExample(field: StoryField): void {
  form.value[field] = EXAMPLES[field]
}

onMounted(load)
onBeforeUnmount(() => clearTimeout(flashTimer))
</script>

<template>
  <main class="ssettings">
    <header class="ssettings__head">
      <RouterLink class="ssettings__back" :to="{ name: 'story-adventure', params: { storyId } }">
        <IconArrowLeft :size="14" /> Back to the story
      </RouterLink>
      <PageIntro
        :title="`Story settings${title ? ` · ${title}` : ''}`"
        sub="Your own words, added to everything the AI writes and paints in this story. Changes apply from the next turn or the next picture." />
    </header>

    <p v-if="error" class="ssettings__alert" role="alert">{{ error }}</p>
    <p v-if="loading" class="ev-info"><IconInfo :size="14" /> Loading…</p>

    <template v-else>
      <!-- storyteller ------------------------------------------------------- -->
      <section class="card ev-card">
        <header class="card__head">
          <span class="card__icon"><IconFeather :size="20" /></span>
          <div>
            <h2 class="card__title">Storyteller</h2>
            <p class="card__sub">
              Added around every prompt the storyteller AI gets in this story: what characters
              decide, how scenes resolve, the narration, the director and day summaries.
            </p>
          </div>
        </header>
        <div class="pair">
          <label class="field">
            <span class="field__label">Before every prompt</span>
            <textarea
              v-model="form.llmPrefix"
              class="ev-input words"
              rows="3"
              :placeholder="EXAMPLES.llmPrefix" />
            <span class="field__meta">
              <button
                v-if="!form.llmPrefix"
                type="button"
                class="linkbtn"
                @click="useExample('llmPrefix')">
                Use the example
              </button>
              <span v-else :class="{ over: errors.llmPrefix }"
                >{{ form.llmPrefix.length }} / {{ LLM_LIMIT }}</span
              >
            </span>
          </label>
          <label class="field">
            <span class="field__label">After every prompt</span>
            <textarea
              v-model="form.llmSuffix"
              class="ev-input words"
              rows="3"
              :placeholder="EXAMPLES.llmSuffix" />
            <span class="field__meta">
              <button
                v-if="!form.llmSuffix"
                type="button"
                class="linkbtn"
                @click="useExample('llmSuffix')">
                Use the example
              </button>
              <span v-else :class="{ over: errors.llmSuffix }"
                >{{ form.llmSuffix.length }} / {{ LLM_LIMIT }}</span
              >
            </span>
          </label>
        </div>
        <p class="card__note">
          <IconInfo :size="14" /> Good for tone, style and rules of the world. Words that ask for a
          different answer format can confuse the storyteller, so keep to how the story should feel.
        </p>
      </section>

      <!-- pictures ----------------------------------------------------------- -->
      <section class="card ev-card">
        <header class="card__head">
          <span class="card__icon"><IconImage :size="20" /></span>
          <div>
            <h2 class="card__title">Pictures</h2>
            <p class="card__sub">
              Added around every picture painted for this story: portraits, places and story
              moments.
            </p>
          </div>
        </header>
        <div class="pair">
          <label class="field">
            <span class="field__label">Before every picture</span>
            <input
              v-model="form.imagePrefix"
              class="ev-input"
              :placeholder="EXAMPLES.imagePrefix" />
            <span class="field__meta">
              <span :class="{ over: errors.imagePrefix }"
                >{{ form.imagePrefix.length }} / {{ IMAGE_LIMIT }}</span
              >
            </span>
          </label>
          <label class="field">
            <span class="field__label">After every picture</span>
            <input
              v-model="form.imageSuffix"
              class="ev-input"
              :placeholder="EXAMPLES.imageSuffix" />
            <span class="field__meta">
              <span :class="{ over: errors.imageSuffix }"
                >{{ form.imageSuffix.length }} / {{ IMAGE_LIMIT }}</span
              >
            </span>
          </label>
        </div>
      </section>

      <!-- characters --------------------------------------------------------- -->
      <section class="card ev-card">
        <header class="card__head">
          <span class="card__icon"><IconUsers :size="20" /></span>
          <div>
            <h2 class="card__title">Characters in pictures</h2>
            <p class="card__sub">
              Added right around a character whenever they are painted: their portrait and every
              story moment they are in. Faces stay the same anyway; use this for what should always
              be there, like a scar or a favourite scarf.
            </p>
          </div>
        </header>
        <ul class="people">
          <li v-for="c in form.characters" :key="c.characterId" class="person">
            <span class="person__face">
              <img v-if="c.portraitAssetId" :src="assetUrl(storyId, c.portraitAssetId)" alt="" />
              <span v-else>{{ c.name.slice(0, 1) }}</span>
            </span>
            <span class="person__name">{{ c.name }}</span>
            <label class="person__field">
              <span class="sr-only">Before {{ c.name }}</span>
              <input v-model="c.prefix" class="ev-input" placeholder="before, e.g. tall," />
            </label>
            <label class="person__field">
              <span class="sr-only">After {{ c.name }}</span>
              <input
                v-model="c.suffix"
                class="ev-input"
                :placeholder="`after, e.g. ${EXAMPLES.characterSuffix}`" />
            </label>
            <span
              v-if="
                errors[`character:${c.characterId}:prefix`] ||
                errors[`character:${c.characterId}:suffix`]
              "
              class="person__err">
              At most {{ IMAGE_LIMIT }} characters each.
            </span>
          </li>
        </ul>
      </section>
    </template>

    <SaveBar :dirty="dirty" :saved="savedFlash" secondary-label="Discard" @secondary="discard">
      <template #end>
        <button
          type="button"
          class="cta cta--foot"
          :disabled="!dirty || !valid || saving"
          @click="save">
          {{ saving ? 'Saving…' : 'Save story settings' }}
        </button>
      </template>
    </SaveBar>
  </main>
</template>

<style scoped>
.ssettings {
  max-width: 1100px;
  margin: 0 auto;
  padding: 14px 16px 40px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.ssettings__back {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 14.5px;
  color: var(--teal-ink);
  margin-bottom: 8px;
}
.ssettings__alert {
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
.pair {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 18px 24px;
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
.field__meta {
  display: flex;
  justify-content: flex-end;
  font-size: 13px;
  color: var(--muted);
  font-variant-numeric: tabular-nums;
}
.over {
  color: #b3542e;
  font-weight: 600;
}
.words {
  height: auto;
  min-height: 84px;
  padding: 10px 12px;
  resize: vertical;
  line-height: 1.45;
}
.linkbtn {
  font-size: 13px;
  color: var(--teal-ink);
  text-decoration: underline;
  text-underline-offset: 3px;
}
.people {
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.person {
  display: grid;
  grid-template-columns: 44px 120px minmax(0, 1fr) minmax(0, 1fr);
  align-items: center;
  gap: 12px;
}
.person__face {
  width: 44px;
  height: 44px;
  border-radius: 50%;
  overflow: hidden;
  border: 2px solid #e2d3ae;
  background: #efe4c8;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-weight: 600;
  color: var(--ink-2);
}
.person__face img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.person__name {
  font-weight: 600;
  color: var(--ink);
}
.person__err {
  grid-column: 3 / -1;
  font-size: 13px;
  color: #b3542e;
}
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
}
@media (max-width: 760px) {
  .pair {
    grid-template-columns: 1fr;
  }
  .person {
    grid-template-columns: 44px minmax(0, 1fr);
  }
  .person__field {
    grid-column: 1 / -1;
  }
}
</style>
