<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import SetupDialog from '../components/story/SetupDialog.vue'
import MountainRidge from '../components/decor/MountainRidge.vue'
import PageIntro from '../components/ui/PageIntro.vue'
import MenuButton from '../components/MenuButton.vue'
import IconArrowLeft from '../components/icons/IconArrowLeft.vue'
import IconArrowRight from '../components/icons/IconArrowRight.vue'
import { useBackend } from '../composables/useBackend'
import { useInterventions, type DirectMode } from '../composables/useInterventions'
import { usePlayerAsk } from '../composables/usePlayerAsk'
import { useStory } from '../composables/useStory'
import { selectSeat } from '../api/worldsim'
import type { Role } from '../api/http'
import { phaseLabel } from '../game/format'

const route = useRoute()
const router = useRouter()
const storyId = computed(() => String(route.params.storyId ?? ''))
const backend = useBackend()

// Identity is authoritative, never inferred from display names: the room
// sends the persisted grant's role and controlled runtime id (matched
// directly against map occupant ids). The mode badge below is read-only —
// headers alone never switch the actual grant.
const headerRole = computed(() => story.effectiveRole.value)
const headerChar = computed<string | undefined>(() => {
  if (story.effectiveRole.value !== 'player') return undefined
  return controlledId.value ?? undefined
})
const story = useStory(storyId, headerRole, headerChar)
const showSetup = ref(false)
const travelChar = ref('')
const travelTo = ref('')

// Director/God seats (E6): the persisted grant is the seat. Taking one
// replaces the grant at a safe boundary; the server rejects mid-run
// switches. The room badge stays a read-only reflection of that grant.
const seat = computed<'director' | 'deity' | null>(() => {
  const granted = story.grant.value?.role
  return granted === 'director' || granted === 'deity' ? granted : null
})
const seatLabel = computed(() =>
  seat.value === 'director'
    ? 'Director'
    : seat.value === 'deity'
      ? 'Deity'
      : story.effectiveRole.value === 'player'
        ? 'Player'
        : 'Observer'
)
// A bound player seat is never displaced by the seat buttons.
const canTakeSeat = computed(() => story.grantLoaded.value && story.grant.value?.role !== 'player')
const seatBusy = ref(false)
const seatError = ref<string | null>(null)
const queueCtl = useInterventions(
  () => storyId.value,
  () => ({
    role: (seat.value ?? story.effectiveRole.value) as Role,
    characterId: headerChar.value ?? undefined
  })
)
const directMode = computed<DirectMode>(() => (seat.value === 'deity' ? 'force' : 'influence'))
const directionText = ref('')
const editText = ref('')

async function takeSeat(next: 'director' | 'deity' | 'watcher'): Promise<void> {
  seatBusy.value = true
  seatError.value = null
  try {
    await selectSeat(storyId.value, next, { role: story.effectiveRole.value })
    await story.load()
    queueCtl.select(null)
    await queueCtl.refresh()
  } catch (err) {
    seatError.value = err instanceof Error ? err.message : 'could not take the seat'
  } finally {
    seatBusy.value = false
  }
}

async function fileDirection(): Promise<void> {
  if (!directionText.value.trim() || !seat.value) return
  const item = await queueCtl.submit(directMode.value, directionText.value.trim())
  if (item) directionText.value = ''
}

function pickDirection(id: string): void {
  queueCtl.select(id)
  editText.value = queueCtl.active.value?.text ?? ''
}

async function resubmitEdit(): Promise<void> {
  if (!editText.value.trim()) return
  const item = await queueCtl.editActive(editText.value.trim())
  if (item) editText.value = ''
}

const detail = computed(() => story.detail.value)
const cast = computed(() => {
  const rows: { id: string; name: string; places: string[] }[] = []
  story.occupantsByPlace.value.forEach((row: { name: string; places: string[] }, id: string) =>
    rows.push({ id, ...row })
  )
  return rows.sort((a, b) => a.name.localeCompare(b.name))
})
const controlledId = computed(() => story.controlledRuntimeId.value)
const controlledName = computed(
  () => cast.value.find((c) => c.id === controlledId.value)?.name ?? null
)
const controlledMissing = computed(
  () =>
    story.effectiveRole.value === 'player' &&
    story.grantLoaded.value &&
    controlledId.value !== null &&
    controlledName.value === null
)
const playerReady = computed(() => {
  if (story.effectiveRole.value !== 'player') return true
  return story.grantLoaded.value && controlledId.value !== null
})
const travelChoices = computed(() => {
  if (story.effectiveRole.value === 'player' && controlledId.value) {
    return cast.value.filter((c) => c.id === controlledId.value)
  }
  return cast.value
})
const destinations = computed(() => {
  const places = story.map.value?.places ?? []
  const here = places.find((p) => (p.occupant_ids ?? []).includes(travelChar.value))
  return (here?.routes ?? []).map((r: { to_location_id: string }) => ({
    id: r.to_location_id,
    name:
      places.find((p: { id: string; name: string }) => p.id === r.to_location_id)?.name ??
      r.to_location_id
  }))
})
const nextIndex = computed(() => (detail.value?.absolute_index ?? 0) + 1)

async function advance(): Promise<void> {
  await story.advance()
  // Queued directions drain during the beat: re-read their states afterward.
  if (seat.value) await queueCtl.refresh()
}

// Player action: the controlled character speaks to one castmate. The
// attempt files with the next committed beat — reactions, resolution and
// narration follow — never alone. Co-located castmates sort first.
const NIL_SNAPSHOT = '00000000-0000-0000-0000-000000000000'
const askTarget = ref('')
const askText = ref('')
const askTargets = computed(() => {
  const mine = controlledId.value
  const others = cast.value.filter((c) => c.id !== mine)
  if (!mine) return others
  const here = new Set(cast.value.find((c) => c.id === mine)?.places ?? [])
  const shared = others.filter((c) => c.places.some((p) => here.has(p)))
  return [...shared, ...others.filter((c) => !shared.includes(c))]
})

watch(
  askTargets,
  (rows) => {
    if (!rows.some((c) => c.id === askTarget.value)) askTarget.value = rows[0]?.id ?? ''
  },
  { immediate: true }
)

const submitAsk = usePlayerAsk((intents) => story.advance(intents), askText)

async function askQuestion(): Promise<void> {
  const actor = controlledId.value
  const target = askTarget.value
  if (!actor || !target) return
  await submitAsk((topic) => ({
    [actor]: {
      family: 'communicate',
      character_id: actor,
      snapshot_id: NIL_SNAPSHOT,
      target_character_id: target,
      topic
    }
  }))
}

async function travel(): Promise<void> {
  if (!travelChar.value || !travelTo.value) return
  await story.travel(travelChar.value, travelTo.value)
}

// The controlled actor wins over alphabetical order: as soon as the grant
// resolves, travel targets the controlled runtime id.
watch(
  [cast, controlledId],
  ([rows, controlled]) => {
    if (controlled) {
      travelChar.value = controlled
      return
    }
    if (!travelChar.value && rows.length) travelChar.value = rows[0].id
  },
  { immediate: true }
)
watch(destinations, (rows) => {
  travelTo.value = rows[0]?.id ?? ''
})

onMounted(() => {
  void story.load().then(() => {
    if (seat.value) void queueCtl.refresh()
  })
  void backend.refresh()
})
onUnmounted(() => {
  story.cancel()
  queueCtl.dispose()
})
</script>

<template>
  <main class="play">
    <section class="play__band ev-card">
      <MountainRidge class="play__ridge" />
      <PageIntro
        :title="detail?.title ?? 'Opening the story…'"
        :sub="
          detail
            ? `Day ${detail.day} · ${phaseLabel(detail.phase)}`
            : 'Loading the world behind this tale.'
        " />
    </section>
    <p v-if="story.loadError.value" class="play__state" role="alert">
      {{ story.loadError.value }} —
      <button type="button" class="play__link" @click="story.load()">retry</button>
    </p>
    <template v-else-if="detail">
      <p class="play__meta">
        <span class="play__badge">{{ seatLabel }}</span>
        <span v-if="controlledName">Playing as {{ controlledName }}</span>
        <span v-else-if="story.effectiveRole.value === 'player' && !story.grantLoaded.value">
          Resolving player…
        </span>
        <span>Beat {{ detail.absolute_index }}</span>
        <button type="button" class="play__link" @click="showSetup = true">
          Initial configuration
        </button>
        <span class="play__as">Mode set by the story grant</span>
      </p>
      <p v-if="controlledMissing" class="play__notice play__notice--error" role="alert">
        The controlled character is not on the map — travel is unavailable until they appear.
      </p>
      <p v-if="backend.status.value.modelProfile" class="play__notice" role="status">
        Development model active ({{ backend.status.value.modelProfile }}) — beats are deterministic
        stand-ins, not live provider prose.
      </p>
      <p
        v-if="story.notice.value"
        class="play__notice"
        :class="`play__notice--${story.notice.value.kind}`"
        role="status">
        {{ story.notice.value.text }}
      </p>
      <div class="play__grid">
        <section class="play__card" aria-label="Cast and places">
          <h2>Cast &amp; places</h2>
          <ul class="play__cast">
            <li v-for="member in cast" :key="member.id">
              <strong>{{ member.name }}</strong>
              <span>{{ member.places.join(', ') }}</span>
              <em v-if="member.id === controlledId">you</em>
            </li>
          </ul>
          <h3>Begin a journey</h3>
          <div class="play__travel">
            <label>
              Who
              <select
                v-model="travelChar"
                :disabled="story.effectiveRole.value === 'player' && !!controlledId">
                <option v-for="member in travelChoices" :key="member.id" :value="member.id">
                  {{ member.name }} — {{ member.places.join(', ') }}
                </option>
              </select>
            </label>
            <label>
              To
              <select v-model="travelTo">
                <option v-for="dest in destinations" :key="dest.id" :value="dest.id">
                  {{ dest.name }}
                </option>
              </select>
            </label>
            <MenuButton
              :disabled="!travelChar || !travelTo || story.traveling.value || !playerReady"
              @click="travel()">
              {{ story.traveling.value ? 'Starting…' : 'Start journey' }}
            </MenuButton>
          </div>
          <h3>Advance the story</h3>
          <MenuButton
            :icon="IconArrowRight"
            :disabled="story.advancing.value || !story.grantLoaded.value"
            @click="advance()">
            {{ story.advancing.value ? 'Committing beat…' : `Commit beat ${nextIndex}` }}
          </MenuButton>
          <p v-if="story.effectiveRole.value !== 'player'" class="play__empty">
            Watching: beats advance the world without your actions. Player mode is chosen when the
            story is created.
          </p>
        </section>
        <section
          v-if="story.effectiveRole.value === 'player' && controlledId"
          class="play__card"
          aria-label="Speak as your character">
          <h2>Speak as {{ controlledName }}</h2>
          <p class="play__empty">
            Your words file with the next committed beat — the cast's reactions, the resolution and
            the narration follow.
          </p>
          <div class="play__travel">
            <label>
              To
              <select v-model="askTarget" :disabled="!askTargets.length">
                <option v-for="member in askTargets" :key="member.id" :value="member.id">
                  {{ member.name }} — {{ member.places.join(', ') }}
                </option>
              </select>
            </label>
            <label>
              Say
              <input
                v-model="askText"
                type="text"
                maxlength="256"
                placeholder="Ask something in your own words." />
            </label>
            <MenuButton
              :disabled="!askText.trim() || !askTarget || story.advancing.value"
              @click="askQuestion()">
              {{ story.advancing.value ? 'Committing beat…' : 'Ask with the next beat' }}
            </MenuButton>
          </div>
        </section>
        <section class="play__card" aria-label="Story so far">
          <h2>Story so far</h2>
          <p v-if="!story.entries.value.length" class="play__empty">
            Nothing has happened yet — commit the first beat.
          </p>
          <ol v-else class="play__feed">
            <li v-for="entry in [...story.entries.value].reverse()" :key="entry.event_id">
              <span class="play__kind">{{ entry.event_type.replace(/_/g, ' ') }}</span>
              <p v-if="entry.snippet">{{ entry.snippet }}</p>
            </li>
          </ol>
          <p class="play__empty" role="status">
            Showing {{ story.entries.value.length }} loaded events.
            <template v-if="story.hasMore.value"> Older history remains on the server. </template>
          </p>
          <MenuButton
            v-if="story.hasMore.value"
            variant="outline"
            :disabled="story.loadingMore.value"
            @click="story.loadMore()">
            {{ story.loadingMore.value ? 'Loading…' : 'Load older history' }}
          </MenuButton>
        </section>
      </div>
      <section class="play__card" aria-label="Operating seat">
        <h2>Operating seat</h2>
        <p v-if="!canTakeSeat" class="play__empty">
          The player's seat is bound — director seats stay unavailable while it holds.
        </p>
        <template v-else>
          <p class="play__empty">
            Taking a seat replaces the story grant at a safe boundary; mid-run switches are refused.
          </p>
          <div class="play__row">
            <template v-if="!seat">
              <MenuButton :disabled="seatBusy" @click="takeSeat('director')">
                {{ seatBusy ? 'Taking the seat…' : 'Take the Director seat' }}
              </MenuButton>
              <MenuButton :disabled="seatBusy" @click="takeSeat('deity')">
                {{ seatBusy ? 'Taking the seat…' : 'Take the God seat' }}
              </MenuButton>
            </template>
            <MenuButton v-else variant="outline" :disabled="seatBusy" @click="takeSeat('watcher')">
              {{ seatBusy ? 'Leaving the seat…' : 'Return to Observer seat' }}
            </MenuButton>
          </div>
          <p v-if="seatError" class="play__notice play__notice--error" role="alert">
            {{ seatError }}
          </p>
        </template>
      </section>
      <section v-if="seat" class="play__card" aria-label="Direct the story">
        <h2>Direct the story</h2>
        <p class="play__empty">
          Directions can be submitted, edited, and cancelled. Queued directions apply when beats
          commit: starting travel begins a journey — arrival follows when it completes.
        </p>
        <p class="play__empty">
          {{
            seat === 'deity'
              ? 'God mode forces effects: travel, bouts, overrides and persistent conditions.'
              : 'Direct mode proposes hooks and arcs; forcing effects needs the God seat.'
          }}
        </p>
        <label class="play__field">
          Direction
          <textarea
            v-model="directionText"
            rows="3"
            maxlength="2000"
            :disabled="queueCtl.busy.value"
            placeholder="Name characters and places explicitly." />
        </label>
        <div class="play__row">
          <MenuButton
            :disabled="!directionText.trim() || queueCtl.busy.value"
            @click="fileDirection()">
            {{ queueCtl.busy.value ? 'Filing…' : `File direction (${directMode})` }}
          </MenuButton>
          <MenuButton
            v-if="queueCtl.pending.value"
            variant="outline"
            :disabled="queueCtl.busy.value"
            @click="queueCtl.retry()">
            Retry filing
          </MenuButton>
          <MenuButton
            v-if="queueCtl.pending.value"
            variant="outline"
            :disabled="queueCtl.busy.value"
            @click="queueCtl.discardPending()">
            Discard
          </MenuButton>
        </div>
        <p
          v-if="queueCtl.notice.value"
          class="play__notice"
          :class="queueCtl.notice.value.kind === 'error' ? 'play__notice--error' : ''"
          role="status">
          {{ queueCtl.notice.value.text }}
        </p>
        <h3>Queue</h3>
        <p v-if="!queueCtl.queue.value.length" class="play__empty">Nothing filed yet.</p>
        <ol v-else class="play__queue">
          <li v-for="entry in queueCtl.queue.value" :key="entry.id">
            <button type="button" class="play__link" @click="pickDirection(entry.id)">
              {{ entry.text }}
            </button>
            <span class="play__sub"
              >{{ entry.status.replace(/_/g, ' ') }} · {{ entry.mode }} · v{{ entry.version }}</span
            >
            <ul v-if="entry.steps?.length">
              <li v-for="step in entry.steps" :key="step.id">
                {{ step.kind.replace(/_/g, ' ') }} — {{ step.status.replace(/_/g, ' ')
                }}<span v-if="step.failure_reason">: {{ step.failure_reason }}</span>
              </li>
            </ul>
            <p v-if="entry.failure_reason" class="play__sub">{{ entry.failure_reason }}</p>
          </li>
        </ol>
        <template v-if="queueCtl.active.value">
          <h3>Selected direction</h3>
          <label
            v-if="['needs_clarification', 'queued'].includes(queueCtl.active.value.status)"
            class="play__field">
            Revised text
            <textarea
              v-model="editText"
              rows="2"
              maxlength="2000"
              :disabled="queueCtl.busy.value" />
          </label>
          <div class="play__row">
            <MenuButton
              v-if="['needs_clarification', 'queued'].includes(queueCtl.active.value.status)"
              :disabled="!editText.trim() || queueCtl.busy.value"
              @click="resubmitEdit()">
              Resubmit text
            </MenuButton>
            <MenuButton
              v-if="!['completed', 'cancelled', 'failed'].includes(queueCtl.active.value.status)"
              variant="outline"
              :disabled="queueCtl.busy.value"
              @click="queueCtl.cancelActive()">
              Cancel direction
            </MenuButton>
          </div>
        </template>
      </section>
      <footer class="play__foot">
        <MenuButton variant="outline" :icon="IconArrowLeft" @click="router.push('/stories')"
          >All stories</MenuButton
        >
      </footer>
    </template>
    <p v-else class="play__state" role="status">Loading…</p>
    <SetupDialog :setup="story.setup.value" :open="showSetup" @close="showSetup = false" />
  </main>
</template>

<style scoped>
.play {
  max-width: 1100px;
  margin: 0 auto;
  padding: 14px 16px 40px;
}
.play__state {
  padding: 18px;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: #fbf6e9;
}
.play__link {
  font: inherit;
  color: #1f4d3f;
  background: none;
  border: none;
  cursor: pointer;
  text-decoration: underline;
  padding: 0;
}
.play__meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  color: #4a4436;
}
.play__badge {
  border: 1px solid var(--line);
  border-radius: 999px;
  padding: 2px 10px;
  background: #fbf6e9;
  font-weight: 600;
}
.play__as {
  margin-left: auto;
  display: flex;
  gap: 6px;
  align-items: center;
}
.play__as select {
  font: inherit;
  padding: 6px 8px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: #fffdf6;
}
.play__notice {
  padding: 10px 14px;
  border-radius: 10px;
  border: 1px solid var(--line);
  background: #fbf6e9;
}
.play__notice--error {
  border-color: #b3543f;
  background: #fbeee8;
  color: #7c3226;
}
.play__grid {
  display: grid;
  grid-template-columns: minmax(0, 5fr) minmax(0, 7fr);
  gap: 14px;
  margin-top: 12px;
}
.play__card {
  border: 1px solid var(--line);
  border-radius: 14px;
  background: #fbf6e9;
  padding: 16px 18px;
}
.play__card h2 {
  margin: 0 0 8px;
  font-family: 'Cormorant Garamond', Georgia, serif;
  font-size: 22px;
}
.play__card h3 {
  margin: 16px 0 8px;
  font-size: 15px;
}
.play__row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 10px;
}
.play__field {
  display: grid;
  gap: 6px;
  margin-top: 10px;
  font-size: 14px;
  color: #4a4436;
}
.play__field textarea {
  font: inherit;
  padding: 8px 10px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: #fffdf6;
  resize: vertical;
}
.play__queue {
  margin: 8px 0 0;
  padding-left: 20px;
  display: grid;
  gap: 10px;
}
.play__queue ul {
  margin: 4px 0 0;
  padding-left: 18px;
  font-size: 14px;
  color: #4a4436;
}
.play__sub {
  display: block;
  font-size: 13px;
  color: #6b5d43;
}
.play__cast {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 6px;
}
.play__cast li {
  display: flex;
  gap: 8px;
  align-items: baseline;
}
.play__cast span {
  color: #6b5d43;
  font-size: 14px;
}
.play__cast em {
  font-size: 12px;
  color: #1f4d3f;
}
.play__travel {
  display: grid;
  gap: 8px;
}
.play__travel label {
  display: grid;
  gap: 4px;
  font-size: 14px;
}
.play__travel select {
  font: inherit;
  padding: 8px 10px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: #fffdf6;
}
.play__feed {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 10px;
}
.play__feed li {
  border-top: 1px solid var(--line);
  padding-top: 8px;
}
.play__kind {
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: #6b5d43;
}
.play__empty {
  color: #6b5d43;
}
.play__foot {
  margin-top: 14px;
}
.play__grid + .play__card,
.play__card + .play__card,
.play__card + .play__foot {
  margin-top: 14px;
}
.play__band {
  position: relative;
  overflow: hidden;
  padding: 20px 26px;
  margin-bottom: 14px;
}
.play__ridge {
  position: absolute;
  right: 0;
  bottom: 0;
  width: 46%;
  height: 100%;
  color: #c9b58c;
  opacity: 0.5;
  pointer-events: none;
}
@media (max-width: 900px) {
  .play__grid {
    grid-template-columns: 1fr;
  }
}
</style>
