<!--
  CharacterSidePanel — the studio's right-hand panel, changing with the step
  so it helps with the task at hand:
    1 Overview   — the concept: where they come from, what draws them on,
                   what they keep close (read from the later steps' fields);
    2 Appearance — the portrait studio: paint, import, frame, where it shows;
    3 Background — the compass: wants, fears, lines they will not cross;
    4 Voice      — how they sound: their lines, or a sample in a situation
                   the player picks (written only when asked);
  Review shows the whole character sheet (CharacterPreviewPanel).
-->
<script setup lang="ts">
import { computed, ref, type Component } from 'vue'
import { libraryAssetUrl, sampleVoice } from '../../api/worldsim'
import {
  VOICE_SITUATIONS,
  compassRows,
  conceptRows,
  identityLine,
  sayings,
  voiceFields
} from '../../game/characterForm'
import type { CharacterDraft, PortraitFrames } from '../../game/studio'
import type { WritingSampleView } from '../../../content/clients/worldsim'
import FramedImage from '../ui/FramedImage.vue'
import PortraitPicker from './PortraitPicker.vue'
import StudioSelect from './StudioSelect.vue'
import IconSparkle from '../icons/IconSparkle.vue'
import IconEmblem from '../icons/IconEmblem.vue'
import IconGlobe from '../icons/IconGlobe.vue'
import IconSatchel from '../icons/IconSatchel.vue'
import IconEye from '../icons/IconEye.vue'
import IconLock from '../icons/IconLock.vue'
import IconBranch from '../icons/IconBranch.vue'
import IconHeart from '../icons/IconHeart.vue'
import IconUser from '../icons/IconUser.vue'
import IconFeather from '../icons/IconFeather.vue'

const props = defineProps<{
  step: number
  draft: CharacterDraft
  name: string
  /** Words to paint them from (Appearance). */
  paintWords: string
}>()
const emit = defineEmits<{
  go: [step: number]
  portrait: [assetId: string | null, frames: PortraitFrames | null]
}>()

const src = computed(() =>
  props.draft.portraitAssetId ? libraryAssetUrl(props.draft.portraitAssetId, 640) : ''
)
const who = computed(() => identityLine(props.draft))
const traits = computed(() =>
  props.draft.traits
    .split(/[,;]/)
    .map((t) => t.trim())
    .filter((t) => t && t.length <= 24)
    .slice(0, 4)
)
const shortName = computed(() => (props.name || 'They').split(/\s+/)[0])

const HEADS: Record<number, { title: string; sub: string }> = {
  1: { title: 'Character concept', sub: 'Who they are at heart, from what you have written.' },
  2: { title: 'Portrait studio', sub: 'Painted from how they look, or your own picture.' },
  3: { title: 'Character compass', sub: 'What drives them, and what holds them back.' },
  4: { title: 'How they sound', sub: 'Hear them before the story does.' }
}
const head = computed(() => HEADS[props.step] ?? HEADS[1])

const CONCEPT_ICONS: Record<string, Component> = {
  history: IconGlobe,
  want: IconSparkle,
  carries: IconSatchel
}
const COMPASS_ICONS: Record<string, Component> = {
  want: IconSparkle,
  secretFear: IconEye,
  boundaries: IconLock,
  contradiction: IconBranch,
  pressure: IconHeart
}
/** Where an unwritten row is filled in. */
const ROW_STEP: Record<string, number> = { history: 3, want: 3, carries: 5 }

const concept = computed(() => conceptRows(props.draft))
const compass = computed(() => compassRows(props.draft))

// Voice: their own lines until a sample is asked for.
const situation = ref<string>(VOICE_SITUATIONS[1])
const sample = ref<WritingSampleView | null>(null)
const sampling = ref(false)
const sampleError = ref<string | null>(null)
/** Each new sample replays its lines one after another. */
const sampleRun = ref(0)
const lines = computed(() => sayings(props.draft))

async function hear(): Promise<void> {
  sampling.value = true
  sampleError.value = null
  try {
    sample.value = await sampleVoice({
      name: props.name,
      fields: voiceFields(props.draft),
      situation: situation.value,
      other: 'A stranger'
    })
    sampleRun.value += 1
  } catch (err) {
    sampleError.value =
      err instanceof Error && err.message ? err.message : 'The sample could not be written.'
  } finally {
    sampling.value = false
  }
}
</script>

<template>
  <aside class="card ev-card side" :aria-label="head.title">
    <header class="side__head">
      <IconEmblem :size="22" class="side__emblem" />
      <div :key="step" class="side__headtext">
        <h2 class="side__title">{{ head.title }}</h2>
        <p class="side__sub">{{ head.sub }}</p>
      </div>
    </header>

    <!-- who they are, at a glance (the portrait studio shows the picture itself) -->
    <div v-if="step !== 2" class="side__who">
      <span class="side__pic">
        <FramedImage
          v-if="draft.portraitAssetId && draft.portraitFrames"
          :src="src"
          :frame="draft.portraitFrames.portrait"
          :alt="`${name} portrait`" />
        <button v-else type="button" class="side__nopic" @click="emit('go', 2)">
          <IconSparkle :size="20" />
          <span>Add a picture</span>
        </button>
      </span>
      <div class="side__id">
        <p class="side__name">{{ name || 'Unnamed' }}</p>
        <p v-if="!name && step === 4" class="side__line side__hint">
          Add a name to hear them in context.
        </p>
        <p v-if="draft.pronouns" class="side__pron">{{ draft.pronouns }}</p>
        <p v-if="who" class="side__line">{{ who }}</p>
        <ul v-if="traits.length" class="side__traits">
          <li v-for="t in traits" :key="t">{{ t }}</li>
        </ul>
      </div>
    </div>

    <!-- 1 · concept -->
    <ul v-if="step === 1" class="side__rows ev-rise">
      <li v-for="row in concept" :key="row.key" class="side__row">
        <span class="side__icon"><component :is="CONCEPT_ICONS[row.key]" :size="18" /></span>
        <span class="side__rowtext">
          <b>{{ row.label }}</b>
          <span v-if="row.text">{{ row.text }}</span>
          <button v-else type="button" class="side__later" @click="emit('go', ROW_STEP[row.key])">
            Not written yet — step {{ ROW_STEP[row.key] }}
          </button>
        </span>
      </li>
    </ul>

    <!-- 2 · portrait studio -->
    <PortraitPicker
      v-else-if="step === 2"
      class="side__in"
      variant="panel"
      :name="name || 'The character'"
      :asset-id="draft.portraitAssetId"
      :frames="draft.portraitFrames"
      :paint-prompt="paintWords"
      @change="(assetId, frames) => emit('portrait', assetId, frames)" />

    <!-- 3 · compass -->
    <ul v-else-if="step === 3" class="side__rows ev-rise">
      <li
        v-for="row in compass"
        :key="row.key"
        class="side__row"
        :class="{ 'side__row--empty': !row.text }">
        <span class="side__icon"><component :is="COMPASS_ICONS[row.key]" :size="18" /></span>
        <span class="side__rowtext">
          <b>{{ row.label }}</b>
          <span>{{ row.text || 'Not written yet' }}</span>
        </span>
      </li>
    </ul>

    <!-- 4 · voice -->
    <div v-else-if="step === 4" class="side__voice side__in">
      <p class="side__voicehead">
        {{ sample ? situation : 'Things they would say' }}
      </p>
      <div class="side__chat" aria-live="polite">
        <template v-if="sample">
          <div
            v-for="(line, i) in sample.lines"
            :key="`${sampleRun}-${i}`"
            class="say say--unfold"
            :style="{ animationDelay: `${i * 0.38}s` }"
            :class="{ 'say--them': line.who === 'them' }">
            <span class="say__face">
              <FramedImage
                v-if="line.who === 'them' && draft.portraitAssetId && draft.portraitFrames"
                :src="src"
                :frame="draft.portraitFrames.face" />
              <IconUser v-else :size="18" />
            </span>
            <span class="say__body">
              <b>{{ line.who === 'them' ? shortName : sample.other }}</b>
              <span>{{ line.text }}</span>
            </span>
          </div>
        </template>
        <template v-else-if="lines.length">
          <div v-for="line in lines.slice(0, 4)" :key="line" class="say say--them">
            <span class="say__face">
              <FramedImage
                v-if="draft.portraitAssetId && draft.portraitFrames"
                :src="src"
                :frame="draft.portraitFrames.face" />
              <IconUser v-else :size="18" />
            </span>
            <span class="say__body">
              <b>{{ shortName }}</b>
              <span>{{ line }}</span>
            </span>
          </div>
        </template>
        <div v-if="sampling" class="say say--them say--typing" aria-hidden="true">
          <span class="say__face"><IconUser :size="18" /></span>
          <span class="say__body ev-dots"><span>●</span><span>●</span><span>●</span></span>
        </div>
        <div v-else-if="!sample && !lines.length" class="side__waiting">
          <IconFeather :size="22" />
          <b>Your sample dialogue will appear here.</b>
          <span>Add a tone and a few lines, then generate a sample to hear them in a scene.</span>
        </div>
      </div>
      <div class="side__try">
        <label class="ev-field-label" for="voice-situation">Try a situation</label>
        <div class="side__tryrow">
          <StudioSelect
            id="voice-situation"
            v-model="situation"
            :options="VOICE_SITUATIONS"
            aria-label="Situation" />
          <button type="button" class="ghost" :disabled="sampling" @click="hear">
            <IconSparkle :size="14" />
            {{ sampling ? 'Writing…' : sample ? 'Another sample' : 'Generate a sample' }}
          </button>
        </div>
        <p v-if="sampleError" class="side__error" role="alert">{{ sampleError }}</p>
        <p v-else class="side__quiet side__note">
          Written from the tone and lines you are editing; nothing is saved.
        </p>
      </div>
    </div>
  </aside>
</template>

<style scoped>
.side {
  display: flex;
  flex-direction: column;
  gap: 18px;
}
.side__head {
  display: flex;
  align-items: flex-start;
  gap: 10px;
}
.side__emblem {
  flex: none;
  margin-top: 4px;
  color: var(--gold);
}
.side__title {
  font-family: var(--font-display);
  font-size: 25px;
  font-weight: 600;
  line-height: 1.15;
  color: var(--ink);
}
.side__sub {
  font-family: var(--font-ui);
  font-size: 14.5px;
  color: var(--ink-3);
}

.side__who {
  display: flex;
  gap: 16px;
  align-items: flex-start;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--line-soft);
}
.side__pic {
  flex: none;
  width: 116px;
  height: 174px;
  border-radius: 10px;
  overflow: hidden;
  border: 1px solid var(--line);
  background: linear-gradient(180deg, #efe4c8, #e3d2aa);
  box-shadow: var(--card-shadow);
}
.side__nopic {
  display: flex;
  flex-direction: column;
  gap: 6px;
  width: 100%;
  height: 100%;
  align-items: center;
  justify-content: center;
  font-family: var(--font-ui);
  font-size: 13.5px;
  color: #8c7343;
}
.side__id {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.side__name {
  font-family: var(--font-display);
  font-size: 30px;
  font-weight: 600;
  line-height: 1.05;
  color: var(--ink);
  overflow-wrap: anywhere;
}
.side__pron {
  font-family: var(--font-ui);
  font-size: 15px;
  color: var(--muted);
}
.side__line {
  font-family: var(--font-ui);
  font-size: 15.5px;
  font-weight: 500;
  color: var(--ink-2);
}
.side__traits {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 6px;
  list-style: none;
}
.side__traits li {
  padding: 3px 10px;
  border-radius: 999px;
  background: #f3e5c8;
  border: 1px solid #e2cfa3;
  font-family: var(--font-ui);
  font-size: 13.5px;
  color: #6a5328;
}

.side__rows {
  list-style: none;
  display: grid;
  gap: 8px;
}
.side__row {
  display: flex;
  gap: 14px;
  align-items: flex-start;
  padding: 10px 14px;
  border-radius: 10px;
  background: #f6eedb;
}
.side__icon {
  flex: none;
  display: grid;
  place-items: center;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: #efe2c3;
  color: var(--gold);
}
.side__rowtext {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
  font-size: 15.5px;
  line-height: 1.45;
  color: var(--ink-2);
}
.side__rowtext b {
  font-family: var(--font-ui);
  font-size: 15px;
  font-weight: 700;
  color: var(--ink);
}
.side__row--empty .side__rowtext span {
  font-style: italic;
  color: var(--muted);
}
.side__later {
  align-self: flex-start;
  font-style: italic;
  color: var(--teal-ink);
  text-decoration: underline;
  text-underline-offset: 3px;
}

.side__voice {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.side__voicehead {
  font-family: var(--font-ui);
  font-size: 14px;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--gold);
}
.side__chat {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.say {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  max-width: 92%;
}
.say--them {
  flex-direction: row-reverse;
  align-self: flex-end;
}
.say__face {
  flex: none;
  display: grid;
  place-items: center;
  width: 40px;
  height: 40px;
  border-radius: 50%;
  overflow: hidden;
  background: #e8dcc0;
  color: var(--ink-3);
  border: 1px solid var(--line);
}
.say__body {
  display: flex;
  flex-direction: column;
  gap: 1px;
  padding: 8px 12px;
  border-radius: 10px;
  background: #f1e8d3;
  font-size: 15.5px;
  line-height: 1.4;
  color: var(--ink);
}
.say--them .say__body {
  background: rgba(20, 84, 90, 0.1);
}
.say__body b {
  font-family: var(--font-ui);
  font-size: 13px;
  font-weight: 700;
  color: var(--ink-3);
}
.say--them .say__body b {
  color: var(--teal-ink);
}
.side__try {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding-top: 14px;
  border-top: 1px solid var(--line-soft);
}
.side__tryrow {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
}
.side__tryrow > :first-child {
  flex: 1 1 260px;
  min-width: 0;
}
.side__tryrow .ghost {
  flex: none;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.side__hint {
  font-weight: 400;
  color: var(--muted);
}
.side__waiting {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 26px 20px;
  border: 1px dashed var(--line);
  border-radius: 12px;
  text-align: center;
  color: var(--ink-3);
}
.side__waiting svg {
  color: var(--gold);
}
.side__waiting b {
  font-size: 17px;
  font-weight: 500;
  color: var(--ink-2);
}
.side__waiting span {
  max-width: 34ch;
  font-family: var(--font-ui);
  font-size: 14.5px;
}
.side__quiet {
  font-size: 14.5px;
  font-style: italic;
  color: var(--muted);
}
.side__note {
  font-style: normal;
  font-family: var(--font-ui);
  font-size: 13.5px;
}
.side__error {
  font-size: 14px;
  color: #b3542e;
}

@media (max-width: 1240px) {
  .side {
    position: static;
    max-height: none;
  }
}
/* ————— motion: each step's panel arrives, lines unfold like a dialogue box ————— */
.side__headtext,
.side__in {
  animation: side-in 0.5s var(--ease-settle) both;
}
@keyframes side-in {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
}
.side__who {
  animation: side-in 0.5s var(--ease-settle) both;
}
.side__pic {
  transition: transform 0.5s var(--ease-settle);
}
.side__who:hover .side__pic {
  transform: rotate(-1.5deg) scale(1.03);
}
.side__emblem {
  animation: ev-float 5s var(--ease-sine) infinite;
}
.side__row {
  transition:
    background-color 0.2s ease,
    transform 0.3s var(--ease-settle);
}
.side__row:hover {
  transform: translateX(3px);
}
.say--unfold {
  animation: say-in 0.46s var(--ease-settle) both;
}
.say--unfold:not(.say--them) {
  transform-origin: left bottom;
}
.say--them.say--unfold {
  transform-origin: right bottom;
}
@keyframes say-in {
  from {
    opacity: 0;
    transform: translateY(10px) scale(0.94);
  }
}
.say--typing {
  animation: say-in 0.3s var(--ease-settle) both;
}
.say--typing .say__body {
  flex-direction: row;
  gap: 4px;
  font-size: 9px;
  letter-spacing: 0.1em;
  color: var(--teal-ink);
}
</style>
