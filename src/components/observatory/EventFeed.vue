<script setup lang="ts">
/**
 * Observatory event feed: readable events per beat, newest first.
 *
 * When new beats arrive while the reader is scrolled into older ones, the
 * list keeps their place (the scroll offset grows by the inserted height)
 * and a pill offers to jump back to the newest beat.
 */
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import type { ChronicleEntry } from '../../../content/clients/worldsim'
import type { FeedBeat } from '../../game/observatory'
import IconImage from '../icons/IconImage.vue'
import IconBranch from '../icons/IconBranch.vue'
import IconRewind from '../icons/IconRewind.vue'
import { canBranch, canRewind } from '../../game/branches'

const props = defineProps<{
  beats: FeedBeat[]
  nameOf: (id: string) => string
  placeOf: (id: string | null | undefined) => string | null
  /** Scenes with a painted picture: their entries carry a small mark. */
  pictured?: ReadonlySet<string>
  /** Turns whose end state was kept: they offer "Branch from here". */
  branchable?: ReadonlySet<number>
  /** The newest finished turn: earlier kept turns offer "Go back to this turn". */
  latestTurn?: number | null
}>()

const emit = defineEmits<{
  open: [entry: ChronicleEntry]
  focus: [characterId: string | null]
  branch: [index: number]
  rewind: [index: number]
}>()

const list = ref<HTMLElement | null>(null)
const unseen = ref(0)

watch(
  () => props.beats[0]?.index,
  async (newest, previous) => {
    const el = list.value
    if (!el || previous === undefined || newest === previous) return
    const before = el.scrollHeight
    const reading = el.scrollTop > 24
    await nextTick()
    if (reading) {
      el.scrollTop += el.scrollHeight - before
      unseen.value += 1
    }
  },
  { flush: 'pre' }
)

function toNewest(): void {
  unseen.value = 0
  list.value?.scrollTo({ top: 0, behavior: 'smooth' })
}

function onScroll(): void {
  if ((list.value?.scrollTop ?? 0) <= 24) unseen.value = 0
}

/*
 * A long story draws its newest FEED_WINDOW beats; scrolling toward the end
 * draws more. The DOM stays small however long the story grows
 * (perf-frontend-001).
 */
const FEED_WINDOW = 120
const limit = ref(FEED_WINDOW)
const shown = computed(() =>
  props.beats.length > limit.value ? props.beats.slice(0, limit.value) : props.beats
)
const more = ref<HTMLElement | null>(null)
let moreWatch: IntersectionObserver | null = null
watch(more, (el) => {
  moreWatch?.disconnect()
  if (!el || typeof IntersectionObserver === 'undefined') return
  moreWatch = new IntersectionObserver(
    ([e]) => {
      if (e?.isIntersecting) limit.value += FEED_WINDOW
    },
    { root: list.value, rootMargin: '0px 0px 600px 0px' }
  )
  moreWatch.observe(el)
})
onBeforeUnmount(() => moreWatch?.disconnect())

function body(entry: ChronicleEntry): string {
  return entry.text ?? entry.title
}
</script>

<template>
  <section class="ef" aria-label="Events">
    <header class="ef__head">
      <h2>Events</h2>
      <Transition name="ev-pop">
        <button v-if="unseen" type="button" class="ef__new ev-press" @click="toNewest()">
          {{ unseen }} new beat{{ unseen === 1 ? '' : 's' }} above
        </button>
      </Transition>
    </header>
    <div ref="list" class="ef__list" @scroll.passive="onScroll">
      <p v-if="!beats.length" class="ef__empty ev-empty">
        Nothing has happened yet. Press Step or Play to let the world move.
      </p>
      <TransitionGroup name="ef" tag="div" class="ef__beats">
        <article
          v-for="(beat, i) in shown"
          :key="beat.index"
          class="ef__beat"
          :style="{ '--i': Math.min(i, 6) }">
          <h3>
            <span>{{ beat.label }}</span>
            <button
              v-if="branchable && canBranch(branchable, beat.index)"
              type="button"
              class="ef__branch ev-press"
              :title="`Start a new story from the end of ${beat.label}`"
              @click="emit('branch', beat.index)">
              <IconBranch :size="12" /> Branch from here
            </button>
            <button
              v-if="branchable && canRewind(branchable, latestTurn, beat.index)"
              type="button"
              class="ef__branch ev-press"
              :title="`Continue this story from the end of ${beat.label}`"
              @click="emit('rewind', beat.index)">
              <IconRewind :size="12" /> Go back to this turn
            </button>
          </h3>
          <p v-if="beat.quiet" class="ef__quiet">
            A quiet stretch: everyone waited or rested{{
              beat.quiet.beats > 1 ? ` (${beat.quiet.beats} beats)` : ''
            }}.
          </p>
          <button
            v-for="entry in beat.entries"
            :key="entry.event_id"
            type="button"
            class="ef__entry"
            @click="emit('open', entry)"
            @mouseenter="emit('focus', entry.participant_ids?.[0] ?? null)"
            @mouseleave="emit('focus', null)">
            <span class="ef__where">
              <template v-if="entry.participant_ids?.length">
                {{ entry.participant_ids.map((id) => nameOf(id)).join(' & ') }}
              </template>
              <template v-if="placeOf(entry.location_id)">
                · {{ placeOf(entry.location_id) }}
              </template>
              <span
                v-if="entry.scene_id && pictured?.has(entry.scene_id)"
                class="ef__pictured"
                role="img"
                aria-label="Has a picture"
                title="This scene has a picture">
                <IconImage :size="13" />
              </span>
            </span>
            <span class="ef__text">{{ body(entry) }}</span>
          </button>
        </article>
      </TransitionGroup>
      <button
        v-if="beats.length > shown.length"
        ref="more"
        type="button"
        class="ef__more"
        @click="limit += FEED_WINDOW">
        Show older beats
      </button>
    </div>
  </section>
</template>

<style scoped>
.ef {
  display: flex;
  flex-direction: column;
  min-height: 0;
  height: 100%;
  border: 1px solid var(--line);
  border-radius: var(--radius-card);
  background: var(--surface-2);
  box-shadow: var(--card-shadow);
}
.ef__head {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px 8px;
  border-bottom: 1px solid var(--line-soft);
}
.ef__more {
  display: block;
  margin: 8px auto 0;
  font-size: 14px;
  color: var(--teal-ink);
  text-decoration: underline;
  text-underline-offset: 3px;
}
.ef__head h2 {
  font-family: var(--font-display);
  font-size: 22px;
  color: var(--ink);
}
.ef__new {
  position: relative;
  margin-left: auto;
  --ev-breathe-color: rgba(20, 84, 90, 0.4);
  --ev-ring-scale: 1.2;
  font: inherit;
  font-size: 13px;
  padding: 2px 10px;
  border-radius: 999px;
  border: 1px solid var(--teal);
  background: var(--teal);
  color: var(--cream-on-teal);
  cursor: pointer;
}
.ef__new::after {
  inset: 0;
  content: '';
  position: absolute;
  pointer-events: none;
  border-radius: inherit;
  box-shadow: 0 0 0 3px var(--ev-breathe-color, var(--ember-glow));
  opacity: 0;
  animation: ev-ring 2.4s var(--ease-out) infinite;
}
.ef__list {
  overflow-y: auto;
  padding: 6px 12px 14px;
  min-height: 0;
  flex: 1;
}
.ef__empty {
  padding: 16px 4px;
  color: var(--ink-3);
}
.ef__branch {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font: 500 12px var(--font-ui);
  letter-spacing: 0;
  text-transform: none;
  color: var(--teal-ink);
  background: none;
  border: 1px solid var(--line-soft);
  border-radius: 999px;
  padding: 1px 9px;
  cursor: pointer;
  opacity: 0.8;
  transition:
    opacity 0.2s ease,
    border-color 0.2s ease;
}
.ef__branch:hover,
.ef__branch:focus-visible {
  opacity: 1;
  border-color: var(--teal-ink);
}
.ef__beat h3 {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  position: sticky;
  top: -6px;
  margin: 10px 0 4px;
  padding: 4px 4px;
  font: 600 13px var(--font-body);
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--gold);
  background: var(--surface-2);
}
.ef__quiet {
  padding: 4px 10px 8px;
  font-size: 14px;
  font-style: italic;
  color: var(--ink-3);
}
/* a new beat slides in from the top of the chronicle; the rest make room */
.ef-enter-active {
  transition:
    opacity 0.4s var(--ease-out) calc(var(--i, 0) * 0.05s),
    transform 0.55s var(--ease-settle) calc(var(--i, 0) * 0.05s);
}
.ef-enter-from {
  opacity: 0;
  transform: translateY(-14px);
}
.ef-enter-active .ef__entry {
  animation: ef-entry-in 0.5s var(--ease-settle) both;
}
.ef-enter-active .ef__entry:nth-of-type(2) {
  animation-delay: 0.06s;
}
.ef-enter-active .ef__entry:nth-of-type(n + 3) {
  animation-delay: 0.12s;
}
.ef-leave-active {
  transition: opacity 0.18s var(--ease-in);
}
.ef-leave-to {
  opacity: 0;
}
.ef-move {
  transition: transform 0.5s var(--ease-settle);
}
@keyframes ef-entry-in {
  from {
    opacity: 0;
    translate: 10px 0;
  }
}
.ef__entry {
  position: relative;
  transition:
    border-color var(--dur) ease,
    background-color var(--dur) ease,
    translate var(--dur) var(--ease-settle);
  gap: 2px;
  width: 100%;
  text-align: left;
  font: inherit;
  color: inherit;
  padding: 8px 10px;
  margin: 2px 0;
  border: 1px solid transparent;
  border-radius: 10px;
  background: none;
  cursor: pointer;
}
.ef__entry:hover,
.ef__entry:focus-visible {
  border-color: var(--line);
  background: var(--panel);
  translate: 3px 0;
}
/* an ember marker slides down beside the entry under the pointer */
.ef__entry::before {
  content: '';
  position: absolute;
  left: -1px;
  top: 10px;
  bottom: 10px;
  width: 3px;
  border-radius: 2px;
  background: var(--ember);
  scale: 1 0;
  transition: scale 0.3s var(--ease-settle);
}
.ef__entry:hover::before,
.ef__entry:focus-visible::before {
  scale: 1 1;
}
.ef__entry:active {
  scale: 0.99;
}
.ef__pictured {
  display: inline-flex;
  vertical-align: -2px;
  margin-left: 6px;
  color: var(--gold);
}
.ef__where {
  font-size: 13px;
  color: var(--teal-ink);
  font-weight: 600;
}
.ef__text {
  display: -webkit-box;
  -webkit-line-clamp: 4;
  line-clamp: 4;
  -webkit-box-orient: vertical;
  overflow: hidden;
  font-size: 15px;
  line-height: 1.45;
  color: var(--ink-2);
}
</style>
