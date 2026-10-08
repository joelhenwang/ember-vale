<!--
  PictureFramer — the player says which part of a picture each layout shows.
  One step per frame (e.g. the 2:3 portrait, then the face square, kept
  inside the portrait), then a preview. Drag a frame to move it, drag a
  corner to resize it; its shape never changes. Frames are fractions of
  the picture (src/game/framing.ts).
-->
<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import FramedImage from './FramedImage.vue'
import {
  WHOLE,
  fit,
  keepInside,
  moveFrame,
  resizeFrame,
  type Corner,
  type Frame,
  type Size
} from '../../game/framing'

export interface FrameStep {
  key: string
  title: string
  hint: string
  /** Pixel shape, width / height. */
  ratio: number
  /** Kept inside this earlier step's frame. */
  within?: string
  /** Shown as a circle (the round token) as well as its square. */
  round?: boolean
  /** Where the frame starts when there is none yet. */
  start?: (frames: Record<string, Frame>, size: Size) => Frame
}

export interface PreviewShape {
  label: string
  step: string
  /** CSS size of the preview box. */
  width: number
  height: number
  round?: boolean
}

const props = defineProps<{
  title: string
  src: string
  size: Size
  steps: FrameStep[]
  previews: PreviewShape[]
  initial?: Record<string, Frame> | null
  /** Ask for a better start for a step (e.g. find the face); null keeps the default. */
  suggest?: (step: string, frames: Record<string, Frame>) => Promise<Frame | null>
}>()

const emit = defineEmits<{ done: [frames: Record<string, Frame>]; cancel: [] }>()

const frames = ref<Record<string, Frame>>({})
const at = ref(0)
const suggesting = ref(false)
const suggestNote = ref<string | null>(null)
const stage = ref<HTMLElement | null>(null)
const previewing = computed(() => at.value >= props.steps.length)
const step = computed(() => props.steps[at.value] ?? null)
const bounds = computed<Frame>(() =>
  step.value?.within ? (frames.value[step.value.within] ?? WHOLE) : WHOLE
)
const current = computed(() => (step.value ? frames.value[step.value.key] : null))
const aspect = computed(() => `${props.size.width} / ${props.size.height}`)
/** Tall pictures fit the screen's height, wide ones its width; never stretched. */
const stageWidth = computed(
  () => `min(100%, calc(62vh * ${props.size.width} / ${props.size.height}))`
)

function startFrame(s: FrameStep): Frame {
  const within = s.within ? (frames.value[s.within] ?? WHOLE) : WHOLE
  const begun = props.initial?.[s.key] ?? s.start?.(frames.value, props.size)
  return begun ? keepInside(begun, s.ratio, props.size, within) : fit(s.ratio, props.size, within)
}

async function enter(index: number): Promise<void> {
  at.value = index
  suggestNote.value = null
  const s = props.steps[index]
  if (!s) return
  // An earlier frame may have moved: this one starts or stays inside it.
  frames.value = { ...frames.value, [s.key]: startFrame(s) }
  if (!props.initial?.[s.key] && props.suggest && !frames.value[`suggested:${s.key}`]) {
    suggesting.value = true
    try {
      const found = await props.suggest(s.key, frames.value)
      if (found && at.value === index) {
        frames.value = {
          ...frames.value,
          [s.key]: keepInside(found, s.ratio, props.size, bounds.value),
          [`suggested:${s.key}`]: found
        }
        suggestNote.value = 'Placed where the face was found. Move it if it is off.'
      }
    } catch {
      suggestNote.value = 'Could not look for the face; place it by hand.'
    } finally {
      suggesting.value = false
    }
  }
}

onMounted(() => void enter(0))

/* dragging --------------------------------------------------------------- */
let drag: { mode: 'move' | Corner; x: number; y: number; frame: Frame } | null = null

function fraction(event: PointerEvent): { x: number; y: number } {
  const box = stage.value!.getBoundingClientRect()
  return { x: (event.clientX - box.left) / box.width, y: (event.clientY - box.top) / box.height }
}

function grab(event: PointerEvent, mode: 'move' | Corner): void {
  if (!current.value) return
  const p = fraction(event)
  drag = { mode, x: p.x, y: p.y, frame: current.value }
  ;(event.currentTarget as HTMLElement).setPointerCapture(event.pointerId)
}

function pull(event: PointerEvent): void {
  if (!drag || !step.value) return
  const p = fraction(event)
  const dx = p.x - drag.x
  const dy = p.y - drag.y
  const next =
    drag.mode === 'move'
      ? moveFrame(drag.frame, dx, dy, bounds.value)
      : resizeFrame(drag.frame, drag.mode, dx, step.value.ratio, props.size, bounds.value)
  frames.value = { ...frames.value, [step.value.key]: next }
}

function release(): void {
  drag = null
}

/** Arrow keys nudge the frame (Shift: further), for keyboard players. */
function nudge(event: KeyboardEvent): void {
  if (!current.value || !step.value) return
  const by = event.shiftKey ? 0.05 : 0.01
  const moves: Record<string, [number, number]> = {
    ArrowLeft: [-by, 0],
    ArrowRight: [by, 0],
    ArrowUp: [0, -by],
    ArrowDown: [0, by]
  }
  const move = moves[event.key]
  if (!move) return
  event.preventDefault()
  frames.value = {
    ...frames.value,
    [step.value.key]: moveFrame(current.value, move[0], move[1], bounds.value)
  }
}

function pct(v: number): string {
  return `${v * 100}%`
}

function finish(): void {
  const kept: Record<string, Frame> = {}
  for (const s of props.steps) kept[s.key] = frames.value[s.key]!
  emit('done', kept)
}
</script>

<template>
  <div
    class="framer"
    role="dialog"
    aria-modal="true"
    :aria-label="title"
    @keydown.esc="emit('cancel')">
    <div class="framer__card">
      <header class="framer__head">
        <h2>{{ title }}</h2>
        <ol class="framer__steps" aria-label="Steps">
          <li
            v-for="(s, i) in steps"
            :key="s.key"
            :class="{ 'is-on': i === at, 'is-done': i < at }">
            {{ i + 1 }} · {{ s.title }}
          </li>
          <li :class="{ 'is-on': previewing }">{{ steps.length + 1 }} · Check</li>
        </ol>
      </header>

      <template v-if="!previewing && step">
        <p :key="step.key" class="framer__hint framer__swap">{{ step.hint }}</p>
        <p v-if="suggesting" class="framer__note" role="status">Looking for the face…</p>
        <p v-else-if="suggestNote" class="framer__note" role="status">{{ suggestNote }}</p>
        <div
          ref="stage"
          class="framer__stage"
          :style="{ aspectRatio: aspect, width: stageWidth }"
          @pointermove="pull"
          @pointerup="release"
          @pointercancel="release">
          <img :src="src" alt="" draggable="false" />
          <div
            v-if="step.within && frames[step.within]"
            class="framer__outer"
            :style="{
              left: pct(frames[step.within]!.x),
              top: pct(frames[step.within]!.y),
              width: pct(frames[step.within]!.w),
              height: pct(frames[step.within]!.h)
            }" />
          <div
            v-if="current"
            :key="step.key"
            class="framer__frame"
            :class="{ 'framer__frame--round': step.round }"
            :style="{
              left: pct(current.x),
              top: pct(current.y),
              width: pct(current.w),
              height: pct(current.h)
            }"
            tabindex="0"
            role="slider"
            :aria-label="`${step.title}: drag or use the arrow keys to move it`"
            @pointerdown.prevent="grab($event, 'move')"
            @keydown="nudge">
            <span v-if="step.round" class="framer__circle" aria-hidden="true" />
            <span
              v-for="c in ['nw', 'ne', 'sw', 'se'] as Corner[]"
              :key="c"
              class="framer__corner"
              :class="`framer__corner--${c}`"
              aria-hidden="true"
              @pointerdown.stop.prevent="grab($event, c)" />
          </div>
        </div>
      </template>

      <template v-else>
        <p class="framer__hint framer__swap">
          This is how it will look. Go back to change a frame.
        </p>
        <div class="framer__previews ev-pop-stagger">
          <figure v-for="p in previews" :key="p.label">
            <span
              class="framer__preview"
              :class="{ 'framer__preview--round': p.round }"
              :style="{ width: `${p.width}px`, height: `${p.height}px` }">
              <FramedImage :src="src" :frame="frames[p.step]" />
            </span>
            <figcaption>{{ p.label }}</figcaption>
          </figure>
        </div>
      </template>

      <footer class="framer__foot">
        <button type="button" class="ghost" @click="emit('cancel')">Cancel</button>
        <span class="framer__spacer" />
        <button v-if="at > 0" type="button" class="ghost" @click="enter(at - 1)">Back</button>
        <button
          v-if="!previewing"
          type="button"
          class="cta cta--sm"
          :disabled="suggesting"
          @click="enter(at + 1)">
          Next
        </button>
        <button v-else type="button" class="cta cta--sm" @click="finish">Use this picture</button>
      </footer>
    </div>
  </div>
</template>

<style scoped>
.framer {
  position: fixed;
  inset: 0;
  z-index: 60;
  display: grid;
  place-items: center;
  padding: 16px;
  background: rgba(43, 36, 22, 0.55);
}
.framer__card {
  width: 100%;
  max-width: 760px;
  max-height: calc(100vh - 32px);
  overflow-y: auto;
  background: linear-gradient(180deg, var(--surface-2), var(--surface));
  border: 1px solid var(--line);
  border-radius: var(--radius-card);
  box-shadow: var(--card-shadow);
  padding: 20px 24px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.framer__head h2 {
  font-family: var(--font-display);
  font-size: 28px;
  color: var(--ink);
}
.framer__steps {
  list-style: none;
  display: flex;
  flex-wrap: wrap;
  gap: 6px 14px;
  margin-top: 4px;
  font-size: 14px;
  color: var(--muted);
}
.framer__steps .is-on {
  color: var(--teal-ink);
  font-weight: 600;
}
.framer__steps .is-done {
  color: var(--ink-2);
}
.framer__hint {
  color: var(--ink-2);
  font-size: 15px;
}
.framer__note {
  color: var(--teal-ink);
  font-size: 14px;
}
.framer__stage {
  position: relative;
  margin: 0 auto;
  user-select: none;
  touch-action: none;
  overflow: hidden;
  border-radius: 8px;
  background: var(--bg-deep);
}
.framer__stage > img {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
}
.framer__outer {
  position: absolute;
  outline: 1px solid rgba(255, 255, 255, 0.55);
  pointer-events: none;
}
.framer__frame {
  position: absolute;
  border: 2px dashed #fff;
  box-shadow: 0 0 0 9999px rgba(20, 16, 10, 0.55);
  cursor: move;
  touch-action: none;
}
.framer__frame:focus-visible {
  outline: 3px solid var(--gold-soft);
}
.framer__circle {
  position: absolute;
  inset: 0;
  border-radius: 50%;
  border: 2px dashed var(--gold-soft);
  pointer-events: none;
}
.framer__corner {
  position: absolute;
  width: 16px;
  height: 16px;
  background: #fff;
  border: 2px solid #2e2718;
  border-radius: 3px;
  touch-action: none;
}
.framer__corner--nw {
  left: -9px;
  top: -9px;
  cursor: nwse-resize;
}
.framer__corner--ne {
  right: -9px;
  top: -9px;
  cursor: nesw-resize;
}
.framer__corner--sw {
  left: -9px;
  bottom: -9px;
  cursor: nesw-resize;
}
.framer__corner--se {
  right: -9px;
  bottom: -9px;
  cursor: nwse-resize;
}
.framer__previews {
  display: flex;
  flex-wrap: wrap;
  gap: 18px;
  align-items: flex-end;
}
.framer__previews figure {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
}
.framer__previews figcaption {
  font-size: 13px;
  color: var(--muted);
}
.framer__preview {
  display: block;
  border-radius: 10px;
  overflow: hidden;
  border: 1px solid var(--line);
  background: var(--bg-deep);
}
.framer__preview--round {
  border-radius: 50%;
  border: 2px solid var(--cream-on-teal);
}
.framer__foot {
  display: flex;
  gap: 10px;
  align-items: center;
}
.framer__spacer {
  flex: 1;
}
/* ————— motion: each step's frame lands on the picture, the check pops in ————— */
.framer__swap {
  animation: framer-swap 0.4s var(--ease-settle) both;
}
@keyframes framer-swap {
  from {
    opacity: 0;
    transform: translateY(6px);
  }
}
.framer__frame {
  animation: framer-land 0.5s var(--ease-settle) both;
}
@keyframes framer-land {
  from {
    opacity: 0;
    transform: scale(1.12);
  }
}
.framer__corner {
  transition: transform 0.2s var(--ease-settle);
}
.framer__corner:hover {
  transform: scale(1.35);
}
.framer__steps li {
  transition: color 0.25s ease;
}
.framer__steps .is-on {
  animation: framer-step 0.4s var(--ease-spring);
}
@keyframes framer-step {
  from {
    transform: translateY(3px);
    opacity: 0.4;
  }
}
.framer__preview {
  transition: transform 0.35s var(--ease-settle);
}
.framer__preview:hover {
  transform: translateY(-3px) rotate(-1deg);
}
</style>
