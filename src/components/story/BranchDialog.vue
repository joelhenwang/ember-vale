<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { branchStory, rewindStory } from '../../api/worldsim'
import type { StoryRewindResponse } from '../../../content/clients/worldsim'
import { ApiError } from '../../api/http'
import { beatTimeLabel } from '../../game/observatory'
import { branchTitle, newBranchKey, pathNotTakenTitle } from '../../game/branches'
import { storyLocation } from '../../game/storyRoute'

/**
 * "Branch from here" (a new story that continues from the end of one turn)
 * and "Go back to this turn" (this story continues from there; the later
 * turns are kept as a story of their own). Says plainly what happens first.
 * The key is made once per opening, so a retry after a dropped answer gets
 * the same answer rather than a second story or a second rewind.
 */
const props = withDefaults(
  defineProps<{
    open: boolean
    storyId: string
    storyTitle: string
    turn: number | null
    mode?: 'branch' | 'rewind'
    /** The story's newest turn (rewind: what is removed, and the saved story's name). */
    latest?: number | null
  }>(),
  { mode: 'branch', latest: null }
)
const emit = defineEmits<{ close: []; rewound: [made: StoryRewindResponse] }>()

const router = useRouter()
const busy = ref(false)
const error = ref<string | null>(null)
/** After going back: where the later turns went. */
const done = ref<StoryRewindResponse | null>(null)
let key = newBranchKey()

watch(
  () => [props.open, props.turn, props.mode] as const,
  ([open]) => {
    if (open) {
      key = newBranchKey()
      error.value = null
      busy.value = false
      done.value = null
    }
  }
)

const rewinding = computed(() => props.mode === 'rewind')
const when = computed(() => (props.turn === null ? '' : beatTimeLabel(props.turn)))
const title = computed(() => (props.turn === null ? '' : branchTitle(props.storyTitle, props.turn)))
const later = computed(() =>
  props.turn === null || props.latest === null ? 0 : Math.max(0, props.latest - props.turn)
)
const laterWords = computed(() =>
  later.value === 1 ? 'The 1 later turn is' : `The ${later.value} later turns are`
)
const savedTitle = computed(() =>
  props.latest === null ? '' : pathNotTakenTitle(props.storyTitle, props.latest)
)

async function start(): Promise<void> {
  if (props.turn === null || busy.value) return
  busy.value = true
  error.value = null
  try {
    if (rewinding.value) {
      const made = await rewindStory(props.storyId, props.turn, key)
      done.value = made
      emit('rewound', made)
    } else {
      const made = await branchStory(props.storyId, props.turn, key)
      emit('close')
      await router.push(storyLocation(made.story_id, made.role))
    }
  } catch (err) {
    error.value =
      err instanceof ApiError && err.code === 'PRECONDITION_FAILED'
        ? err.message
        : rewinding.value
          ? 'The story could not go back. Nothing has changed; try again.'
          : 'The new story could not be started. Nothing has changed; try again.'
  } finally {
    busy.value = false
  }
}

async function openSaved(): Promise<void> {
  if (!done.value) return
  const id = done.value.saved_story_id
  const role = done.value.role
  emit('close')
  await router.push(storyLocation(id, role))
}

function close(): void {
  if (!busy.value) emit('close')
}
</script>

<template>
  <Transition name="ev-modal">
    <div
      v-if="open && turn !== null"
      class="branch"
      role="dialog"
      aria-modal="true"
      aria-labelledby="branch-title"
      @click.self="close"
      @keydown.esc="close">
      <div v-if="done" class="branch__card">
        <p class="branch__kicker">Gone back</p>
        <h2 id="branch-title" class="branch__title">The story continues from {{ when }}</h2>
        <ul class="branch__points">
          <li>Everyone is where they were at the end of that turn. Your next turn starts here.</li>
          <li>
            The turns you left are kept as <b>{{ done.saved_title }}</b
            >. Open it any time from Stories.
          </li>
        </ul>
        <div class="branch__actions">
          <button type="button" class="branch__cancel ev-press" @click="openSaved">
            Open the path not taken
          </button>
          <button type="button" class="branch__go ev-press" @click="close">Carry on here</button>
        </div>
      </div>
      <div v-else-if="rewinding" class="branch__card">
        <p class="branch__kicker">Go back to this turn</p>
        <h2 id="branch-title" class="branch__title">Go back to {{ when }}</h2>
        <ul class="branch__points">
          <li>
            <b>{{ storyTitle }}</b> continues from the end of this turn: everyone where they were,
            with what they carried, what they knew and the rumours as they stood then.
          </li>
          <li>
            {{ laterWords }} removed from this story.
            {{ later === 1 ? "It isn't lost: it is kept" : "They aren't lost: they are kept" }} as a
            separate story you can open from Stories.
          </li>
          <li>Pictures still being painted for the later turns are dropped.</li>
        </ul>
        <p class="branch__name">
          The later turns will be called <b>{{ savedTitle }}</b>
        </p>
        <p v-if="error" class="branch__error" role="alert">{{ error }}</p>
        <div class="branch__actions">
          <button type="button" class="branch__cancel ev-press" :disabled="busy" @click="close">
            Cancel
          </button>
          <button type="button" class="branch__go ev-press" :disabled="busy" @click="start">
            {{ busy ? 'Going back…' : 'Go back to this turn' }}
          </button>
        </div>
      </div>
      <div v-else class="branch__card">
        <p class="branch__kicker">Branch from here</p>
        <h2 id="branch-title" class="branch__title">Start a new story from {{ when }}</h2>
        <ul class="branch__points">
          <li>
            The new story begins at the end of this turn: everyone where they were, with what they
            carried, what they knew and the rumours as they stood then.
          </li>
          <li>
            <b>{{ storyTitle }}</b> stays exactly as it is. You can go back to it any time from
            Stories.
          </li>
          <li>Pictures still being painted stay with the original story.</li>
        </ul>
        <p class="branch__name">
          It will be called <b>{{ title }}</b>
        </p>
        <p v-if="error" class="branch__error" role="alert">{{ error }}</p>
        <div class="branch__actions">
          <button type="button" class="branch__cancel ev-press" :disabled="busy" @click="close">
            Cancel
          </button>
          <button type="button" class="branch__go ev-press" :disabled="busy" @click="start">
            {{ busy ? 'Starting the new story…' : 'Start the new story' }}
          </button>
        </div>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.branch {
  position: fixed;
  inset: 0;
  background: rgba(43, 36, 22, 0.45);
  display: grid;
  place-items: center;
  padding: 16px;
  z-index: 60;
}
.branch__card {
  max-width: 520px;
  width: 100%;
  background: #fbf6e9;
  border: 1px solid var(--line);
  border-radius: 14px;
  padding: 20px 22px;
  box-shadow: 0 18px 40px rgba(43, 36, 22, 0.25);
}
.branch__kicker {
  margin: 0;
  font-family: var(--font-ui);
  font-size: 12px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--ember);
}
.branch__title {
  margin: 4px 0 10px;
  font-family: 'Cormorant Garamond', Georgia, serif;
  font-size: 26px;
  line-height: 1.15;
}
.branch__points {
  margin: 0;
  padding-left: 18px;
  display: grid;
  gap: 6px;
  font-family: var(--font-body);
  font-size: 15px;
  color: #4a3f2c;
}
.branch__name {
  margin: 14px 0 0;
  font-family: var(--font-ui);
  font-size: 14px;
  color: #6b5d43;
}
.branch__error {
  margin: 12px 0 0;
  padding: 8px 10px;
  border-radius: 8px;
  background: #f6e3d6;
  color: #7a2e12;
  font-family: var(--font-ui);
  font-size: 14px;
}
.branch__actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 18px;
  flex-wrap: wrap;
}
.branch__cancel,
.branch__go {
  font-family: var(--font-ui);
  font-size: 15px;
  border-radius: 9px;
  padding: 8px 16px;
  cursor: pointer;
  border: 1px solid var(--line);
  transition:
    background 0.2s ease,
    border-color 0.2s ease;
}
.branch__cancel {
  background: none;
}
.branch__cancel:hover {
  background: var(--panel-2);
}
.branch__go {
  background: var(--ember);
  border-color: var(--ember);
  color: #fffaf0;
}
.branch__go:hover {
  filter: brightness(1.05);
}
.branch__go:disabled,
.branch__cancel:disabled {
  opacity: 0.7;
  cursor: progress;
}
</style>
