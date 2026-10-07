<script setup lang="ts">
/**
 * One painted moment, read like a page of an illustrated book: the
 * picture on the left; its headline, where and when, and the scene's
 * narration on the right, with spoken lines beside the speaker's face.
 * Previous and Next walk the story's other painted moments.
 */
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { assetUrl, getSceneNarration, type CallOptions } from '../../api/worldsim'
import type { SceneArtView } from '../../../content/clients/worldsim'
import {
  momentLines,
  momentTitle,
  momentWhen,
  type MomentLine,
  type Speaker
} from '../../game/moments'
import IconX from '../icons/IconX.vue'
import IconArrowLeft from '../icons/IconArrowLeft.vue'
import IconArrowRight from '../icons/IconArrowRight.vue'
import IconSparkle from '../icons/IconSparkle.vue'

const props = defineProps<{
  worldId: string
  /** Painted moments, oldest first. */
  moments: SceneArtView[]
  /** Which one is open; null keeps the dialog closed. */
  index: number | null
  speakers: ReadonlyMap<string, Speaker>
  places: ReadonlyMap<string, string>
  opts: CallOptions
}>()
const emit = defineEmits<{ close: []; 'update:index': [index: number] }>()

const lines = ref<MomentLine[]>([])
const loading = ref(false)
const problem = ref(false)

const moment = computed(() => (props.index === null ? null : (props.moments[props.index] ?? null)))
const picture = computed(() =>
  moment.value?.asset_id ? assetUrl(props.worldId, moment.value.asset_id) : null
)
const when = computed(() =>
  moment.value
    ? momentWhen(
        moment.value,
        moment.value.location_id ? props.places.get(moment.value.location_id) : null
      )
    : ''
)

watch(
  moment,
  async (now) => {
    lines.value = []
    problem.value = false
    if (!now) return
    loading.value = true
    try {
      const beats = await getSceneNarration(now.scene_id, props.opts)
      if (moment.value?.picture_id === now.picture_id)
        lines.value = momentLines(beats, props.speakers)
    } catch {
      problem.value = true
    } finally {
      loading.value = false
    }
  },
  { immediate: true }
)

function go(step: number): void {
  if (props.index === null) return
  const next = props.index + step
  if (next >= 0 && next < props.moments.length) emit('update:index', next)
}

function onKey(event: KeyboardEvent): void {
  if (props.index === null) return
  if (event.key === 'Escape') emit('close')
  else if (event.key === 'ArrowLeft') go(-1)
  else if (event.key === 'ArrowRight') go(1)
}
watch(
  () => props.index !== null,
  (open) => {
    if (open) window.addEventListener('keydown', onKey)
    else window.removeEventListener('keydown', onKey)
  },
  { immediate: true }
)
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))
</script>

<template>
  <div
    v-if="moment"
    class="moment-dlg"
    role="dialog"
    aria-modal="true"
    :aria-label="momentTitle(moment)"
    @click.self="emit('close')">
    <article class="moment-dlg__card">
      <div class="moment-dlg__art">
        <img v-if="picture" :src="picture" :alt="moment.caption" />
      </div>
      <div class="moment-dlg__page">
        <button class="moment-dlg__close" type="button" aria-label="Close" @click="emit('close')">
          <IconX :size="20" />
        </button>
        <p class="ev-eyebrow moment-dlg__when">{{ when }}</p>
        <h2 class="moment-dlg__title">{{ momentTitle(moment) }}</h2>
        <div class="moment-dlg__rule" aria-hidden="true">
          <span></span>
          <IconSparkle :size="14" />
          <span></span>
        </div>
        <div class="moment-dlg__text">
          <p v-if="moment.title && moment.caption" class="moment-dlg__caption">
            {{ moment.caption }}
          </p>
          <p v-if="loading" class="moment-dlg__quiet">Finding the page…</p>
          <p v-else-if="problem" class="moment-dlg__quiet">This page could not be read just now.</p>
          <template v-else>
            <template v-for="(line, i) in lines" :key="i">
              <p v-if="line.kind === 'told'" class="moment-dlg__told">{{ line.text }}</p>
              <div v-else class="moment-dlg__said">
                <img
                  v-if="line.speaker.portraitUrl"
                  class="moment-dlg__face"
                  :src="line.speaker.portraitUrl"
                  alt="" />
                <span v-else class="moment-dlg__face moment-dlg__face--blank" aria-hidden="true">
                  {{ line.speaker.name.charAt(0) }}
                </span>
                <div class="moment-dlg__bubble">
                  <b>{{ line.speaker.name }}</b>
                  <span>{{ line.text }}</span>
                </div>
              </div>
            </template>
            <p v-if="!lines.length && !moment.title" class="moment-dlg__told">
              {{ moment.caption }}
            </p>
          </template>
        </div>
        <footer class="moment-dlg__foot">
          <button type="button" class="moment-dlg__step" :disabled="index === 0" @click="go(-1)">
            <IconArrowLeft :size="14" />
            Previous
          </button>
          <span class="moment-dlg__count">{{ (index ?? 0) + 1 }} of {{ moments.length }}</span>
          <button
            type="button"
            class="moment-dlg__step"
            :disabled="index === moments.length - 1"
            @click="go(1)">
            Next
            <IconArrowRight :size="14" />
          </button>
        </footer>
      </div>
    </article>
  </div>
</template>

<style scoped>
.moment-dlg {
  position: fixed;
  inset: 0;
  z-index: 60;
  display: grid;
  place-items: center;
  padding: 24px;
  background: rgba(36, 29, 16, 0.55);
}
.moment-dlg__card {
  display: grid;
  grid-template-columns: minmax(0, 1.45fr) minmax(340px, 1fr);
  width: min(1320px, 100%);
  height: min(780px, calc(100vh - 48px));
  border: 2px solid var(--gold-soft);
  border-radius: 14px;
  overflow: hidden;
  background: var(--surface-2);
  box-shadow: 0 24px 60px rgba(30, 22, 8, 0.45);
}
.moment-dlg__art {
  min-width: 0;
  background: #2b2416;
}
.moment-dlg__art img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.moment-dlg__page {
  position: relative;
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  padding: 30px 30px 0;
  border-left: 1px solid var(--line);
  background: linear-gradient(180deg, var(--surface-2), var(--surface));
}
.moment-dlg__close {
  position: absolute;
  top: 18px;
  right: 18px;
  display: inline-flex;
  padding: 6px;
  border-radius: 50%;
  color: var(--ink-3);
}
.moment-dlg__close:hover {
  color: var(--ink);
  background: var(--panel-2);
}
.moment-dlg__when {
  color: var(--teal-ink);
  padding-right: 40px;
}
.moment-dlg__title {
  margin-top: 6px;
  font-family: var(--font-display);
  font-size: 34px;
  font-weight: 600;
  line-height: 1.1;
  color: var(--ink);
  text-wrap: balance;
}
.moment-dlg__rule {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 14px 0 6px;
  color: var(--gold);
}
.moment-dlg__rule span {
  flex: 1;
  height: 1px;
  background: var(--line);
}
.moment-dlg__text {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 8px 4px 20px 0;
  font-size: 17px;
  line-height: 1.55;
  color: var(--ink-2);
}
.moment-dlg__caption {
  font-style: italic;
  color: var(--ink-3);
}
.moment-dlg__quiet {
  color: var(--muted);
}
.moment-dlg__said {
  display: grid;
  grid-template-columns: 56px minmax(0, 1fr);
  gap: 12px;
  align-items: start;
}
.moment-dlg__face {
  width: 56px;
  height: 56px;
  border-radius: 50%;
  object-fit: cover;
  border: 2px solid var(--gold-soft);
}
.moment-dlg__face--blank {
  display: grid;
  place-items: center;
  font-family: var(--font-display);
  font-size: 24px;
  color: var(--ink-3);
  background: var(--panel-2);
}
.moment-dlg__bubble {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 10px 14px;
  border-radius: 10px;
  background: rgba(20, 84, 90, 0.08);
}
.moment-dlg__bubble b {
  font-family: var(--font-ui);
  font-size: 15px;
  font-weight: 600;
  color: var(--teal-ink);
}
.moment-dlg__foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 0 18px;
  border-top: 1px solid var(--line);
  font-family: var(--font-ui);
}
.moment-dlg__step {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  border-radius: 8px;
  font-size: 15px;
  color: var(--ink-2);
}
.moment-dlg__step:hover:not(:disabled) {
  background: var(--panel-2);
  color: var(--ink);
}
.moment-dlg__step:disabled {
  opacity: 0.4;
  cursor: default;
}
.moment-dlg__count {
  font-size: 14px;
  color: var(--muted);
}

@media (max-width: 900px) {
  .moment-dlg {
    padding: 0;
  }
  .moment-dlg__card {
    grid-template-columns: minmax(0, 1fr);
    grid-template-rows: auto minmax(0, 1fr);
    height: 100%;
    border-radius: 0;
    border: 0;
  }
  .moment-dlg__art {
    aspect-ratio: 16 / 9;
  }
  .moment-dlg__page {
    border-left: 0;
    padding: 18px 16px 0;
  }
  .moment-dlg__title {
    font-size: 28px;
  }
}
</style>
