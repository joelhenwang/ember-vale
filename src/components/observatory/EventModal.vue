<script setup lang="ts">
/**
 * Event focus dialog: about 80% of the viewport, art on the left (~70%),
 * the scene's narration and dialogue on the right. Scene illustrations do
 * not exist yet, so the art pane shows the world map with an honest
 * label. A native <dialog> keeps focus inside and closes on Escape.
 */
import { onMounted, ref, watch } from 'vue'
import type { BeatView, ChronicleEntry } from '../../../content/clients/worldsim'
import { assetUrl, getSceneNarration, type CallOptions } from '../../api/worldsim'
import { beatTimeLabel } from '../../game/observatory'
import IconX from '../icons/IconX.vue'

const props = defineProps<{
  worldId: string
  entry: ChronicleEntry
  mapAssetId: string | null
  opts: CallOptions
  nameOf: (id: string) => string
  placeOf: (id: string | null | undefined) => string | null
}>()

const emit = defineEmits<{ close: [] }>()

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

function onBackdrop(event: MouseEvent): void {
  if (event.target === dialog.value) dialog.value?.close()
}
</script>

<template>
  <dialog
    ref="dialog"
    class="em"
    aria-labelledby="em-title"
    @close="emit('close')"
    @click="onBackdrop">
    <div class="em__frame">
      <figure class="em__art">
        <img v-if="mapAssetId" :src="assetUrl(worldId, mapAssetId)" alt="" />
        <figcaption>No illustration for this scene yet · showing the world map</figcaption>
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
          <button type="button" class="em__close" aria-label="Close" @click="dialog?.close()">
            <IconX :size="18" />
          </button>
        </header>
        <div class="em__text">
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
}
.em__art img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  filter: saturate(0.85);
}
.em__art figcaption {
  position: absolute;
  left: 12px;
  bottom: 12px;
  padding: 3px 10px;
  border-radius: 999px;
  font-size: 13px;
  background: rgba(249, 242, 225, 0.9);
  color: var(--ink-3);
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
