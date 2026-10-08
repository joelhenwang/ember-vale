<!--
  CharacterPreviewPanel — the character as the form has them so far: their
  picture, name and who they are at a glance, the overview, what they wear
  and carry and how they are, and a line in their voice. Read-only; it
  follows the draft as the player types.
-->
<script setup lang="ts">
import { computed } from 'vue'
import { libraryAssetUrl } from '../../api/worldsim'
import { identityLine } from '../../game/characterForm'
import type { CharacterDraft } from '../../game/studio'
import FramedImage from '../ui/FramedImage.vue'
import IconEmblem from '../icons/IconEmblem.vue'
import IconSparkle from '../icons/IconSparkle.vue'
import IconCoat from '../icons/IconCoat.vue'
import IconSatchel from '../icons/IconSatchel.vue'
import IconHeart from '../icons/IconHeart.vue'
import IconUser from '../icons/IconUser.vue'
import IconBook from '../icons/IconBook.vue'
import IconFeather from '../icons/IconFeather.vue'
import { vTilt } from '../../composables/useEffects'

const props = defineProps<{ draft: CharacterDraft; name: string; title?: string }>()

const src = computed(() =>
  props.draft.portraitAssetId ? libraryAssetUrl(props.draft.portraitAssetId) : ''
)
const who = computed(() => identityLine(props.draft))
const looks = computed(() =>
  [
    props.draft.hair && `${props.draft.hair}${/hair/i.test(props.draft.hair) ? '' : ' hair'}`,
    props.draft.eyes && `${props.draft.eyes}${/eye/i.test(props.draft.eyes) ? '' : ' eyes'}`,
    props.draft.body,
    props.draft.marks
  ]
    .map((s) => s.trim())
    .filter(Boolean)
)
const gear = computed(() =>
  [
    { icon: IconCoat, label: 'Equipped', detail: props.draft.wears },
    { icon: IconSatchel, label: 'Carried', detail: props.draft.carries },
    { icon: IconHeart, label: 'Physical state', detail: props.draft.condition }
  ].filter((g) => g.detail.trim())
)
const line = computed(
  () =>
    props.draft.exampleLine
      .split('\n')
      .map((l) => l.trim().replace(/^["“]|["”]$/g, ''))
      .find(Boolean) ?? ''
)
/** Parts of the sheet still empty, said plainly so the sheet never looks broken. */
const missing = computed(() =>
  [
    { icon: IconUser, label: 'Appearance', empty: !looks.value.length && !who.value },
    {
      icon: IconBook,
      label: 'Background & personality',
      empty: !props.draft.history.trim() && !props.draft.traits.trim()
    },
    { icon: IconFeather, label: 'Voice', empty: !props.draft.tone.trim() && !line.value },
    { icon: IconSatchel, label: 'Gear & condition', empty: !gear.value.length }
  ].filter((m) => m.empty)
)
const traits = computed(() =>
  props.draft.traits
    .split(/[,;]/)
    .map((t) => t.trim())
    // a short word or two each; longer phrases read badly as chips
    .filter((t) => t && t.length <= 24)
    .slice(0, 6)
)
</script>

<template>
  <aside class="card ev-card preview cpv" aria-label="Character preview">
    <header class="preview__head">
      <IconEmblem :size="22" class="preview__emblem" />
      <h2 class="preview__title">{{ title ?? 'Preview' }}</h2>
    </header>

    <div class="cpv__hero">
      <span v-tilt="7" class="cpv__pic">
        <FramedImage
          v-if="draft.portraitAssetId && draft.portraitFrames"
          :src="src"
          :frame="draft.portraitFrames.portrait"
          :alt="`${name} portrait`" />
        <span v-else class="cpv__nopic"><IconSparkle :size="26" /></span>
      </span>
      <div class="cpv__who">
        <p class="cpv__name">{{ name || 'Unnamed' }}</p>
        <p v-if="draft.pronouns" class="cpv__pron">{{ draft.pronouns }}</p>
        <p v-if="who" class="cpv__line">{{ who }}</p>
        <ul v-if="traits.length" class="cpv__traits ev-pop-stagger">
          <li v-for="t in traits" :key="t">{{ t }}</li>
        </ul>
      </div>
    </div>

    <p v-if="draft.overview" class="cpv__overview">{{ draft.overview }}</p>
    <p v-else class="cpv__empty">Their overview will show here.</p>

    <ul v-if="looks.length" class="cpv__looks">
      <li v-for="l in looks" :key="l">{{ l }}</li>
    </ul>

    <ul v-if="gear.length" class="cpv__gear ev-rise">
      <li v-for="g in gear" :key="g.label">
        <component :is="g.icon" :size="18" />
        <span>
          <b>{{ g.label }}</b>
          {{ g.detail }}
        </span>
      </li>
    </ul>

    <blockquote v-if="line" class="cpv__quote">“{{ line }}”</blockquote>

    <ul v-if="missing.length" class="cpv__missing">
      <li v-for="m in missing" :key="m.label">
        <component :is="m.icon" :size="18" />
        <span>
          <b>{{ m.label }}</b>
          Nothing written yet.
        </span>
      </li>
    </ul>
  </aside>
</template>

<style scoped>
.cpv {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.cpv .preview__head {
  display: flex;
  align-items: center;
  gap: 10px;
}
.cpv .preview__emblem {
  color: var(--gold);
}
.cpv .preview__title {
  font-family: var(--font-display);
  font-size: 25px;
  font-weight: 600;
  color: #26200f;
}
.cpv__hero {
  display: flex;
  gap: 18px;
  align-items: flex-start;
}
.cpv__pic {
  position: relative;
  flex: none;
  width: 150px;
  height: 225px;
  border-radius: 12px;
  overflow: hidden;
  border: 1px solid var(--line);
  background: linear-gradient(180deg, #efe4c8, #e3d2aa);
  box-shadow: var(--card-shadow);
}
.cpv__nopic {
  display: flex;
  height: 100%;
  align-items: center;
  justify-content: center;
  color: #b49a63;
}
.cpv__who {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.cpv__name {
  font-family: var(--font-display);
  font-size: 32px;
  font-weight: 600;
  line-height: 1.05;
  color: #211b0e;
  overflow-wrap: anywhere;
}
.cpv__pron {
  font-family: var(--font-ui);
  font-size: 15px;
  color: var(--muted);
}
.cpv__line {
  font-family: var(--font-ui);
  font-size: 16px;
  font-weight: 500;
  color: var(--ink-2);
}
.cpv__traits {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 6px;
  list-style: none;
}
.cpv__traits li {
  padding: 3px 10px;
  border-radius: 999px;
  background: #f3e5c8;
  border: 1px solid #e2cfa3;
  font-family: var(--font-ui);
  font-size: 14px;
  color: #6a5328;
}
.cpv__overview {
  font-size: 16px;
  line-height: 1.6;
  color: var(--ink-2);
  white-space: pre-line;
  display: -webkit-box;
  -webkit-line-clamp: 8;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.cpv__missing {
  list-style: none;
  display: grid;
}
.cpv__missing li {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  padding: 12px 2px;
  border-top: 1px solid var(--line-soft);
  font-style: italic;
  color: var(--muted);
}
.cpv__missing svg {
  flex: none;
  margin-top: 2px;
  color: var(--gold);
}
.cpv__missing b {
  display: block;
  font-family: var(--font-ui);
  font-style: normal;
  font-weight: 600;
  color: var(--ink-2);
}
.cpv__empty {
  font-style: italic;
  color: var(--muted);
}
.cpv__looks {
  list-style: none;
  display: grid;
  gap: 4px;
  padding: 12px 14px;
  border-radius: 10px;
  background: #f6eedb;
  font-size: 15px;
  color: var(--ink-2);
}
.cpv__looks li::before {
  content: '·';
  margin-right: 8px;
  color: var(--gold);
}
.cpv__gear {
  list-style: none;
  display: grid;
  gap: 10px;
}
.cpv__gear li {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  font-size: 15px;
  color: var(--ink-2);
}
.cpv__gear svg {
  flex: none;
  margin-top: 2px;
  color: var(--gold);
}
.cpv__gear b {
  display: block;
  font-family: var(--font-ui);
  font-weight: 700;
  color: var(--ink);
}
.cpv__quote {
  padding: 12px 16px;
  border-left: 3px solid var(--ember);
  border-radius: 0 10px 10px 0;
  background: linear-gradient(90deg, #fbefdc, transparent);
  font-style: italic;
  font-size: 16.5px;
  color: var(--ink);
}
@media (max-width: 1240px) {
  .cpv {
    position: static;
    max-height: none;
  }
}
@media (max-width: 480px) {
  .cpv__pic {
    width: 110px;
    height: 165px;
  }
}
/* ————— motion: the sheet lays itself out, the portrait is a card in hand ————— */
.cpv {
  animation: cpv-in 0.55s var(--ease-settle) both;
}
@keyframes cpv-in {
  from {
    opacity: 0;
    transform: translateY(12px);
  }
}
.cpv .preview__emblem {
  animation: ev-float 5s var(--ease-sine) infinite;
}
.cpv__hero {
  animation: cpv-in 0.6s var(--ease-settle) 0.08s both;
}
</style>
