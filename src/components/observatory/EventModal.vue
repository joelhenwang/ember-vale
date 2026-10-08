<script setup lang="ts">
/**
 * Event focus dialog: about 80% of the viewport, art on the left (~70%),
 * the scene's narration and dialogue on the right. The art pane shows the
 * scene's painted picture when it has one (opening the moment view), says
 * so while one is being painted, and otherwise shows the world map with an
 * honest label and a way to paint the scene. A native <dialog> keeps focus
 * inside and closes on Escape.
 */
import { computed, onMounted, ref, watch } from 'vue'
import type { BeatView, ChronicleEntry, SceneArtView } from '../../../content/clients/worldsim'
import { assetUrl, getSceneNarration, type CallOptions } from '../../api/worldsim'
import { beatTimeLabel } from '../../game/observatory'
import { momentTitle } from '../../game/moments'
import { moves } from '../../composables/useMotion'
import IconX from '../icons/IconX.vue'
import IconImage from '../icons/IconImage.vue'

const props = defineProps<{
  worldId: string
  entry: ChronicleEntry
  mapAssetId: string | null
  opts: CallOptions
  nameOf: (id: string) => string
  placeOf: (id: string | null | undefined) => string | null
  /** This scene's newest picture that did not fail, if any. */
  picture?: SceneArtView | null
}>()

const emit = defineEmits<{ close: []; moment: [pictureId: string]; paint: [sceneId: string] }>()

const ready = computed(() =>
  props.picture?.status === 'ready' && props.picture.asset_id ? props.picture : null
)
const painting = computed(() => !!props.picture && !ready.value)

const dialog = ref<HTMLDialogElement | null>(null)
const beats = ref<BeatView[] | null>(null)
const failed = ref(false)

async function loadBeats(): Promise<void> {
  beats.value = null
  failed.value = false
  if (!props.entry.scene_id) return
  try {
    beats.value = await getSceneNarration(props.entry.scene_id, props.opts)
  } catch {
    failed.value = true
  }
}

onMounted(() => {
  dialog.value?.showModal()
  void loadBeats()
})
watch(() => props.entry.event_id, loadBeats)

/* Closing plays the dialog out first, then really closes it. */
const closing = ref(false)
function shut(): void {
  const el = dialog.value
  if (!el || closing.value) return
  if (!moves()) {
    el.close()
    return
  }
  closing.value = true
  let timer = 0
  const done = (): void => {
    window.clearTimeout(timer)
    el.removeEventListener('animationend', ended)
    closing.value = false
    if (el.open) el.close()
  }
  // only the dialog's own exit counts, not a line of text finishing its entrance
  const ended = (event: AnimationEvent): void => {
    if (event.target === el) done()
  }
  el.addEventListener('animationend', ended)
  timer = window.setTimeout(done, 400) // never strand an open dialog
}
function onCancel(event: Event): void {
  event.preventDefault()
  shut()
}

function onBackdrop(event: MouseEvent): void {
  if (event.target === dialog.value) shut()
}
</script>

<template>
  <dialog
    ref="dialog"
    class="em"
    :class="{ 'em--closing': closing }"
    aria-labelledby="em-title"
    @close="emit('close')"
    @cancel="onCancel"
    @click="onBackdrop">
    <div class="em__frame">
      <figure class="em__art">
        <template v-if="ready && ready.asset_id">
          <img
            class="ev-drift em__picture"
            :src="assetUrl(worldId, ready.asset_id, 1280)"
            :alt="ready.caption ?? momentTitle(ready)" />
          <figcaption class="em__caption">
            <span>{{ momentTitle(ready) }}</span>
            <button type="button" class="em__act" @click="emit('moment', ready.picture_id)">
              See the moment
            </button>
          </figcaption>
        </template>
        <template v-else>
          <img
            v-if="mapAssetId"
            class="ev-drift"
            :src="assetUrl(worldId, mapAssetId, 1280)"
            alt="" />
          <figcaption class="em__caption">
            <span v-if="painting"
              >This scene is being painted<span class="ev-dots" aria-hidden="true"
                ><span>.</span><span>.</span><span>.</span></span
              ></span
            >
            <span v-else>No illustration for this scene yet · showing the world map</span>
            <button
              v-if="!painting && entry.scene_id"
              type="button"
              class="em__act"
              @click="emit('paint', entry.scene_id)">
              <IconImage :size="14" /> Paint this scene
            </button>
          </figcaption>
        </template>
      </figure>
      <div class="em__story">
        <header>
          <p class="em__when">
            {{ beatTimeLabel(entry.absolute_index) }}
            <template v-if="placeOf(entry.location_id)">
              · {{ placeOf(entry.location_id) }}</template
            >
          </p>
          <h2 id="em-title">
            {{ entry.participant_ids?.map((id) => nameOf(id)).join(' & ') || 'The world' }}
          </h2>
          <button type="button" class="em__close" aria-label="Close" @click="shut()">
            <IconX :size="18" />
          </button>
        </header>
        <div :key="beats ? beats.length : -1" class="em__text ev-rise">
          <template v-if="beats && beats.length">
            <p
              v-for="beat in beats"
              :key="beat.id"
              :class="beat.kind === 'dialogue' ? 'em__line' : 'em__narration'">
              <template v-if="beat.kind === 'dialogue' && beat.speaker_id">
                <span class="em__speaker" aria-hidden="true">❝</span>
                <strong>{{ nameOf(beat.speaker_id) }}</strong>
              </template>
              {{ beat.text }}
            </p>
          </template>
          <p v-else class="em__narration">{{ entry.text ?? entry.title }}</p>
          <p v-if="failed" class="em__note">Could not load the scene's dialogue lines.</p>
        </div>
      </div>
    </div>
  </dialog>
</template>

<style scoped>
.em {
  width: min(80vw, 1400px);
  height: min(80vh, 900px);
  max-width: none;
  max-height: none;
  margin: auto;
  padding: 0;
  border: 1px solid var(--line-strong);
  border-radius: 14px;
  background: var(--surface-2);
  color: var(--ink-2);
  box-shadow: 0 20px 60px -20px rgba(46, 39, 24, 0.55);
}
.em::backdrop {
  background: rgba(46, 39, 24, 0.45);
  backdrop-filter: blur(2px);
}
/* opening: the scene rises toward you out of a darkening room */
.em[open] {
  animation: em-in 0.5s var(--ease-settle) both;
}
.em[open]::backdrop {
  animation: ev-fade 0.32s var(--ease-out) both;
}
.em.em--closing {
  animation: em-out 0.22s var(--ease-in) both;
}
.em.em--closing::backdrop {
  animation: em-fade-out 0.22s var(--ease-in) both;
}
@keyframes em-in {
  from {
    opacity: 0;
    transform: translateY(22px) scale(0.96);
  }
}
@keyframes em-out {
  to {
    opacity: 0;
    transform: translateY(10px) scale(0.98);
  }
}
@keyframes em-fade-out {
  to {
    opacity: 0;
  }
}
.em__frame {
  display: grid;
  grid-template-columns: minmax(0, 7fr) minmax(0, 3fr);
  height: 100%;
}
.em__art {
  position: relative;
  margin: 0;
  background: var(--bg-deep);
  overflow: hidden;
  animation: ev-push-in 1.1s var(--ease-settle) both;
}
.em__art img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  filter: saturate(0.85);
}
.em__art img.em__picture {
  filter: none;
}
.em__caption {
  animation: ev-fade 0.5s var(--ease-out) 0.6s both;
  position: absolute;
  left: 12px;
  right: 12px;
  bottom: 12px;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  pointer-events: none;
}
.em__caption > span {
  padding: 3px 10px;
  border-radius: 999px;
  font-size: 13px;
  background: rgba(249, 242, 225, 0.9);
  color: var(--ink-3);
}
.em__act {
  pointer-events: auto;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border-radius: 999px;
  border: 1px solid var(--line-strong);
  background: var(--surface);
  color: var(--ink);
  font-family: var(--font-ui);
  font-size: 14px;
  cursor: pointer;
  transition:
    background-color var(--dur) ease,
    scale var(--dur-quick) var(--ease-out);
}
.em__act:hover {
  background: var(--panel);
}
.em__story {
  display: flex;
  flex-direction: column;
  min-height: 0;
  border-left: 1px solid var(--line);
}
.em__story header {
  position: relative;
  padding: 18px 48px 10px 20px;
  border-bottom: 1px solid var(--line-soft);
}
.em__when {
  font-size: 13px;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--gold);
}
.em__story h2 {
  font-family: var(--font-display);
  font-size: 24px;
  color: var(--ink);
}
.em__close {
  position: absolute;
  top: 14px;
  right: 12px;
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  border: 1px solid var(--line);
  background: var(--surface);
  color: var(--ink-2);
  cursor: pointer;
  transition:
    rotate 0.3s var(--ease-settle),
    background-color var(--dur) ease,
    scale var(--dur-quick) var(--ease-out);
}
.em__close:hover {
  rotate: 90deg;
  background: var(--panel);
}
.em__close:active {
  scale: 0.92;
}
.em__text {
  overflow-y: auto;
  padding: 14px 20px 20px;
  display: grid;
  gap: 12px;
  align-content: start;
  line-height: 1.55;
}
.em__line strong {
  color: var(--teal-ink);
  margin-right: 4px;
}
.em__speaker {
  color: var(--gold);
  margin-right: 4px;
}
.em__note {
  font-size: 13px;
  color: var(--ink-3);
}
@media (max-width: 760px) {
  .em {
    width: 94vw;
    height: 88vh;
  }
  .em__frame {
    grid-template-columns: 1fr;
    grid-template-rows: 38% 1fr;
  }
  .em__story {
    border-left: none;
    border-top: 1px solid var(--line);
  }
}
</style>
