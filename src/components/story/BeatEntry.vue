<script setup lang="ts">
import { computed, onMounted, watch } from 'vue'
import type { TimelineEntry } from '../../../content/clients/worldsim'
import type { BeatDetailState } from '../../composables/useStory'
import { readScene, sceneCitations, type ScenePointer, type TopicRecord } from './beatReading'

const props = defineProps<{
  index: number
  entries: TimelineEntry[]
  /** Every distinct scene pointer in this beat, in timeline order. */
  pointers: ScenePointer[]
  loadedMap: Record<string, BeatDetailState | undefined>
  nameOf: (id: string) => string
  youId?: string | null
}>()

const emit = defineEmits<{ (e: 'request-details', eventIds: string[]): void }>()

function request(): void {
  const missing = props.pointers.map((p) => p.eventId).filter((id) => !props.loadedMap[id])
  if (missing.length > 0) emit('request-details', missing)
}

onMounted(request)
watch(() => [props.pointers, props.loadedMap], request)

function displayName(id: string | null | undefined): string {
  if (!id) return 'Narration'
  const name = props.nameOf(id)
  return props.youId && id === props.youId ? `${name} (you)` : name
}

function initial(name: string): string {
  return (name.trim().charAt(0) || '·').toUpperCase()
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

/**
 * A supplementary topic as a verbatim record: quotation marks preserved
 * as written, never presented as speech, never a commitment claim.
 */
function recordLine(record: TopicRecord): string {
  const speaker = displayName(record.speakerId)
  const whom = record.targetId ? `${speaker} → ${displayName(record.targetId)}` : speaker
  return record.quoted ? `${whom} · ${record.topic}` : `${whom} · topic: ${record.topic}`
}

type Segment = { kind: 'rich'; pointer: ScenePointer } | { kind: 'legacy'; entry: TimelineEntry }

/**
 * The beat in timeline order: one rich segment per pointed event (its
 * scenes, or its snippet lines when every read failed), legacy lines for
 * entries without pointers. Later rows of an already-rendered event are
 * covered by that event's segment — never repeated.
 */
const segments = computed<Segment[]>(() => {
  const out: Segment[] = []
  const seen = new Set<string>()
  for (const entry of props.entries) {
    const pointer = props.pointers.find((p) => p.eventId === entry.event_id)
    if (pointer) {
      if (!seen.has(pointer.eventId)) {
        seen.add(pointer.eventId)
        out.push({ kind: 'rich', pointer })
      }
    } else {
      out.push({ kind: 'legacy', entry })
    }
  }
  return out
})

function eventSnippets(eventId: string): TimelineEntry[] {
  return props.entries.filter((e) => e.event_id === eventId && e.snippet)
}
</script>

<template>
  <article class="beat" :aria-label="`Beat ${index}`">
    <h3 class="beat__head">Beat {{ index }}</h3>
    <template v-for="(segment, si) in segments" :key="si">
      <template v-if="segment.kind === 'legacy'">
        <p class="beat__kind">{{ segment.entry.event_type.replace(/_/g, ' ') }}</p>
        <p v-if="segment.entry.snippet" class="beat__text">{{ segment.entry.snippet }}</p>
      </template>
      <template
        v-else-if="
          !loadedMap[segment.pointer.eventId] || loadedMap[segment.pointer.eventId]?.pending
        ">
        <p class="beat__empty" role="status">Gathering structured beat…</p>
      </template>
      <template v-else-if="loadedMap[segment.pointer.eventId]?.failed">
        <template
          v-for="entry in eventSnippets(segment.pointer.eventId)"
          :key="entry.event_id + entry.sequence">
          <p class="beat__kind">{{ entry.event_type.replace(/_/g, ' ') }}</p>
          <p class="beat__text">{{ entry.snippet }}</p>
        </template>
      </template>
      <template v-else>
        <template v-for="scene in loadedMap[segment.pointer.eventId]!.scenes" :key="scene.sceneId">
          <template v-if="!scene.failed && scene.detail">
            <template
              v-for="(block, bi) in readScene(scene.detail, scene.narration).blocks"
              :key="bi">
              <div v-if="block.type === 'say'" class="beat__say">
                <span class="beat__avatar" aria-hidden="true">{{
                  initial(displayName(block.speakerId))
                }}</span>
                <div>
                  <p class="beat__speaker">{{ displayName(block.speakerId) }}</p>
                  <template v-for="para in paragraphs(block.text)" :key="para.join('|')">
                    <p class="beat__text">
                      <template v-for="(ln, j) in para" :key="j">
                        {{ ln }}<br v-if="j < para.length - 1" />
                      </template>
                    </p>
                  </template>
                </div>
              </div>
              <template v-else>
                <template v-for="para in paragraphs(block.text)" :key="para.join('|')">
                  <p class="beat__text">
                    <template v-for="(ln, k) in para" :key="k">
                      {{ ln }}<br v-if="k < para.length - 1" />
                    </template>
                  </p>
                </template>
              </template>
            </template>
            <details class="beat__details">
              <summary>Beat details</summary>
              <ul v-if="(scene.detail.attempts ?? []).length">
                <li v-for="a in scene.detail.attempts ?? []" :key="a.id">
                  {{ displayName(a.actor_character_id) }} — {{ a.observable_summary }} ({{
                    a.status.replace(/_/g, ' ')
                  }})
                </li>
              </ul>
              <template v-if="readScene(scene.detail, scene.narration).records.length">
                <p class="beat__records-head">
                  Communication records (topics as filed — not speech):
                </p>
                <ul>
                  <template
                    v-for="record in readScene(scene.detail, scene.narration).records"
                    :key="record.speakerId + record.topic">
                    <li>{{ recordLine(record) }}</li>
                  </template>
                </ul>
              </template>
              <p v-if="scene.detail.resolution">
                Outcome {{ scene.detail.resolution.outcome }} · resolver
                {{ scene.detail.resolution.resolver }}.
                {{ scene.detail.resolution.rationale }}
              </p>
              <p v-if="sceneCitations(scene.narration).length">
                Cites: {{ sceneCitations(scene.narration).join(', ') }}
              </p>
              <p v-if="segment.pointer.fallback">
                Narration for this beat fell back to a deterministic stand-in.
              </p>
              <p v-else>Narrated beat.</p>
              <p v-if="scene.detail.status !== 'committed'">
                Scene state: {{ scene.detail.status.replace(/_/g, ' ') }}.
              </p>
            </details>
          </template>
          <template v-else>
            <template
              v-for="entry in eventSnippets(segment.pointer.eventId)"
              :key="entry.event_id + entry.sequence">
              <p class="beat__kind">{{ entry.event_type.replace(/_/g, ' ') }}</p>
              <p class="beat__text">{{ entry.snippet }}</p>
            </template>
          </template>
        </template>
      </template>
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
.beat__records-head {
  margin: 6px 0 2px;
  font-size: 13px;
  color: #6b5d43;
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
