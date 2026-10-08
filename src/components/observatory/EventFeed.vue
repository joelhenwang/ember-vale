<script setup lang="ts">
/**
 * Observatory event feed: readable events per beat, newest first.
 *
 * When new beats arrive while the reader is scrolled into older ones, the
 * list keeps their place (the scroll offset grows by the inserted height)
 * and a pill offers to jump back to the newest beat.
 */
import { nextTick, ref, watch } from 'vue'
import type { ChronicleEntry } from '../../../content/clients/worldsim'
import type { FeedBeat } from '../../game/observatory'

const props = defineProps<{
  beats: FeedBeat[]
  nameOf: (id: string) => string
  placeOf: (id: string | null | undefined) => string | null
}>()

const emit = defineEmits<{
  open: [entry: ChronicleEntry]
  focus: [characterId: string | null]
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
          v-for="(beat, i) in beats"
          :key="beat.index"
          class="ef__beat"
          :style="{ '--i': Math.min(i, 6) }">
          <h3>{{ beat.label }}</h3>
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
            </span>
            <span class="ef__text">{{ body(entry) }}</span>
          </button>
        </article>
      </TransitionGroup>
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
.ef__head h2 {
  font-family: var(--font-display);
  font-size: 22px;
  color: var(--ink);
}
.ef__new {
  margin-left: auto;
  animation: ev-breathe 2.4s var(--ease-sine) infinite;
  --ev-breathe-color: rgba(20, 84, 90, 0.4);
  font: inherit;
  font-size: 13px;
  padding: 2px 10px;
  border-radius: 999px;
  border: 1px solid var(--teal);
  background: var(--teal);
  color: var(--cream-on-teal);
  cursor: pointer;
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
.ef__beat h3 {
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
