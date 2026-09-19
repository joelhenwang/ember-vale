<!--
  CharacterPreviewPanel — right-hand "Character preview" column of the
  Character studio (see CharacterStudioView for the form column and footer).

  Self-contained by design: it resolves the character draft from the route
  param itself (no props), so both studio entries (/library/character/:id and
  /new-story/character/:id) render identical chrome. It owns only presentational
  preview state (selected tab, zoom lightbox, fake render timers); every field
  edit flows through the reactive draft in game/studio.ts, which is what the
  "dirty → image is one draft behind" banner watches.

  Style contract: shared studio chrome (card, tabs, .cta/.ghost, .ev-*) comes
  from src/styles/studio.css — this block must only contain rules specific to
  the preview (profile, full-body figure, gear, chat, lightbox) plus deliberate
  per-view overrides of the shared rules.
-->
<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { catalog } from '../../game/catalog'
import { resolveImage, setGeneratedImage } from '../../game/images'
import type { ImageSlot } from '../../game/model'
import {
  CHAR_TONES,
  defaultTraits,
  ensureCharDraft,
  genericBeat,
  isCharDirty,
  VOICE_SITUATIONS,
  wrenBeats
} from '../../game/studio'
import StudioSelect from '../studio/StudioSelect.vue'
import IconSparkle from '../icons/IconSparkle.vue'
import IconEmblem from '../icons/IconEmblem.vue'
import IconCheck from '../icons/IconCheck.vue'
import IconX from '../icons/IconX.vue'
import IconInfo from '../icons/IconInfo.vue'
import IconExpand from '../icons/IconExpand.vue'
import IconImage from '../icons/IconImage.vue'
import IconCoat from '../icons/IconCoat.vue'
import IconSatchel from '../icons/IconSatchel.vue'
import IconHeart from '../icons/IconHeart.vue'

const route = useRoute()
const id = computed(() => String(route.params.id ?? 'new'))
const character = computed(() => catalog.characters.find((c) => c.id === id.value))
const displayName = computed(() => character.value?.name ?? 'the new character')
const draft = computed(() => ensureCharDraft(id.value))
const dirty = computed(() => isCharDirty(id.value))

const tab = ref<'appearance' | 'voice' | 'behavior'>('appearance')
const TAB_LABELS = { appearance: 'Appearance', voice: 'Voice', behavior: 'Behavior' } as const

/* ————— appearance ————— */
const fullSlot = computed<ImageSlot | null>(() =>
  id.value === 'wren'
    ? 'character.wren.fullbody'
    : character.value
      ? character.value.imageSlot
      : null
)
const fullUrl = computed(() => (fullSlot.value ? resolveImage(fullSlot.value) : ''))
const rendering = ref(false)
const rendered = ref(id.value === 'wren')
let renderTimer: ReturnType<typeof setTimeout> | undefined
function updateFullBody(): void {
  if (rendering.value) return
  rendering.value = true
  clearTimeout(renderTimer)
  // DEMO: fake render latency; production streams the image task's result.
  renderTimer = setTimeout(() => {
    setGeneratedImage(
      'character.wren.fullbody',
      `/images/character-wren-fullbody.webp?r=${Date.now()}`
    )
    rendered.value = true
    draft.value.appearanceSaved = true
    rendering.value = false
  }, 900)
}
onBeforeUnmount(() => clearTimeout(renderTimer))

const gear = [
  { icon: IconCoat, label: 'Equipped', detail: 'Traveler coat · Leather vest' },
  { icon: IconSatchel, label: 'Carried', detail: 'Satchel · Belt pouch' },
  { icon: IconHeart, label: 'Physical state', detail: 'Lean build · Bandaged forearm' }
]

/* ————— zoom lightbox ————— */
const zoomed = ref(false)
function onKey(e: KeyboardEvent): void {
  if (e.key === 'Escape') zoomed.value = false
}
if (typeof window !== 'undefined') window.addEventListener('keydown', onKey)
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))

/* ————— voice ————— */
const situation = ref<string>(VOICE_SITUATIONS[0]!)
const variant = ref(0)
const tone = ref('Neutral')
const generating = ref(false)
const situationIdx = computed(() => Math.max(0, VOICE_SITUATIONS.indexOf(situation.value)))
watch([situation, tone], () => {
  variant.value += 1
})

const beat = computed(() =>
  id.value === 'wren'
    ? wrenBeats(situationIdx.value, variant.value)
    : genericBeat(displayName.value, variant.value)
)

function refine(t: string): void {
  tone.value = t
  variant.value += 1
}
let genTimer: ReturnType<typeof setTimeout> | undefined
function generateSample(): void {
  if (generating.value) return
  generating.value = true
  clearTimeout(genTimer)
  // DEMO: fake composition latency; production would await a voice sample task.
  genTimer = setTimeout(() => {
    variant.value += 1
    generating.value = false
  }, 800)
}
onBeforeUnmount(() => clearTimeout(genTimer))

/* ————— behavior ————— */
const traits = ref<Record<string, boolean>>(defaultTraits())
</script>

<template>
  <aside class="card ev-card preview" aria-label="Character preview">
    <header class="preview__head">
      <IconEmblem :size="24" class="preview__emblem" />
      <h2 class="preview__title">Character preview</h2>
    </header>

    <div class="preview__profile">
      <img
        v-if="fullSlot"
        class="preview__avatar"
        :src="fullUrl"
        :alt="`${displayName} portrait`" />
      <div v-else class="preview__avatar preview__avatar--empty"><IconSparkle :size="22" /></div>
      <div class="preview__who">
        <p class="preview__name">{{ character ? displayName : 'New character' }}</p>
        <p class="preview__role">{{ character?.role ?? 'Not yet defined' }}</p>
        <span class="preview__pill">
          <IconCheck :size="10" />
          {{
            tab === 'appearance'
              ? draft.appearanceSaved
                ? 'Appearance saved'
                : 'Profile ready'
              : 'Appearance saved'
          }}
        </span>
      </div>
      <button v-if="tab === 'appearance'" type="button" class="preview__change">
        Change profile
      </button>
    </div>

    <div v-if="tab === 'appearance'" class="preview__mini">
      <span class="mini"
        ><span class="mini__c">1</span> Profile <IconCheck :size="11" class="mini__ok"
      /></span>
      <span class="mini__line"></span>
      <span class="mini"
        ><span class="mini__c">2</span> Full-body
        <IconCheck v-if="rendered" :size="11" class="mini__ok" />
      </span>
    </div>

    <div class="preview__tabs" role="tablist" aria-label="Preview sections">
      <button
        v-for="t in ['appearance', 'voice', 'behavior'] as const"
        :id="`cpanel-tab-${t}`"
        :key="t"
        type="button"
        role="tab"
        :aria-selected="tab === t"
        :aria-controls="`cpanel-panel-${t}`"
        :class="{ 'preview__tabs--on': tab === t }"
        @click="tab = t">
        {{ TAB_LABELS[t] }}
      </button>
    </div>

    <!-- appearance -->
    <div
      v-show="tab === 'appearance'"
      id="cpanel-panel-appearance"
      class="preview__pane"
      role="tabpanel"
      aria-labelledby="cpanel-tab-appearance">
      <div class="fullfig">
        <button
          v-if="fullSlot"
          type="button"
          class="fullfig__imgwrap"
          @click="zoomed = true"
          aria-label="Enlarge full-body image">
          <img
            :src="fullUrl"
            :alt="`${displayName} full body`"
            :class="{ 'is-rendering': rendering }" />
        </button>
        <div v-else class="fullfig__empty">
          <IconSparkle :size="26" />
          <p>A full-body render will appear<br />once the profile is complete.</p>
        </div>
        <span v-if="fullSlot" class="fullfig__zoom"><IconExpand :size="13" /></span>
      </div>

      <ul class="gear">
        <li v-for="g in gear" :key="g.label">
          <component :is="g.icon" :size="20" class="gear__icon" />
          <div>
            <b>{{ g.label }}</b>
            <span>{{ g.detail }}</span>
          </div>
        </li>
      </ul>

      <p class="match" :class="{ 'match--stale': dirty && rendered }">
        <IconCheck :size="11" v-if="rendered && !(dirty && rendered)" />
        <IconInfo :size="13" v-else />
        {{
          rendered
            ? dirty
              ? 'Profile changed — image is one draft behind.'
              : 'Matches current appearance'
            : 'No full-body image yet'
        }}
      </p>

      <button type="button" class="cta cta--full" :disabled="rendering" @click="updateFullBody">
        <IconImage :size="16" />
        {{
          rendering
            ? 'Rendering…'
            : rendered
              ? 'Re-render full-body image'
              : 'Update full-body image'
        }}
      </button>
      <p class="ev-info preview__footnote">
        <IconInfo :size="14" />
        Uses your profile, equipped gear and physical state.
      </p>
    </div>

    <!-- voice -->
    <div
      v-show="tab === 'voice'"
      id="cpanel-panel-voice"
      class="preview__pane preview__pane--voice"
      role="tabpanel"
      aria-labelledby="cpanel-tab-voice">
      <label class="ev-field-label" for="c-situation">Situation</label>
      <StudioSelect id="c-situation" v-model="situation" :options="VOICE_SITUATIONS" />

      <div class="chat">
        <p class="chat__sys">{{ beat.system }}</p>
        <div class="chat__msg">
          <img :src="fullSlot ? fullUrl : ''" alt="" />
          <p>
            <b>{{ character ? displayName : 'Them' }}</b
            ><br />{{ beat.line }}
          </p>
        </div>
        <p class="chat__sys">{{ beat.system2 }}</p>
        <div class="chat__msg">
          <img :src="fullSlot ? fullUrl : ''" alt="" />
          <p>
            <b>{{ character ? displayName : 'Them' }}</b
            ><br />{{ beat.line2 }}
          </p>
        </div>
      </div>

      <div class="ev-divider chat__rule" aria-hidden="true"><IconSparkle :size="11" /></div>

      <span class="ev-field-label"
        >Refine the voice{{ tone !== 'Neutral' ? ` — ${tone.toLowerCase()}` : '' }}</span
      >
      <div class="tones">
        <button
          v-for="t in CHAR_TONES"
          :key="t"
          type="button"
          class="tones__b"
          :class="{ 'tones__b--on': tone === t }"
          @click="refine(t)">
          {{ t }}
        </button>
      </div>
      <p class="ev-info">
        <IconInfo :size="14" /> Refinements propose changes to your character notes.
      </p>

      <button type="button" class="cta cta--full" :disabled="generating" @click="generateSample">
        <IconImage :size="16" /> {{ generating ? 'Composing…' : 'Generate sample' }}
      </button>
      <p class="ev-info"><IconInfo :size="14" /> Preview dialogue is not story history.</p>
    </div>

    <!-- behavior -->
    <div
      v-show="tab === 'behavior'"
      id="cpanel-panel-behavior"
      class="preview__pane"
      role="tabpanel"
      aria-labelledby="cpanel-tab-behavior">
      <span class="ev-field-label">Default tendencies</span>
      <div class="traits">
        <button
          v-for="(on, name) in traits"
          :key="name"
          type="button"
          class="trait"
          :class="{ 'trait--on': on }"
          :aria-pressed="on"
          @click="traits[name] = !on">
          <span class="trait__c"><IconCheck v-if="on" :size="10" /></span>
          {{ name }}
        </button>
      </div>
      <p class="ev-info">
        <IconInfo :size="14" />
        Behavior steers the narrator’s choices; it never locks the story.
      </p>
    </div>
  </aside>

  <!-- lightbox -->
  <Teleport to="body">
    <div
      v-if="zoomed"
      class="lb"
      @click="zoomed = false"
      role="dialog"
      aria-label="Full-body preview">
      <button type="button" class="lb__x" aria-label="Close" @click.stop="zoomed = false">
        <IconX :size="14" />
      </button>
      <img :src="fullUrl" :alt="`${displayName} full body`" @click.stop />
    </div>
  </Teleport>
</template>

<style scoped>
/* profile + mini stepper -------------------------------------- */
.preview__profile {
  display: flex;
  align-items: flex-start;
  gap: 15px;
  margin-top: 16px;
}
.preview__avatar {
  width: 118px;
  height: 118px;
  flex: none;
  border-radius: 12px;
  object-fit: cover;
  object-position: 50% 14%;
  border: 1px solid #d9c8a3;
  box-shadow: 0 2px 6px rgba(96, 74, 40, 0.18);
}
.preview__avatar--empty {
  display: flex;
  align-items: center;
  justify-content: center;
  background: #f4ecd8;
  color: var(--gold-soft);
}
.preview__who {
  min-width: 0;
}
.preview__name {
  font-family: var(--font-display);
  font-size: 27px;
  font-weight: 600;
  line-height: 1.05;
  color: #26200f;
}
.preview__role {
  margin: 2px 0 8px;
  font-size: 16px;
  color: #55482f;
}
.preview__pill {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  height: 27px;
  padding: 0 11px;
  border-radius: 8px;
  background: #dfeadb;
  border: 1px solid #c3d8b6;
  color: #3f6b3a;
  font-size: 13.5px;
  font-weight: 600;
}
.preview__change {
  margin-left: auto;
  align-self: center;
  font-size: 14px;
  color: var(--teal-ink);
  text-decoration: underline;
  text-underline-offset: 3px;
  text-decoration-thickness: 1px;
}
.preview__change:hover {
  color: var(--teal);
}
.preview__mini {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 15px 2px 4px;
}
.mini {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 15px;
  font-weight: 500;
  color: #4c4130;
}
.mini__c {
  width: 26px;
  height: 26px;
  border-radius: 50%;
  border: 1.5px solid #2e7265;
  color: var(--teal-ink);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  font-weight: 600;
}
.mini__ok {
  color: #2e7265;
}
.mini__line {
  flex: 1;
  height: 1px;
  background: #d9c9a6;
}
.preview__pane--voice {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

/* appearance: figure, gear, match ----------------------------- */
.fullfig {
  position: relative;
  border-radius: 10px;
  border: 1px solid #e0d2ae;
  background: #f4efe0;
  overflow: hidden;
}
.fullfig__imgwrap {
  display: block;
  width: 100%;
  height: 560px;
}
.fullfig img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  object-position: 50% 0;
}
.fullfig img.is-rendering {
  opacity: 0.45;
  filter: blur(3px);
}
.fullfig__zoom {
  position: absolute;
  top: 10px;
  right: 10px;
  width: 30px;
  height: 30px;
  border-radius: 8px;
  background: #fdf8eadd;
  border: 1px solid #d5c6a2;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #55482f;
  pointer-events: none;
}
.fullfig__empty {
  height: 560px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 14px;
  color: var(--muted);
  text-align: center;
  font-size: 14.5px;
  line-height: 1.5;
}
.gear {
  list-style: none;
  margin-top: 14px;
  display: flex;
  flex-direction: column;
  gap: 11px;
}
.gear li {
  display: flex;
  gap: 12px;
  align-items: flex-start;
}
.gear__icon {
  color: #a5823f;
  flex: none;
  margin-top: 1px;
}
.gear b {
  display: block;
  font-size: 15.5px;
  font-weight: 600;
  color: #33291a;
}
.gear span {
  font-size: 14px;
  color: #6c5f45;
}
.match {
  display: flex;
  align-items: center;
  gap: 9px;
  margin-top: 14px;
  padding: 9px 13px;
  border-radius: 8px;
  background: #e2edda;
  border: 1px solid #c6d8b8;
  color: #4a723f;
  font-size: 14px;
  font-weight: 500;
}
.match--stale {
  background: #f6ecd4;
  border-color: #e2cf9f;
  color: #8a6a26;
}

/* voice tab --------------------------------------------------- */
.chat {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 4px;
}
.chat__sys {
  background: #eef2f0;
  border: 1px solid #e0e8e4;
  border-radius: 8px;
  padding: 9px 13px;
  font-size: 14.5px;
  line-height: 1.45;
  color: #46524b;
}
.chat__msg {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  padding: 0 2px;
}
.chat__msg img {
  width: 36px;
  height: 36px;
  flex: none;
  border-radius: 50%;
  object-fit: cover;
  object-position: 50% 18%;
  border: 1px solid #d5c6a2;
}
.chat__msg p {
  font-size: 15px;
  line-height: 1.4;
  color: var(--ink-2);
}
.chat__msg b {
  font-size: 14.5px;
  font-weight: 600;
  color: var(--teal-ink);
}
.chat__rule {
  margin: 6px 0 2px;
  color: var(--gold-soft);
}
.tones {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
}
.tones__b {
  height: 41px;
  border-radius: 9px;
  border: 1px solid #cdbb93;
  background: #fbf5e6;
  font-size: 15px;
  font-weight: 500;
  color: var(--ink-2);
  transition:
    border-color 0.14s ease,
    color 0.14s ease,
    background 0.14s ease;
}
.tones__b:hover {
  border-color: #b39c6d;
}
.tones__b--on {
  border-color: #2e7265;
  color: var(--teal-ink);
  background: #eef5ef;
  box-shadow: inset 0 0 0 1px #2e7265;
}

/* behavior tab ------------------------------------------------ */
.traits {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}
.trait {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 11px 13px;
  border-radius: 9px;
  border: 1px solid #d9c8a3;
  background: #fbf5e6;
  font-size: 14.5px;
  color: var(--ink-2);
  transition: all 0.14s ease;
  text-align: left;
}
.trait__c {
  width: 19px;
  height: 19px;
  flex: none;
  border-radius: 50%;
  border: 1.5px solid #b9a577;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: transparent;
}
.trait--on {
  border-color: #2e7265;
  background: #edf4ef;
}
.trait--on .trait__c {
  border-color: #2e7265;
  background: #2e7265;
  color: var(--cream-on-teal);
}

/* lightbox ---------------------------------------------------- */
.lb {
  position: fixed;
  inset: 0;
  z-index: 50;
  background: rgba(46, 36, 18, 0.58);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: zoom-out;
}
.lb img {
  max-height: 86vh;
  border-radius: 14px;
  border: 1px solid #d9c8a3;
  box-shadow: 0 30px 60px -20px rgba(20, 14, 4, 0.6);
  background: #f4efe0;
  cursor: auto;
}
.lb__x {
  position: absolute;
  top: 22px;
  right: 26px;
  width: 38px;
  height: 38px;
  border-radius: 50%;
  background: #fbf5e6;
  border: 1px solid #c8b691;
  color: #55482f;
  display: flex;
  align-items: center;
  justify-content: center;
}
/* Deliberate per-view overrides of the shared studio.css chrome: the mockup
   tunes these three values tighter than the world studio uses. */
.preview__tabs {
  margin-top: 10px;
}
.cta--full {
  margin-top: 12px;
}
.preview__footnote {
  margin-top: 11px;
}
</style>
