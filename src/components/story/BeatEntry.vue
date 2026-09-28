<script setup lang="ts">
import { computed, onMounted, watch } from 'vue'
import type { BeatView, TimelineEntry } from '../../../content/clients/worldsim'
import type { BeatDetailState, LoadedScene } from '../../composables/useStory'

const props = defineProps<{
  index: number
  entries: TimelineEntry[]
  /** Structured-content pointer for this beat, if committed this session. */
  beatRef?: { fallback: boolean }
  /** The pointer's event id: the beat entry the structured content joins on
   * (not the beat's first entry — world_ticked rows sort before the beat's
   * own resolved event). */
  detailEventId?: string
  /** Loaded scene content; absent while pending or failed. */
  loaded?: BeatDetailState
  nameOf: (id: string) => string
  youId?: string | null
}>()

const emit = defineEmits<{ (e: 'request-detail', eventId: string): void }>()

function request(): void {
  if (props.beatRef && !props.loaded && props.detailEventId) {
    emit('request-detail', props.detailEventId)
  }
}

onMounted(request)
watch(() => [props.beatRef, props.loaded, props.detailEventId], request)

/** Backend attempt summaries arrive prefixed (`attempt:wait: …`): technical records, not prose. */
function isAttemptRecord(text: string): boolean {
  return /^attempt:[a-z_]+:/.test(text.trim())
}

function paragraphs(text: string): string[][] {
  return text
    .split(/\n{2,}/)
    .map((block) =>
      block
        .split('\n')
        .map((line) => line.trim())
        .filter(Boolean)
    )
    .filter((lines) => lines.length > 0)
}

function displayName(id: string | null | undefined): string {
  if (!id) return 'Narration'
  const name = props.nameOf(id)
  return props.youId && id === props.youId ? `${name} (you)` : name
}

function initial(name: string): string {
  return (name.trim().charAt(0) || '·').toUpperCase()
}

function cleanTopic(topic: unknown): string | null {
  if (typeof topic !== 'string' || !topic.trim()) return null
  const trimmed = topic.trim()
  return trimmed.length > 1 && trimmed.startsWith('"') && trimmed.endsWith('"')
    ? trimmed.slice(1, -1)
    : trimmed
}

interface SpeakLine {
  key: string
  speakerId: string | null
  text: string
}

function sceneLines(scene: LoadedScene): { spoken: SpeakLine[]; prose: string[] } {
  const spoken: SpeakLine[] = []
  const prose: string[] = []
  for (const beat of scene.narration) {
    if (beat.kind === 'dialogue') {
      spoken.push({ key: beat.id, speakerId: beat.speaker_id ?? null, text: beat.text })
    } else if (!isAttemptRecord(beat.text ?? '')) {
      prose.push(beat.text)
    }
  }
  if (spoken.length === 0) {
    // No voiced dialogue beats: fall back to the structured
    // communicate intents/reactions (never the mashed snippet).
    const says: SpeakLine[] = []
    for (const intent of scene.detail.intents ?? []) {
      if (intent.family !== 'communicate') continue
      const topic = cleanTopic((intent.detail as Record<string, unknown> | null)?.['topic'])
      if (topic) {
        says.push({ key: intent.id, speakerId: intent.author_character_id, text: topic })
      }
    }
    for (const reaction of scene.detail.reactions ?? []) {
      if (reaction.family !== 'communicate') continue
      const topic = cleanTopic((reaction.detail as Record<string, unknown> | null)?.['topic'])
      if (topic) {
        says.push({ key: reaction.id, speakerId: reaction.reactor_character_id, text: topic })
      }
    }
    spoken.push(...says)
  }
  return { spoken, prose }
}

interface TechLine {
  key: string
  text: string
}

function sceneTech(scene: LoadedScene): { attempts: TechLine[]; citations: string[] } {
  const attempts = (scene.detail.attempts ?? []).map((a) => ({
    key: a.id,
    text: `${displayName(a.actor_character_id)} — ${a.observable_summary} (${a.status.replace(/_/g, ' ')})`
  }))
  const citations = scene.narration.flatMap((b: BeatView) => b.cited_fact_keys ?? [])
  return { attempts, citations: [...new Set(citations)] }
}

const rich = computed(() => props.loaded && !props.loaded.failed && props.loaded.scenes.length > 0)
</script>

<template>
  <article class="beat" :aria-label="`Beat ${index}`">
    <h3 class="beat__head">Beat {{ index }}</h3>
    <template v-if="rich">
      <template v-for="scene in loaded!.scenes" :key="scene.detail.id">
        <template v-for="line in sceneLines(scene).spoken" :key="line.key">
          <div class="beat__say">
            <span class="beat__avatar" aria-hidden="true">{{
              initial(displayName(line.speakerId))
            }}</span>
            <div>
              <p class="beat__speaker">{{ displayName(line.speakerId) }}</p>
              <template v-for="para in paragraphs(line.text)" :key="para.join('|')">
                <p class="beat__text">
                  <template v-for="(ln, j) in para" :key="j">
                    {{ ln }}<br v-if="j < para.length - 1" />
                  </template>
                </p>
              </template>
            </div>
          </div>
        </template>
        <template v-for="text in sceneLines(scene).prose" :key="text">
          <template v-for="para in paragraphs(text)" :key="para.join('|')">
            <p class="beat__text">
              <template v-for="(ln, k) in para" :key="k">
                {{ ln }}<br v-if="k < para.length - 1" />
              </template>
            </p>
          </template>
        </template>
        <details class="beat__details">
          <summary>Beat details</summary>
          <ul v-if="sceneTech(scene).attempts.length">
            <li v-for="a in sceneTech(scene).attempts" :key="a.key">{{ a.text }}</li>
          </ul>
          <p v-if="scene.detail.resolution">
            Outcome {{ scene.detail.resolution.outcome }} · resolver
            {{ scene.detail.resolution.resolver }}.
            {{ scene.detail.resolution.rationale }}
          </p>
          <p v-if="sceneTech(scene).citations.length">
            Cites: {{ sceneTech(scene).citations.join(', ') }}
          </p>
          <p v-if="beatRef?.fallback">
            Narration for this beat fell back to a deterministic stand-in.
          </p>
          <p v-else>Narrated beat.</p>
          <p v-if="scene.detail.status !== 'committed'">
            Scene state: {{ scene.detail.status.replace(/_/g, ' ') }}.
          </p>
        </details>
      </template>
    </template>
    <template v-else>
      <template v-for="entry in entries" :key="entry.event_id">
        <p class="beat__kind">{{ entry.event_type.replace(/_/g, ' ') }}</p>
        <p v-if="entry.snippet" class="beat__text">{{ entry.snippet }}</p>
      </template>
      <p v-if="beatRef && loaded?.pending" class="beat__empty" role="status">
        Gathering structured beat…
      </p>
    </template>
  </article>
</template>

<style scoped>
.beat {
  border-top: 1px solid var(--line);
  padding-top: 8px;
  display: grid;
  gap: 8px;
}
.beat__head {
  margin: 0;
  font-size: 14px;
  color: #4a4436;
}
.beat__say {
  display: flex;
  gap: 10px;
  align-items: flex-start;
}
.beat__avatar {
  flex: none;
  width: 30px;
  height: 30px;
  border-radius: 50%;
  background: #1f4d3f;
  color: #fbf6e9;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 15px;
}
.beat__speaker {
  margin: 0 0 2px;
  font-weight: 700;
  font-size: 14px;
}
.beat__text {
  margin: 0 0 6px;
  line-height: 1.5;
}
.beat__kind {
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: #6b5d43;
  margin: 0;
}
.beat__empty {
  color: #6b5d43;
  font-size: 13px;
  margin: 0;
}
.beat__details {
  font-size: 13px;
  color: #4a4436;
}
.beat__details summary {
  cursor: pointer;
  color: #1f4d3f;
  text-decoration: underline;
}
.beat__details ul {
  margin: 6px 0;
  padding-left: 18px;
}
.beat__details p {
  margin: 4px 0;
}
</style>
