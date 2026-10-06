<script setup lang="ts">
/**
 * Paint this scene: the server suggests a prompt (who is there, what
 * happens, where); the player may edit it before painting. The people
 * listed keep their faces (their portraits are sent as references), so
 * the words need not describe them exactly. Painting runs in the
 * background; the picture appears under the scene once ready.
 */
import { computed, ref, watch } from 'vue'
import { getPictureSuggestion, paintScene, type CallOptions } from '../../api/worldsim'
import type { PictureSuggestion } from '../../../content/clients/worldsim'

const props = defineProps<{
  worldId: string
  sceneId: string | null
  opts: CallOptions
}>()
const emit = defineEmits<{ close: []; painted: [] }>()

const offer = ref<PictureSuggestion | null>(null)
const prompt = ref('')
const loading = ref(false)
const busy = ref(false)
const problem = ref<string | null>(null)

const PROMPT_MAX = 2000
const canPaint = computed(
  () =>
    !busy.value &&
    !loading.value &&
    offer.value?.available === true &&
    prompt.value.trim().length > 0 &&
    prompt.value.length <= PROMPT_MAX
)
const edited = computed(() => offer.value !== null && prompt.value !== offer.value.prompt)

watch(
  () => props.sceneId,
  async (sceneId) => {
    offer.value = null
    problem.value = null
    if (!sceneId) return
    loading.value = true
    try {
      offer.value = await getPictureSuggestion(props.worldId, sceneId, props.opts)
      prompt.value = offer.value.prompt
    } catch (err) {
      problem.value = err instanceof Error ? err.message : 'Could not prepare this scene.'
    } finally {
      loading.value = false
    }
  },
  { immediate: true }
)

function reset(): void {
  if (offer.value) prompt.value = offer.value.prompt
}

async function paint(): Promise<void> {
  if (!props.sceneId || !canPaint.value) return
  busy.value = true
  problem.value = null
  try {
    await paintScene(
      props.sceneId,
      { world_id: props.worldId, prompt: prompt.value.trim() },
      props.opts
    )
    emit('painted')
    emit('close')
  } catch (err) {
    problem.value = err instanceof Error ? err.message : 'The picture could not be started.'
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div
    v-if="sceneId"
    class="paint-dlg"
    role="dialog"
    aria-modal="true"
    aria-label="Paint this scene"
    @click.self="!busy && emit('close')"
    @keydown.esc="!busy && emit('close')">
    <form class="paint-dlg__card" @submit.prevent="paint">
      <h2>Paint this scene</h2>
      <p class="paint-dlg__lead">
        Here is what the painter will be told. Change anything you like: add a mood, a detail, the
        time of day.
      </p>

      <p v-if="loading" class="paint-dlg__step" role="status">Reading the scene…</p>
      <template v-else-if="offer">
        <div class="paint-dlg__who">
          <span
            v-for="c in offer.characters"
            :key="c.character_id"
            class="who"
            :class="{ 'who--face': c.has_face }">
            {{ c.name }}
            <small>{{ c.has_face ? 'keeps their face' : 'no portrait yet' }}</small>
          </span>
          <span v-if="offer.place" class="who who--place">
            {{ offer.place }} <small>its art as a guide</small>
          </span>
        </div>

        <label class="ev-field-label" for="paint-prompt">Prompt</label>
        <textarea
          id="paint-prompt"
          v-model="prompt"
          class="ev-input paint-dlg__prompt"
          rows="6"
          :maxlength="PROMPT_MAX"
          :disabled="busy"
          autofocus />
        <p v-if="offer.added_before || offer.added_after" class="paint-dlg__added">
          From Story settings, also added:
          <template v-if="offer.added_before">
            before “<b>{{ offer.added_before }}</b
            >”</template
          ><template v-if="offer.added_before && offer.added_after">, </template>
          <template v-if="offer.added_after"
            >after “<b>{{ offer.added_after }}</b
            >”</template
          >.
        </p>
        <p class="paint-dlg__meta">
          <span>{{ prompt.length }} / {{ PROMPT_MAX }}</span>
          <button v-if="edited" type="button" class="paint-dlg__reset" @click="reset">
            Back to the suggestion
          </button>
        </p>
        <p v-if="!offer.available" class="paint-dlg__problem" role="alert">
          No image machine is set up, so nothing can be painted yet (Settings › Image generation).
        </p>
      </template>

      <p v-if="problem" class="paint-dlg__problem" role="alert">{{ problem }}</p>
      <p v-else-if="busy" class="paint-dlg__step" role="status">Handing it to the painter…</p>
      <p v-else class="paint-dlg__hint">
        It appears under the scene in about 15 seconds; keep playing meanwhile.
      </p>

      <div class="paint-dlg__buttons">
        <button type="button" class="paint-dlg__cancel" :disabled="busy" @click="emit('close')">
          Cancel
        </button>
        <button type="submit" class="paint-dlg__go" :disabled="!canPaint">Paint</button>
      </div>
    </form>
  </div>
</template>

<style scoped>
.paint-dlg {
  position: fixed;
  inset: 0;
  z-index: 50;
  display: grid;
  place-items: center;
  padding: 16px;
  background: rgba(43, 36, 22, 0.45);
}
.paint-dlg__card {
  width: 100%;
  max-width: 600px;
  max-height: calc(100vh - 32px);
  overflow-y: auto;
  background: linear-gradient(180deg, var(--surface-2), var(--surface));
  border: 1px solid var(--line);
  border-radius: var(--radius-card);
  box-shadow: var(--card-shadow);
  padding: 22px 26px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.paint-dlg__card h2 {
  font-family: var(--font-display);
  font-size: 30px;
  color: var(--ink);
}
.paint-dlg__lead {
  color: var(--ink-3);
  margin-bottom: 4px;
}
.paint-dlg__who {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 4px;
}
.who {
  display: inline-flex;
  flex-direction: column;
  padding: 6px 12px;
  border-radius: 10px;
  border: 1px solid var(--line);
  background: #fbf6e9;
  font-weight: 600;
  color: var(--ink-2);
  line-height: 1.25;
}
.who small {
  font-weight: 400;
  font-size: 12.5px;
  color: var(--muted);
}
.who--face {
  border-color: #9cc4b9;
  background: #eef6f2;
}
.who--face small {
  color: var(--teal-ink);
}
.who--place {
  background: #f6efdf;
}
.paint-dlg__prompt {
  height: auto;
  min-height: 140px;
  padding: 10px 12px;
  resize: vertical;
  line-height: 1.5;
}
.paint-dlg__meta {
  display: flex;
  justify-content: space-between;
  font-size: 13px;
  color: var(--muted);
}
.paint-dlg__reset {
  color: var(--teal-ink);
  text-decoration: underline;
  text-underline-offset: 3px;
}
.paint-dlg__added {
  font-size: 13.5px;
  color: var(--ink-3);
  line-height: 1.45;
}
.paint-dlg__added b {
  font-weight: 600;
  color: var(--ink-2);
}
.paint-dlg__hint {
  font-size: 14px;
  color: var(--muted);
}
.paint-dlg__problem {
  color: #9a3b2b;
}
.paint-dlg__step {
  color: var(--teal-ink);
  font-style: italic;
}
.paint-dlg__buttons {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 6px;
}
.paint-dlg__cancel {
  color: var(--ink-3);
}
.paint-dlg__go {
  background: linear-gradient(180deg, var(--teal-hi), var(--teal));
  color: var(--cream-on-teal);
  border-radius: 10px;
  padding: 8px 26px;
  font-size: 17px;
}
.paint-dlg__go:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
