<!--
  PortraitCard — a character's own picture in the studio: import one, say
  where its portrait (2:3) and face (square, round on tokens) are, adjust or
  remove it. The picture is kept whole on the server; the frames travel
  with the character (studioFields packCharacter) and every card, sheet and
  token shows its part.
-->
<script setup lang="ts">
import { computed, ref } from 'vue'
import FramedImage from '../ui/FramedImage.vue'
import PictureFramer, { type FrameStep, type PreviewShape } from '../ui/PictureFramer.vue'
import IconImage from '../icons/IconImage.vue'
import { findFace, libraryAssetUrl, uploadPortrait } from '../../api/worldsim'
import { defaultFace, faceFromBox, frameFromList, type Frame, type Size } from '../../game/framing'
import type { PortraitFrames } from '../../game/studio'

const props = defineProps<{
  name: string
  assetId: string | null
  frames: PortraitFrames | null
}>()
const emit = defineEmits<{ change: [assetId: string | null, frames: PortraitFrames | null] }>()

const busy = ref(false)
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
  <section class="card ev-card portrait">
    <header class="card__head">
      <h2 class="card__title"><IconImage :size="17" /> {{ name }}’s picture</h2>
    </header>
    <div class="portrait__body">
      <div v-if="assetId && frames" class="portrait__shots">
        <span class="portrait__card"><FramedImage :src="src" :frame="frames.portrait" /></span>
        <span class="portrait__token"><FramedImage :src="src" :frame="frames.face" /></span>
      </div>
      <p v-else class="portrait__empty">
        No picture of their own: one is painted for each story. Import one to use it everywhere
        instead, on cards, sheets and map tokens.
      </p>
      <div class="portrait__actions">
        <label class="ghost portrait__pick" :class="{ 'is-busy': busy }">
          <input
            type="file"
            accept="image/png,image/jpeg,image/webp"
            :disabled="busy"
            @change="onFile" />
          {{ busy ? 'Opening…' : assetId ? 'Import a different picture' : 'Import a picture' }}
        </label>
        <button v-if="assetId" type="button" class="ghost" :disabled="busy" @click="adjust">
          Adjust the frames
        </button>
        <button
          v-if="assetId"
          type="button"
          class="ghost portrait__remove"
          :disabled="busy"
          @click="emit('change', null, null)">
          Remove
        </button>
      </div>
      <p v-if="error" class="portrait__error" role="alert">{{ error }}</p>
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
  </section>
</template>

<style scoped>
.portrait__body {
  display: flex;
  flex-wrap: wrap;
  gap: 14px 22px;
  align-items: center;
}
.portrait__shots {
  display: flex;
  gap: 16px;
  align-items: flex-end;
}
.portrait__card {
  display: block;
  width: 96px;
  height: 144px;
  border-radius: 10px;
  overflow: hidden;
  border: 1px solid var(--line);
}
.portrait__token {
  display: block;
  width: 52px;
  height: 52px;
  border-radius: 50%;
  overflow: hidden;
  border: 2px solid var(--cream-on-teal);
  box-shadow: 0 1px 4px rgba(46, 39, 24, 0.3);
}
.portrait__empty {
  flex: 1 1 260px;
  font-size: 15px;
  color: var(--ink-2);
  max-width: 60ch;
}
.portrait__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}
.portrait__pick {
  position: relative;
  cursor: pointer;
}
.portrait__pick input {
  position: absolute;
  inset: 0;
  opacity: 0;
  cursor: pointer;
}
.portrait__remove {
  color: #b3542e;
}
.portrait__error {
  flex-basis: 100%;
  color: #b3542e;
  font-size: 14px;
}
</style>
