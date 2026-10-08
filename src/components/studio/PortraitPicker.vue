<!--
  PortraitPicker — a character's picture on the Appearance step: paint one
  from how they look (Generate image), or import one and say where its
  portrait (2:3) and face (round on tokens) are. The picture is kept whole
  on the server; the frames travel with the character (studioFields
  packCharacter) and every card, sheet and token shows its part.
-->
<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import FramedImage from '../ui/FramedImage.vue'
import PictureFramer, { type FrameStep, type PreviewShape } from '../ui/PictureFramer.vue'
import IconImage from '../icons/IconImage.vue'
import {
  findFace,
  libraryAssetUrl,
  paintPortrait,
  previewPortraitPrompt,
  uploadPortrait
} from '../../api/worldsim'
import type { PortraitPromptView } from '../../../content/clients/worldsim'
import {
  defaultFace,
  faceFromBox,
  fit,
  frameFromList,
  type Frame,
  type Size
} from '../../game/framing'
import IconSparkle from '../icons/IconSparkle.vue'
import { burst, vTilt } from '../../composables/useEffects'
import type { PortraitFrames } from '../../game/studio'

const props = defineProps<{
  name: string
  assetId: string | null
  frames: PortraitFrames | null
  /** Words to paint them from (how they look); empty: nothing to paint yet. */
  paintPrompt: string
  /** "panel": a tall picture with its uses below (the studio's side panel). */
  variant?: 'inline' | 'panel'
}>()
const emit = defineEmits<{ change: [assetId: string | null, frames: PortraitFrames | null] }>()

const busy = ref(false)
const painting = ref(false)
/* the portrait card: a new picture lands here with a few sparks */
const card = ref<HTMLElement | null>(null)
function landed(): void {
  window.setTimeout(() => burst(card.value, { count: 18, spread: 110 }), 120)
}
const note = ref<string | null>(null)
const error = ref<string | null>(null)
/** The picture being framed (a new upload, or the current one to adjust). */
const framing = ref<{ assetId: string; src: string; size: Size } | null>(null)

// Drawn at most ~300 px wide: a 640 px copy. The framer gets the whole picture.
const src = computed(() => (props.assetId ? libraryAssetUrl(props.assetId, 640) : ''))

const steps: FrameStep[] = [
  {
    key: 'portrait',
    title: 'Portrait',
    hint: 'Move the dashed frame over the character and drag its corners to size it. This is what character cards and sheets show.',
    ratio: 2 / 3
  },
  {
    key: 'face',
    title: 'Face',
    hint: 'Put the face inside the square. The circle is what round tokens on the map and in the story show.',
    ratio: 1,
    within: 'portrait',
    round: true,
    start: (frames, size) => defaultFace(frames['portrait']!, size)
  }
]
const previews: PreviewShape[] = [
  { label: 'Character card', step: 'portrait', width: 120, height: 180 },
  { label: 'Character sheet', step: 'face', width: 86, height: 86 },
  { label: 'Map token', step: 'face', width: 52, height: 52, round: true },
  { label: 'Story feed', step: 'face', width: 36, height: 36, round: true }
]

function message(err: unknown, fallback: string): string {
  return err instanceof Error && err.message ? err.message : fallback
}

function sizeOf(url: string): Promise<Size> {
  return new Promise((resolve, reject) => {
    const img = new Image()
    img.onload = () => resolve({ width: img.naturalWidth, height: img.naturalHeight })
    img.onerror = () => reject(new Error('Could not open that picture.'))
    img.src = url
  })
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
  busy.value = true
  error.value = null
  try {
    const dataUrl = await new Promise<string>((resolve, reject) => {
      const reader = new FileReader()
      reader.onload = () => resolve(String(reader.result))
      reader.onerror = () => reject(new Error('Could not read that file.'))
      reader.readAsDataURL(file)
    })
    const kept = await uploadPortrait(dataUrl)
    framing.value = {
      assetId: kept.asset_id,
      src: libraryAssetUrl(kept.asset_id),
      size: { width: kept.width, height: kept.height }
    }
  } catch (err) {
    error.value = message(err, 'Could not import that picture.')
  } finally {
    busy.value = false
  }
}

async function adjust(): Promise<void> {
  if (!props.assetId) return
  busy.value = true
  error.value = null
  try {
    const whole = libraryAssetUrl(props.assetId)
    framing.value = { assetId: props.assetId, src: whole, size: await sizeOf(whole) }
  } catch (err) {
    error.value = message(err, 'Could not open the picture.')
  } finally {
    busy.value = false
  }
}

/** The map reader's guess at the face, squared and kept inside the portrait. */
async function suggest(step: string, frames: Record<string, Frame>): Promise<Frame | null> {
  if (step !== 'face' || !framing.value) return null
  const found = await findFace(framing.value.assetId)
  const box = frameFromList(found.face)
  return box ? faceFromBox(box, frames['portrait']!, framing.value.size) : null
}

/**
 * Paint them from how they look, then frame the picture without asking:
 * the portrait is its centred 2:3, the face is where the map reader sees
 * it (or where faces usually are). "Adjust the frames" is always there.
 */
/* ————— the prompt itself: read it, or write your own ————— */
const showPrompt = ref(false)
const shown = ref<PortraitPromptView | null>(null)
/** The whole prompt as the player has it; sent as written once edited. */
const rawPrompt = ref('')
const promptEdited = ref(false)
const promptError = ref<string | null>(null)

async function loadPrompt(): Promise<void> {
  promptError.value = null
  if (!props.paintPrompt) {
    shown.value = null
    if (!promptEdited.value) rawPrompt.value = ''
    return
  }
  try {
    shown.value = await previewPortraitPrompt(props.paintPrompt)
    if (!promptEdited.value) rawPrompt.value = shown.value.prompt
  } catch (err) {
    promptError.value = message(err, 'Could not read the prompt.')
  }
}
function togglePrompt(): void {
  showPrompt.value = !showPrompt.value
  if (showPrompt.value) void loadPrompt()
}
function resetPrompt(): void {
  promptEdited.value = false
  rawPrompt.value = shown.value?.prompt ?? ''
}
// The appearance changed: an untouched prompt follows it.
watch(
  () => props.paintPrompt,
  () => {
    if (showPrompt.value && !promptEdited.value) void loadPrompt()
  }
)
const settingsLine = computed(() => {
  const s = shown.value
  if (!s) return ''
  const seed = s.seed != null ? `seed ${s.seed}` : 'a new seed each time'
  return [s.checkpoint, s.style && `style ${s.style}`, `ratio ${s.ratio}`, `${s.mode} mode`, seed]
    .filter(Boolean)
    .join(' · ')
})
const ownPrompt = computed(() => showPrompt.value && promptEdited.value && !!rawPrompt.value.trim())
const canPaint = computed(() => !!props.paintPrompt || ownPrompt.value)

/* ————— the clock while painting, to the tenth of a second ————— */
const elapsed = ref(0)
let ticker: ReturnType<typeof setInterval> | undefined
function startClock(): void {
  const started = performance.now()
  elapsed.value = 0
  ticker = setInterval(() => (elapsed.value = (performance.now() - started) / 1000), 100)
}
function stopClock(): void {
  if (ticker) clearInterval(ticker)
  ticker = undefined
}
onBeforeUnmount(stopClock)
const clock = computed(() => `${elapsed.value.toFixed(1)} s`)

async function paint(): Promise<void> {
  if (!canPaint.value || painting.value) return
  painting.value = true
  busy.value = true
  error.value = null
  note.value = null
  startClock()
  try {
    const made = ownPrompt.value
      ? await paintPortrait(rawPrompt.value.trim(), true)
      : await paintPortrait(props.paintPrompt)
    const size = { width: made.width, height: made.height }
    const portrait = fit(2 / 3, size)
    let face = defaultFace(portrait, size)
    try {
      const box = frameFromList((await findFace(made.asset_id)).face)
      if (box) face = faceFromBox(box, portrait, size)
    } catch {
      // keep the usual place for a face
    }
    emit('change', made.asset_id, { portrait, face })
    landed()
    note.value = `Painted in ${elapsed.value.toFixed(1)} s. Not quite them? Change the appearance or the prompt and paint again.`
  } catch (err) {
    error.value = message(err, 'Could not paint them this time.')
  } finally {
    stopClock()
    painting.value = false
    busy.value = false
  }
}

function done(frames: Record<string, Frame>): void {
  if (!framing.value) return
  emit('change', framing.value.assetId, { portrait: frames['portrait']!, face: frames['face']! })
  framing.value = null
  landed()
}

const initial = computed(() =>
  framing.value && framing.value.assetId === props.assetId && props.frames
    ? { portrait: props.frames.portrait, face: props.frames.face }
    : null
)
</script>

<template>
  <div class="pick" :class="{ 'pick--panel': variant === 'panel' }">
    <div class="pick__shots" :class="{ 'pick__shots--busy': painting }">
      <span ref="card" v-tilt="7" class="pick__card">
        <FramedImage
          v-if="assetId && frames"
          :key="assetId"
          class="pick__img"
          :src="src"
          :frame="frames.portrait"
          :alt="name" />
        <span v-else class="pick__empty"><IconImage :size="30" /></span>
        <span v-if="painting" class="pick__painting" role="status" aria-live="off">
          <span class="pick__ring" aria-hidden="true">
            <span class="ev-progress-spin"></span><span class="ev-progress-spin"></span
            ><span class="ev-progress-spin"></span>
          </span>
          <IconSparkle :size="22" class="pick__spark" />
          <span class="pick__clock">{{ clock }}</span>
          <span class="pick__label">Painting…</span>
        </span>
      </span>
      <span v-if="assetId && frames && variant !== 'panel'" class="pick__token">
        <FramedImage :src="src" :frame="frames.face" />
      </span>
    </div>
    <div class="pick__side">
      <p class="pick__lead">
        {{
          painting
            ? `Painting them… ${clock} (usually about fifteen seconds).`
            : assetId
              ? 'Their picture, on every card, sheet and map token.'
              : 'No picture yet. Paint one from the appearance above, or bring your own.'
        }}
      </p>
      <div class="pick__actions">
        <button
          type="button"
          class="cta pick__paint"
          :disabled="busy || !canPaint"
          :title="canPaint ? '' : 'Fill in some of the appearance first'"
          @click="paint">
          <IconSparkle :size="15" />
          {{
            painting
              ? `Painting… ${clock}`
              : ownPrompt
                ? 'Generate from my prompt'
                : assetId
                  ? 'Generate again'
                  : 'Generate image'
          }}
        </button>
        <label class="ghost pick__import" :class="{ 'is-busy': busy }">
          <input
            type="file"
            accept="image/png,image/jpeg,image/webp"
            :disabled="busy"
            @change="onFile" />
          <IconImage :size="15" /> Import image
        </label>
      </div>
      <div v-if="assetId" class="pick__more">
        <button type="button" class="studio__link" :disabled="busy" @click="adjust">
          Adjust the framing
        </button>
        <button
          type="button"
          class="studio__link pick__remove"
          :disabled="busy"
          @click="emit('change', null, null)">
          Remove the picture
        </button>
      </div>
      <button
        type="button"
        class="studio__link pick__prompttoggle"
        :aria-expanded="showPrompt"
        @click="togglePrompt">
        {{ showPrompt ? 'Hide the prompt' : 'See and edit the prompt' }}
      </button>
      <div v-if="showPrompt" class="pick__prompt">
        <label class="ev-field-label" for="pick-prompt">
          Prompt sent to the image service
          <span v-if="promptEdited" class="pick__mine">Your own: sent exactly as written</span>
        </label>
        <textarea
          id="pick-prompt"
          v-model="rawPrompt"
          class="ev-input"
          rows="7"
          maxlength="4000"
          :disabled="painting"
          placeholder="Fill in some of the appearance to see the prompt, or write your own."
          @input="promptEdited = true" />
        <p v-if="settingsLine" class="pick__settings">{{ settingsLine }}</p>
        <p v-if="promptError" class="pick__error" role="alert">{{ promptError }}</p>
        <button
          v-if="promptEdited"
          type="button"
          class="studio__link"
          :disabled="painting"
          @click="resetPrompt">
          Back to the prompt from the appearance
        </button>
      </div>
      <p v-if="note && !error" class="pick__note" role="status">{{ note }}</p>
      <p v-if="error" class="pick__error" role="alert">{{ error }}</p>
      <div v-if="variant === 'panel' && assetId && frames" class="pick__uses">
        <p>Where it shows</p>
        <div class="pick__use">
          <span class="pick__use-card"><FramedImage :src="src" :frame="frames.portrait" /></span>
          <span>Cards and sheets</span>
        </div>
        <div class="pick__use">
          <span class="pick__use-token"><FramedImage :src="src" :frame="frames.face" /></span>
          <span>Map and story</span>
        </div>
      </div>
    </div>
    <Transition name="ev-modal">
      <PictureFramer
        v-if="framing"
        :title="`Frame ${name}`"
        :src="framing.src"
        :size="framing.size"
        :steps="steps"
        :previews="previews"
        :initial="initial"
        :suggest="initial ? undefined : suggest"
        @done="done"
        @cancel="framing = null" />
    </Transition>
  </div>
</template>

<style scoped>
.pick {
  display: flex;
  flex-wrap: wrap;
  gap: 18px 24px;
  align-items: flex-start;
  margin-top: 18px;
  padding-top: 18px;
  border-top: 1px dashed var(--line);
}
.pick__shots {
  position: relative;
  display: flex;
  gap: 14px;
  align-items: flex-end;
}
.pick__card {
  position: relative;
  display: block;
  width: 160px;
  height: 240px;
  border-radius: 12px;
  overflow: hidden;
  border: 1px solid var(--line);
  background: linear-gradient(180deg, #efe4c8, #e6d6b0);
  box-shadow: var(--card-shadow);
}
.pick__empty {
  display: flex;
  height: 100%;
  align-items: center;
  justify-content: center;
  color: #b49a63;
}
/* while painting: the old picture blurs, a ring turns, the clock runs */
.pick__img {
  transition: filter 0.4s ease;
  /* a new portrait arrives like a camera pushing in */
  animation: ev-push-in 1s var(--ease-settle) both;
}
.pick__shots--busy .pick__img {
  filter: blur(7px) saturate(0.75) brightness(1.04);
}
.pick__shots--busy .pick__empty {
  opacity: 0.3;
}
.pick__painting {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
  color: #3d3016;
  position: absolute;
  inset: 0;
  background: linear-gradient(
    110deg,
    transparent 20%,
    rgba(255, 240, 210, 0.65) 45%,
    transparent 70%
  );
  background-size: 250% 100%;
  animation: pick-shimmer 1.4s linear infinite;
}
.pick__ring {
  position: absolute;
  top: 50%;
  left: 50%;
  width: 118px;
  height: 118px;
  margin: -59px 0 0 -59px;
}
.pick__ring span {
  position: absolute;
  inset: 0;
  border-radius: 50%;
  border: 4px solid transparent;
  border-top-color: var(--teal);
  border-right-color: rgba(20, 84, 90, 0.35);
  animation: pick-turn 1.6s linear infinite;
}
.pick__ring span:nth-child(2) {
  inset: 13px;
  border-top-color: var(--ember);
  border-right-color: rgba(194, 97, 42, 0.3);
  animation-duration: 2.3s;
  animation-direction: reverse;
}
.pick__ring span:nth-child(3) {
  inset: 26px;
  border-top-color: var(--gold);
  animation-duration: 3.1s;
}
.pick__spark {
  position: relative;
  color: var(--ember);
  animation: pick-pulse 1.4s ease-in-out infinite;
}
.pick__clock {
  position: relative;
  font-family: var(--font-ui);
  font-size: 22px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  text-shadow: 0 1px 2px rgba(255, 250, 235, 0.9);
}
.pick__label {
  position: relative;
  font-family: var(--font-ui);
  font-size: 13.5px;
  text-shadow: 0 1px 2px rgba(255, 250, 235, 0.9);
}
@keyframes pick-turn {
  to {
    transform: rotate(360deg);
  }
}
@keyframes pick-pulse {
  50% {
    transform: scale(1.25);
    opacity: 0.7;
  }
}
/* Asked for less motion: the rings still turn (they say work is under
   way), only more slowly; the pulse and the shimmer stop. */
:root[data-motion='reduced'] .pick__ring span {
  animation-duration: 4s;
}
:root[data-motion='reduced'] .pick__ring span:nth-child(2) {
  animation-duration: 5.5s;
}
:root[data-motion='reduced'] .pick__ring span:nth-child(3) {
  animation-duration: 7s;
}
:root[data-motion='reduced'] .pick__spark,
:root[data-motion='reduced'] .pick__painting {
  animation: none;
}
@media (prefers-reduced-motion: reduce) {
  :root:not([data-motion='full']) .pick__ring span {
    animation-duration: 4s;
  }
  :root:not([data-motion='full']) .pick__ring span:nth-child(2) {
    animation-duration: 5.5s;
  }
  :root:not([data-motion='full']) .pick__ring span:nth-child(3) {
    animation-duration: 7s;
  }
  :root:not([data-motion='full']) .pick__spark,
  :root:not([data-motion='full']) .pick__painting {
    animation: none;
  }
}
.pick__prompttoggle {
  align-self: center;
  font-family: var(--font-ui);
  font-size: 15px;
}
.pick__prompt {
  display: flex;
  flex-direction: column;
  gap: 6px;
  width: 100%;
  text-align: left;
}
.pick__prompt textarea {
  font-family: var(--font-ui);
  font-size: 14.5px;
  line-height: 1.45;
}
.pick__mine {
  margin-left: 8px;
  font-weight: 400;
  color: var(--ember);
}
.pick__settings {
  font-family: var(--font-ui);
  font-size: 13.5px;
  color: var(--ink-3);
}
@keyframes pick-shimmer {
  from {
    background-position: 120% 0;
  }
  to {
    background-position: -120% 0;
  }
}
.pick__token {
  display: block;
  width: 58px;
  height: 58px;
  border-radius: 50%;
  overflow: hidden;
  border: 2px solid var(--cream-on-teal);
  box-shadow: 0 2px 6px rgba(46, 39, 24, 0.35);
}
.pick__side {
  flex: 1 1 260px;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.pick__lead {
  font-size: 16px;
  color: var(--ink-2);
}
.pick__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}
.pick__paint svg {
  color: #ffd9a8;
}
.pick__import {
  position: relative;
  cursor: pointer;
}
.pick__import input {
  position: absolute;
  inset: 0;
  opacity: 0;
  cursor: pointer;
}
.pick__more {
  display: flex;
  gap: 18px;
  font-family: var(--font-ui);
  font-size: 15px;
}
.pick__remove {
  color: #b3542e;
}
.pick__note {
  font-size: 14.5px;
  color: var(--ink-3);
}
.pick__error {
  color: #b3542e;
  font-size: 14.5px;
}

/* the side panel: the picture large, its actions and uses under it */
.pick--panel {
  flex-direction: column;
  align-items: stretch;
  flex-wrap: nowrap;
  gap: 14px;
  margin-top: 0;
  padding-top: 0;
  border-top: 0;
}
.pick--panel .pick__shots {
  justify-content: center;
}
.pick--panel .pick__card {
  width: auto;
  height: clamp(240px, 42vh, 460px);
  aspect-ratio: 2 / 3;
}
.pick--panel .pick__side {
  flex: none;
  align-items: center;
  text-align: center;
}
.pick--panel .pick__actions,
.pick--panel .pick__more {
  justify-content: center;
}
.pick__uses {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: center;
  gap: 10px 22px;
  width: 100%;
  margin-top: 4px;
  padding-top: 14px;
  border-top: 1px solid var(--line-soft);
  font-family: var(--font-ui);
  font-size: 14px;
  color: var(--ink-3);
}
.pick__uses > p {
  flex-basis: 100%;
}
.pick__use {
  display: flex;
  align-items: center;
  gap: 10px;
}
.pick__use-card,
.pick__use-token {
  display: block;
  overflow: hidden;
  border: 1px solid var(--line);
  box-shadow: 0 1px 3px rgba(46, 39, 24, 0.25);
}
.pick__use-card {
  width: 44px;
  height: 66px;
  border-radius: 6px;
}
.pick__use-token {
  width: 46px;
  height: 46px;
  border-radius: 50%;
}
</style>
