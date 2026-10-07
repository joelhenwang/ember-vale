<!--
  PortraitPicker — a character's picture on the Appearance step: paint one
  from how they look (Generate image), or import one and say where its
  portrait (2:3) and face (round on tokens) are. The picture is kept whole
  on the server; the frames travel with the character (studioFields
  packCharacter) and every card, sheet and token shows its part.
-->
<script setup lang="ts">
import { computed, ref } from 'vue'
import FramedImage from '../ui/FramedImage.vue'
import PictureFramer, { type FrameStep, type PreviewShape } from '../ui/PictureFramer.vue'
import IconImage from '../icons/IconImage.vue'
import { findFace, libraryAssetUrl, paintPortrait, uploadPortrait } from '../../api/worldsim'
import {
  defaultFace,
  faceFromBox,
  fit,
  frameFromList,
  type Frame,
  type Size
} from '../../game/framing'
import IconSparkle from '../icons/IconSparkle.vue'
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
const note = ref<string | null>(null)
const error = ref<string | null>(null)
/** The picture being framed (a new upload, or the current one to adjust). */
const framing = ref<{ assetId: string; src: string; size: Size } | null>(null)

const src = computed(() => (props.assetId ? libraryAssetUrl(props.assetId) : ''))

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
    framing.value = { assetId: props.assetId, src: src.value, size: await sizeOf(src.value) }
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
async function paint(): Promise<void> {
  if (!props.paintPrompt || painting.value) return
  painting.value = true
  busy.value = true
  error.value = null
  note.value = null
  const started = performance.now()
  try {
    const made = await paintPortrait(props.paintPrompt)
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
    note.value = `Painted in ${Math.round((performance.now() - started) / 1000)} s. Not quite them? Change the appearance and paint again.`
  } catch (err) {
    error.value = message(err, 'Could not paint them this time.')
  } finally {
    painting.value = false
    busy.value = false
  }
}

function done(frames: Record<string, Frame>): void {
  if (!framing.value) return
  emit('change', framing.value.assetId, { portrait: frames['portrait']!, face: frames['face']! })
  framing.value = null
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
      <span class="pick__card">
        <FramedImage v-if="assetId && frames" :src="src" :frame="frames.portrait" :alt="name" />
        <span v-else class="pick__empty"><IconImage :size="30" /></span>
        <span v-if="painting" class="pick__painting" aria-hidden="true"></span>
      </span>
      <span v-if="assetId && frames && variant !== 'panel'" class="pick__token">
        <FramedImage :src="src" :frame="frames.face" />
      </span>
    </div>
    <div class="pick__side">
      <p class="pick__lead">
        {{
          painting
            ? 'Painting them… this takes about fifteen seconds.'
            : assetId
              ? 'Their picture, on every card, sheet and map token.'
              : 'No picture yet. Paint one from the appearance above, or bring your own.'
        }}
      </p>
      <div class="pick__actions">
        <button
          type="button"
          class="cta pick__paint"
          :disabled="busy || !paintPrompt"
          :title="paintPrompt ? paintPrompt : 'Fill in some of the appearance first'"
          @click="paint">
          <IconSparkle :size="15" />
          {{ painting ? 'Painting…' : assetId ? 'Generate again' : 'Generate image' }}
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
/* a slow shimmer while the picture is being painted */
.pick__painting {
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
