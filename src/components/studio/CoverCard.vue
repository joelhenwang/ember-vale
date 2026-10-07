<!--
  CoverCard — a world's own picture in the studio: import one, say which
  16:7 band of it is the banner, adjust or remove it. The picture is kept
  whole on the server; the frame travels with the world (studioFields
  packWorld) and library cards, story cards and the home banner show it.
-->
<script setup lang="ts">
import { computed, ref } from 'vue'
import FramedImage from '../ui/FramedImage.vue'
import PictureFramer, { type FrameStep, type PreviewShape } from '../ui/PictureFramer.vue'
import IconImage from '../icons/IconImage.vue'
import { libraryAssetUrl, uploadCover } from '../../api/worldsim'
import type { Frame, Size } from '../../game/framing'
import type { WorldCover } from '../../game/studio'

const props = defineProps<{ name: string; cover: WorldCover | null }>()
const emit = defineEmits<{ change: [cover: WorldCover | null] }>()

const busy = ref(false)
const error = ref<string | null>(null)
/** The picture being framed (a new upload, or the current one to adjust). */
const framing = ref<{ assetId: string; src: string; size: Size } | null>(null)

const src = computed(() => (props.cover ? libraryAssetUrl(props.cover.assetId) : ''))

const steps: FrameStep[] = [
  {
    key: 'banner',
    title: 'Banner',
    hint: 'Move the dashed frame over the part of the picture that says the most about this world, and drag its corners to size it.',
    ratio: 16 / 7
  }
]
const previews: PreviewShape[] = [
  { label: 'Library card', step: 'banner', width: 240, height: 105 },
  { label: 'Story card', step: 'banner', width: 240, height: 141 },
  { label: 'Recent story', step: 'banner', width: 213, height: 86 }
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
    const kept = await uploadCover(dataUrl)
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
  if (!props.cover) return
  busy.value = true
  error.value = null
  try {
    framing.value = { assetId: props.cover.assetId, src: src.value, size: await sizeOf(src.value) }
  } catch (err) {
    error.value = message(err, 'Could not open the picture.')
  } finally {
    busy.value = false
  }
}

function done(frames: Record<string, Frame>): void {
  if (!framing.value) return
  emit('change', { assetId: framing.value.assetId, frame: frames['banner']! })
  framing.value = null
}

const initial = computed(() =>
  framing.value && props.cover && framing.value.assetId === props.cover.assetId
    ? { banner: props.cover.frame }
    : null
)
</script>

<template>
  <section class="card ev-card cover">
    <header class="card__head">
      <h2 class="card__title"><IconImage :size="17" /> {{ name }}’s picture</h2>
    </header>
    <div class="cover__body">
      <span v-if="cover" class="cover__shot"><FramedImage :src="src" :frame="cover.frame" /></span>
      <p v-else class="cover__empty">
        No picture of its own yet. Import one and it heads this world’s library card and every story
        told in it.
      </p>
      <div class="cover__actions">
        <label class="ghost cover__pick" :class="{ 'is-busy': busy }">
          <input
            type="file"
            accept="image/png,image/jpeg,image/webp"
            :disabled="busy"
            @change="onFile" />
          {{ busy ? 'Opening…' : cover ? 'Import a different picture' : 'Import a picture' }}
        </label>
        <button v-if="cover" type="button" class="ghost" :disabled="busy" @click="adjust">
          Adjust the banner
        </button>
        <button
          v-if="cover"
          type="button"
          class="ghost cover__remove"
          :disabled="busy"
          @click="emit('change', null)">
          Remove
        </button>
      </div>
      <p v-if="error" class="cover__error" role="alert">{{ error }}</p>
    </div>
    <PictureFramer
      v-if="framing"
      :title="`Frame ${name}`"
      :src="framing.src"
      :size="framing.size"
      :steps="steps"
      :previews="previews"
      :initial="initial"
      @done="done"
      @cancel="framing = null" />
  </section>
</template>

<style scoped>
.cover__body {
  display: flex;
  flex-wrap: wrap;
  gap: 14px 22px;
  align-items: center;
}
.cover__shot {
  display: block;
  width: min(100%, 320px);
  aspect-ratio: 16 / 7;
  border-radius: 10px;
  overflow: hidden;
  border: 1px solid var(--line);
}
.cover__empty {
  flex: 1 1 260px;
  font-size: 15px;
  color: var(--ink-2);
  max-width: 60ch;
}
.cover__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}
.cover__pick {
  position: relative;
  cursor: pointer;
}
.cover__pick input {
  position: absolute;
  inset: 0;
  opacity: 0;
  cursor: pointer;
}
.cover__remove {
  color: #b3542e;
}
.cover__error {
  flex-basis: 100%;
  color: #b3542e;
  font-size: 14px;
}
</style>
