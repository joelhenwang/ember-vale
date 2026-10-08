<!--
  ImageSettingsPanel — the Image generation section of Settings.

  Four cards over the Krea 2 Studio fields (service status, model and
  style, quality and speed, framing and seeds) plus a "Try it" preview
  that draws with the choices on screen, saved or not. State and requests
  live in useImageSettings; the host view owns the save bar.
-->
<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import StatusPill from '../ui/StatusPill.vue'
import ChipGroup from '../ui/ChipGroup.vue'
import ToggleSwitch from '../ui/ToggleSwitch.vue'
import StudioSelect from '../studio/StudioSelect.vue'
import StrengthSlider from './StrengthSlider.vue'
import IconImage from '../icons/IconImage.vue'
import IconRefresh from '../icons/IconRefresh.vue'
import IconSparkle from '../icons/IconSparkle.vue'
import IconInfo from '../icons/IconInfo.vue'
import IconClock from '../icons/IconClock.vue'
import { burst, flash, vRipple } from '../../composables/useEffects'
import {
  IMAGE_RATIOS,
  IMAGE_STEPS,
  MAX_SEED,
  MODE_OPTIONS,
  PREFERRED_CHECKPOINT,
  SEED_OPTIONS,
  checkpointLabel,
  type ImageMode,
  type ImageRatio,
  type SeedMode
} from '../../game/imageSettings'
import type { useImageSettings } from '../../composables/useImageSettings'

const props = defineProps<{ s: ReturnType<typeof useImageSettings> }>()
const s = props.s
const form = s.form

const STATUS = {
  checking: { tone: 'info', label: 'Checking…' },
  live: { tone: 'ok', label: 'Drawing new art' },
  off: { tone: 'warn', label: 'Paused' },
  missing: { tone: 'info', label: 'Not set up' },
  down: { tone: 'fail', label: 'Image machine unreachable' },
  loading: { tone: 'warn', label: 'Image machine warming up' }
} as const
const pill = computed(() => STATUS[s.status.value])

/* model & style ---------------------------------------------------------- */
const checkpointOptions = computed(() => {
  const ids = new Set(s.service.value?.checkpoints ?? [])
  if (form.value.checkpoint) ids.add(form.value.checkpoint)
  return [
    { value: '', label: 'Whatever the image machine has loaded' },
    ...[...ids].map((id) => ({
      value: id,
      label:
        checkpointLabel(id) +
        (id === PREFERRED_CHECKPOINT ? ' · recommended' : '') +
        (id === s.service.value?.checkpoint ? ' · loaded now' : '')
    }))
  ]
})
const checkpoint = computed({
  get: () => form.value.checkpoint ?? '',
  set: (v: string) => (form.value.checkpoint = v || null)
})

const styleOptions = computed(() => {
  const styles = s.service.value?.styles ?? []
  const known = styles.map((st) => ({ value: st.id, label: st.label || st.id }))
  if (form.value.style && !styles.some((st) => st.id === form.value.style)) {
    known.push({ value: form.value.style, label: form.value.style })
  }
  return [{ value: '', label: 'No style (the checkpoint’s own look)' }, ...known]
})
const style = computed({
  get: () => form.value.style ?? '',
  set: (v: string) => (form.value.style = v || null)
})

/* quality & speed --------------------------------------------------------- */
const mode = computed({
  get: () => form.value.mode,
  set: (v: ImageMode) => (form.value.mode = v)
})
const modeChips = MODE_OPTIONS.map(({ value, label }) => ({ value, label }))
const modeHint = computed(() => MODE_OPTIONS.find((m) => m.value === form.value.mode)?.hint ?? '')

const stepOptions = computed(() => [
  { value: '', label: `Automatic (${form.value.turbo ? 4 : 8})` },
  ...IMAGE_STEPS.map((n) => ({ value: String(n), label: `${n} steps` }))
])
const steps = computed({
  get: () => (form.value.steps === null ? '' : String(form.value.steps)),
  set: (v: string) => (form.value.steps = v ? Number(v) : null)
})

/* framing & seeds ---------------------------------------------------------- */
const ratioOptions = [
  { value: '', label: 'Style pack default' },
  ...IMAGE_RATIOS.map((r) => ({ value: r, label: ratioLabel(r) }))
]
function ratioLabel(r: ImageRatio): string {
  const shape: Record<ImageRatio, string> = {
    '1:1': 'square',
    '16:9': 'wide',
    '9:16': 'tall',
    '3:2': 'landscape',
    '2:3': 'portrait',
    '4:3': 'landscape',
    '3:4': 'portrait'
  }
  return `${r} · ${shape[r]}`
}
const portraitRatio = computed({
  get: () => form.value.portrait_ratio ?? '',
  set: (v: string) => (form.value.portrait_ratio = (v || null) as ImageRatio | null)
})
const sceneRatio = computed({
  get: () => form.value.scene_ratio ?? '',
  set: (v: string) => (form.value.scene_ratio = (v || null) as ImageRatio | null)
})
const placeRatio = computed({
  get: () => form.value.place_ratio ?? '',
  set: (v: string) => (form.value.place_ratio = (v || null) as ImageRatio | null)
})
const seedMode = computed({
  get: () => form.value.seed_mode,
  set: (v: SeedMode) => (form.value.seed_mode = v)
})
const seedChips = SEED_OPTIONS.map(({ value, label }) => ({ value, label }))
const seedHint = computed(() => SEED_OPTIONS.find((o) => o.value === form.value.seed_mode)?.hint)
const seedText = computed({
  get: () => String(form.value.seed),
  set: (v: string) => (form.value.seed = v.trim() === '' ? Number.NaN : Number(v))
})
const seedInput = ref<HTMLElement | null>(null)
function rollSeed(): void {
  form.value.seed = Math.floor(Math.random() * MAX_SEED)
  flash(seedInput.value)
}

/* try it -------------------------------------------------------------------- */
const previewRatioOptions = IMAGE_RATIOS.map((r) => ({ value: r, label: ratioLabel(r) }))
const previewRatio = computed({
  get: () => s.previewRatio.value as string,
  set: (v: string) => (s.previewRatio.value = v as ImageRatio)
})
const countChips = ['1', '2', '3', '4'].map((n) => ({ value: n, label: n }))
const previewCount = computed({
  get: () => String(s.previewCount.value),
  set: (v: string) => (s.previewCount.value = Number(v))
})
const expected = computed(
  () => s.seconds.value * s.previewCount.value + (s.switching.value ? 35 : 0)
)

// A ticking clock while the image machine works, so a long wait reads as progress.
const elapsed = ref(0)
let timer: ReturnType<typeof setInterval> | undefined
watch(
  () => s.previewing.value,
  (running) => {
    clearInterval(timer)
    if (running) {
      elapsed.value = 0
      timer = setInterval(() => (elapsed.value += 1), 1000)
    }
  }
)
onBeforeUnmount(() => clearInterval(timer))
// new previews arrive with a small flourish from the Paint button
const goBtn = ref<HTMLElement | null>(null)
watch(
  () => s.previews.value.length,
  (now, before) => {
    if (now > 0 && now !== before) burst(goBtn.value, { count: 12, spread: 60 })
  }
)
const progress = computed(() => Math.min(0.95, elapsed.value / Math.max(1, expected.value)))
</script>

<template>
  <div class="imgset">
    <p v-if="s.error.value" class="imgset__alert" role="alert">{{ s.error.value }}</p>

    <!-- service ------------------------------------------------------------- -->
    <section class="card ev-card">
      <header class="card__head">
        <span class="card__icon"><IconImage :size="21" /></span>
        <h3 class="card__title">Image machine</h3>
        <StatusPill :tone="pill.tone" :label="pill.label" />
        <button
          type="button"
          class="iconbtn"
          :disabled="s.checking.value"
          title="Check again"
          aria-label="Check the image machine again"
          @click="s.refreshService()">
          <IconRefresh
            :size="16"
            :class="{ spin: s.checking.value, 'ev-progress-spin': s.checking.value }" />
        </button>
      </header>
      <p class="card__caption">
        Portraits for new characters and art for newly found places are painted by a Krea 2 machine
        on your network, in the background while you play. Built-in characters and places keep their
        hand-made art.
      </p>

      <div v-if="s.service.value && !s.service.value.configured" class="callout">
        <IconInfo :size="16" />
        <p>
          The server has no image machine set. Add
          <code>WORLDSIM_IMAGES__PROVIDER=krea</code> and
          <code>WORLDSIM_IMAGES__KREA_BASE_URL=http://…:7860</code> to the <code>.env</code> file
          and restart the server. You can still choose settings here.
        </p>
      </div>
      <div v-else-if="s.service.value && !s.service.value.reachable" class="callout callout--warn">
        <IconInfo :size="16" />
        <p>
          The image machine isn’t answering ({{ s.service.value.error ?? 'no reply' }}). Is it
          switched on and connected (Tailscale)? New art waits in the queue until it’s back.
        </p>
      </div>
      <dl v-else-if="s.service.value" class="facts">
        <div>
          <dt>Loaded model</dt>
          <dd>
            {{ s.service.value.checkpoint ? checkpointLabel(s.service.value.checkpoint) : '—' }}
          </dd>
        </div>
        <div>
          <dt>Waiting in its queue</dt>
          <dd>{{ s.service.value.queued }} image{{ s.service.value.queued === 1 ? '' : 's' }}</dd>
        </div>
        <div>
          <dt>Styles available</dt>
          <dd>{{ s.service.value.styles.length }}</dd>
        </div>
      </dl>

      <ToggleSwitch
        v-model="form.enabled"
        label="Paint new art while I play"
        hint="Off pauses painting: new portraits and places wait in a queue and are painted once you turn it back on." />
      <ToggleSwitch
        v-model="form.scene_moments"
        :disabled="!form.enabled"
        label="Paint key moments in the story"
        hint="Arriving somewhere new, meeting someone for the first time, settling a rumour: a picture appears under that scene, with everyone's own face. At most one every few turns. Any scene can still be painted by hand." />
    </section>

    <!-- model & style -------------------------------------------------------- -->
    <section class="card ev-card">
      <header class="card__head">
        <h3 class="card__title">Model and style</h3>
      </header>
      <div class="grid">
        <label class="field">
          <span class="field__label">Checkpoint</span>
          <StudioSelect v-model="checkpoint" :options="checkpointOptions" aria-label="Checkpoint" />
          <span class="field__hint">The base model that draws everything.</span>
        </label>
        <div v-if="s.switching.value" class="callout callout--warn field--wide">
          <IconInfo :size="16" />
          <p>
            The image machine has
            <strong>{{ checkpointLabel(s.service.value?.checkpoint ?? '') }}</strong> loaded. The
            next image will switch it to
            <strong>{{ checkpointLabel(form.checkpoint ?? '') }}</strong
            >, which takes about 35 seconds once, and changes it for everyone else using that
            machine too.
          </p>
        </div>
        <label class="field">
          <span class="field__label">Style</span>
          <StudioSelect v-model="style" :options="styleOptions" aria-label="Style" />
          <span class="field__hint">An art-style add-on (LoRA). Pixel-art packs skip it.</span>
        </label>
        <div class="field">
          <span class="field__label">Style strength</span>
          <StrengthSlider
            v-model="form.style_scale"
            label="Style strength"
            :disabled="!form.style" />
          <span class="field__hint">Around 2, faces and hands start to break.</span>
          <span v-if="s.errors.value.style_scale" class="field__err">{{
            s.errors.value.style_scale
          }}</span>
        </div>
      </div>
    </section>

    <!-- quality & speed ------------------------------------------------------- -->
    <section class="card ev-card">
      <header class="card__head">
        <h3 class="card__title">Quality and speed</h3>
        <span class="estimate" :title="'On an idle machine; a busy queue adds the images ahead'">
          <IconClock :size="15" /> about {{ s.seconds.value }} s per image
        </span>
      </header>
      <div class="grid">
        <div class="field field--wide">
          <span class="field__label">Mode</span>
          <ChipGroup v-model="mode" :options="modeChips" />
          <span class="field__hint">{{ modeHint }}</span>
        </div>

        <div class="field">
          <ToggleSwitch
            v-model="form.turbo"
            label="Turbo (4-step LoRA)"
            hint="About twice as fast. Off: more steps, finer detail, ~24 s an image." />
        </div>
        <label class="field">
          <span class="field__label">Steps</span>
          <StudioSelect v-model="steps" :options="stepOptions" aria-label="Steps" />
          <span class="field__hint">More steps, more time. Automatic suits most uses.</span>
          <span v-if="s.errors.value.steps" class="field__err">{{ s.errors.value.steps }}</span>
        </label>

        <div class="field">
          <ToggleSwitch
            v-model="form.detail"
            label="Detail LoRA (snofs)"
            hint="Sharper textures and small details. Free at strength 1.00." />
        </div>
        <div class="field">
          <span class="field__label">Detail strength</span>
          <StrengthSlider
            v-model="form.detail_scale"
            label="Detail strength"
            :disabled="!form.detail" />
          <span class="field__hint">Any strength other than 1.00 adds about 4 s.</span>
          <span v-if="s.errors.value.detail_scale" class="field__err">
            {{ s.errors.value.detail_scale }}
          </span>
        </div>
      </div>
    </section>

    <!-- framing & seeds ------------------------------------------------------- -->
    <section class="card ev-card">
      <header class="card__head">
        <h3 class="card__title">Framing and seeds</h3>
      </header>
      <div class="grid">
        <label class="field">
          <span class="field__label">Portrait shape</span>
          <StudioSelect
            v-model="portraitRatio"
            :options="ratioOptions"
            aria-label="Portrait shape" />
          <span class="field__hint">Character portraits. The style pack draws them square.</span>
        </label>
        <label class="field">
          <span class="field__label">Place shape</span>
          <StudioSelect v-model="placeRatio" :options="ratioOptions" aria-label="Place shape" />
          <span class="field__hint">Scenery for places. The style pack draws them wide.</span>
        </label>
        <label class="field">
          <span class="field__label">Story picture shape</span>
          <StudioSelect
            v-model="sceneRatio"
            :options="ratioOptions"
            aria-label="Story picture shape" />
          <span class="field__hint"
            >Painted moments in the story. The style pack draws them wide.</span
          >
        </label>
        <div class="field">
          <span class="field__label">Seed</span>
          <ChipGroup v-model="seedMode" :options="seedChips" />
          <span class="field__hint">{{ seedHint }}</span>
        </div>
        <div v-if="form.seed_mode === 'fixed'" class="field">
          <span class="field__label">Seed number</span>
          <span class="seedrow">
            <input
              ref="seedInput"
              v-model="seedText"
              class="ev-input"
              inputmode="numeric"
              aria-label="Seed number" />
            <button type="button" class="ghost seedrow__roll" @click="rollSeed">Roll</button>
          </span>
          <span v-if="s.errors.value.seed" class="field__err">{{ s.errors.value.seed }}</span>
        </div>
      </div>
      <button type="button" class="linkbtn" @click="s.restoreDefaults()">
        Restore recommended settings
      </button>
    </section>

    <!-- try it ---------------------------------------------------------------- -->
    <section class="card card--try ev-card">
      <header class="card__head">
        <span class="card__icon"><IconSparkle :size="20" /></span>
        <h3 class="card__title">Try it</h3>
      </header>
      <p class="card__caption">
        Draws with the settings above, even before you save them. Nothing is kept.
      </p>
      <label class="field field--wide">
        <span class="field__label">Describe a picture</span>
        <textarea
          v-model="s.previewPrompt.value"
          class="ev-input prompt"
          rows="2"
          maxlength="2000"
          aria-label="Picture description"></textarea>
      </label>
      <div class="tryrow">
        <label class="field">
          <span class="field__label">Shape</span>
          <StudioSelect v-model="previewRatio" :options="previewRatioOptions" aria-label="Shape" />
        </label>
        <div class="field">
          <span class="field__label">How many</span>
          <ChipGroup v-model="previewCount" :options="countChips" />
        </div>
        <button
          ref="goBtn"
          v-ripple
          type="button"
          class="cta tryrow__go"
          :disabled="!s.canPreview.value"
          @click="s.preview()">
          <IconSparkle :size="16" />
          {{ s.previewing.value ? 'Painting…' : 'Paint' }}
        </button>
      </div>
      <p class="field__hint">
        About {{ expected }} s on an idle machine{{
          s.switching.value ? ', including the model switch' : ''
        }}.
      </p>

      <Transition name="ev-rise">
        <div v-if="s.previewing.value" class="painting" role="status">
          <div class="painting__bar"><span :style="{ width: `${progress * 100}%` }"></span></div>
          <span>Painting… {{ elapsed }} s</span>
        </div>
      </Transition>
      <p v-if="s.previewError.value" class="imgset__alert" role="alert">
        {{ s.previewError.value }}
      </p>

      <div v-if="s.previews.value.length" class="results">
        <figure
          v-for="(img, i) in s.previews.value"
          :key="img.data_url.slice(-24) + i"
          class="result"
          :style="{ animationDelay: `${i * 0.08}s` }">
          <img :src="img.data_url" :alt="`Preview ${i + 1}`" />
          <figcaption>
            seed {{ img.seed ?? '—' }} · {{ img.width }}×{{ img.height }}
            <template v-if="img.seconds"> · {{ img.seconds.toFixed(1) }} s</template>
          </figcaption>
        </figure>
      </div>
    </section>
  </div>
</template>

<style scoped>
.imgset {
  display: flex;
  flex-direction: column;
  gap: 16px;
  margin-top: 16px;
}
.card {
  padding: 18px 22px 22px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.card__head {
  display: flex;
  align-items: center;
  gap: 13px;
  flex-wrap: wrap;
}
.card__icon {
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
  font-size: 22px;
  font-weight: 600;
  color: var(--ink);
  margin-right: auto;
}
.card__caption {
  font-size: 15px;
  line-height: 1.5;
  color: var(--ink-2);
  max-width: 70ch;
}

.grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 18px 26px;
}
.field {
  display: flex;
  flex-direction: column;
  gap: 7px;
  min-width: 0;
}
.field--wide {
  grid-column: 1 / -1;
}
.field__label {
  font-size: 15.5px;
  font-weight: 600;
  color: var(--ink-2);
}
.field__hint {
  font-size: 13.5px;
  color: var(--muted);
  line-height: 1.4;
}
.field__err {
  font-size: 13px;
  color: #b3542e;
}

.facts {
  display: flex;
  flex-wrap: wrap;
  gap: 10px 34px;
}
.facts dt {
  font-size: 13px;
  color: var(--muted);
}
.facts dd {
  font-size: 15.5px;
  font-weight: 600;
  color: var(--ink);
}

.callout {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  padding: 11px 14px;
  border-radius: 10px;
  border: 1px solid #b9cfd1;
  background: #eef5f3;
  color: var(--ink-2);
  font-size: 14.5px;
  line-height: 1.5;
}
.callout--warn {
  border-color: #dcc189;
  background: #fbf1da;
}
.callout svg {
  flex: none;
  margin-top: 3px;
}
.callout code {
  font-size: 13px;
  background: rgba(46, 39, 24, 0.07);
  padding: 1px 5px;
  border-radius: 5px;
}

.estimate {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 5px 12px;
  border-radius: 999px;
  background: #f1ead6;
  color: var(--ink-2);
  font-size: 14px;
  font-weight: 500;
}

.iconbtn {
  width: 34px;
  height: 34px;
  border-radius: 9px;
  border: 1px solid var(--line);
  background: #fbf6e9;
  color: var(--teal-ink);
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
.iconbtn:disabled {
  opacity: 0.6;
}
.spin {
  animation: spin 0.9s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.seedrow {
  display: flex;
  gap: 8px;
}
.seedrow .ev-input {
  flex: 1;
  min-width: 0;
}
.seedrow__roll {
  flex: none;
}
.linkbtn {
  align-self: flex-start;
  font-size: 14px;
  color: var(--teal-ink);
  text-decoration: underline;
  text-underline-offset: 3px;
}

.prompt {
  min-height: 64px;
  height: auto;
  padding: 10px 12px;
  resize: vertical;
  line-height: 1.45;
}
.tryrow {
  display: flex;
  align-items: flex-end;
  gap: 22px;
  flex-wrap: wrap;
}
.tryrow .field:first-child {
  min-width: 190px;
}
.tryrow__go {
  height: 44px;
  padding: 0 26px;
  font-size: 16px;
  margin-left: auto;
}
.painting {
  display: flex;
  align-items: center;
  gap: 14px;
  font-size: 14px;
  color: var(--ink-2);
}
.painting__bar {
  flex: 1;
  height: 8px;
  border-radius: 999px;
  background: #e8dec6;
  overflow: hidden;
}
.painting__bar span {
  position: relative;
  display: block;
  height: 100%;
  overflow: hidden;
  background: linear-gradient(90deg, #256e67, #3f9184);
  transition: width 1s linear;
}
/* light runs along the bar while the machine works */
.painting__bar span::after {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(90deg, transparent, rgba(255, 244, 214, 0.45), transparent);
  transform: translateX(-100%);
  animation: painting-run 1.4s var(--ease-io) infinite;
}
@keyframes painting-run {
  to {
    transform: translateX(100%);
  }
}
/* a finished picture develops: sharpening out of a warm blur */
.result {
  animation: result-develop 0.9s var(--ease-settle) both;
}
@keyframes result-develop {
  from {
    opacity: 0;
    transform: scale(0.96);
    filter: blur(8px) sepia(0.5);
  }
}
.results {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 14px;
}
.result {
  margin: 0;
  border: 1px solid var(--line);
  border-radius: 12px;
  overflow: hidden;
  background: #fbf6e9;
}
.result img {
  display: block;
  width: 100%;
  height: auto;
}
.result figcaption {
  padding: 7px 10px;
  font-size: 13px;
  color: var(--muted);
  font-variant-numeric: tabular-nums;
}
.imgset__alert {
  padding: 10px 14px;
  border: 1px solid #d6a58c;
  border-radius: 10px;
  background: #fbede5;
  color: #8a3b1c;
  font-size: 14.5px;
}

@media (max-width: 760px) {
  .grid {
    grid-template-columns: 1fr;
  }
}
</style>
