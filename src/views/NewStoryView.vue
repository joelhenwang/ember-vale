<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRoute, useRouter } from 'vue-router'
import CreateCharacterTile from '../components/newstory/CreateCharacterTile.vue'
import SearchField from '../components/ui/SearchField.vue'
import ChipGroup from '../components/ui/ChipGroup.vue'
import SortSelect from '../components/ui/SortSelect.vue'
import CastCard from '../components/newstory/CastCard.vue'
import StoryStepper from '../components/newstory/StoryStepper.vue'
import MenuButton from '../components/MenuButton.vue'
import IconArrowLeft from '../components/icons/IconArrowLeft.vue'
import IconSave from '../components/icons/IconSave.vue'
import IconArrowRight from '../components/icons/IconArrowRight.vue'
import IconPlay from '../components/icons/IconPlay.vue'
import MountainRidge from '../components/decor/MountainRidge.vue'
import PageIntro from '../components/ui/PageIntro.vue'
import { useBackend } from '../composables/useBackend'
import { usePresets, type PresetCharacter } from '../composables/usePresets'
import { resolveRecovery, useStoryDraft } from '../composables/useStoryDraft'
import { usePinnedPresets } from '../composables/usePinnedPresets'
import {
  controlledAfterCastChange,
  localDraftIssues,
  rehomeInvalidLocations,
  type NewStorySelections
} from '../game/drafting'
import { filterCast, type CastFilter } from '../game/filters'
import type { CharacterDef } from '../game/model'

const route = useRoute()
const router = useRouter()
const presets = usePresets()
const backend = useBackend()
const draftCtl = useStoryDraft()

const STEP_SLUGS = ['world', 'characters', 'play-mode', 'story', 'ai', 'review']
// current_step is the visible step: persisted on every navigation, restored
// on reload so return visits land where the draft left off.
function slugOf(n: number): string {
  return STEP_SLUGS[n - 1] ?? 'world'
}
function stepOf(slug: unknown): number {
  const at = typeof slug === 'string' ? STEP_SLUGS.indexOf(slug) : -1
  return at >= 0 ? at + 1 : 1
}
const step = ref(1)
const booted = ref(false)
const bootError = ref<string | null>(null)
const bootNotice = ref<string | null>(null)
let bootCycle = 0

const filters = reactive<CastFilter>({ search: '', category: 'all', sort: 'name' })
const categoryOptions = [
  { value: 'all', label: 'All' },
  { value: 'companions', label: 'Companions' },
  { value: 'locals', label: 'Locals' }
] as const
const sortOptions = [
  { value: 'name', label: 'Name' },
  { value: 'recent', label: 'Recent' }
]
const sortProxy = computed({
  get: (): string => filters.sort,
  set: (value: string) => {
    filters.sort = value === 'recent' ? 'recent' : 'name'
  }
})

const sel = reactive({
  worldId: '',
  worldRev: 1,
  cast: [] as {
    key: string
    presetId: string
    presetRevision: number
    name: string
    location: string
  }[],
  role: 'watcher' as 'watcher' | 'player',
  controlledKey: undefined as string | undefined,
  title: '',
  tone: 'hopeful mystery'
})

const WORLD_BY_ID = computed(() => new Map(presets.worlds.value.map((w) => [w.id, w])))
const pinned = usePinnedPresets()
const worldNotice = ref<string | null>(null)

// An older draft can pin an older world revision while the shelf only loads
// latest: the exact pinned revision supplies the places shown and
// submitted — never the newer map under an older rev. Matches on preset ID
// and revision together.
const selectedWorld = computed(() => WORLD_BY_ID.value.get(sel.worldId))
const worldPlaces = computed(() => {
  const pin = pinned.world.value
  if (pin && pin.id === sel.worldId && pin.revision === sel.worldRev) {
    return pin.places
  }
  return selectedWorld.value?.places ?? []
})

function toCharacterDef(p: PresetCharacter): CharacterDef {
  return {
    id: p.id,
    name: p.name,
    role: p.role,
    blurb: p.blurb || p.tags.join(' · ') || 'A resident of the vale.',
    bio: p.blurb,
    tags: [{ label: 'Preset' }, { label: `rev ${p.revision}` }],
    imageSlot: p.imageSlot,
    categories: [p.playerReady ? 'companions' : 'locals'],
    playerReady: p.playerReady,
    usedInStories: 0,
    updatedAt: 0
  }
}

const characterDefs = computed(() => presets.characters.value.map(toCharacterDef))
const visibleCharacters = computed(() => filterCast(characterDefs.value, filters))
const selectedIds = computed(() => new Set(sel.cast.map((c) => c.presetId)))
const modeNotice = ref<string | null>(null)

const selections = computed<NewStorySelections>(() => ({
  world: { presetId: sel.worldId, presetRevision: sel.worldRev },
  cast: sel.cast.map((c) => ({
    key: c.key,
    presetId: c.presetId,
    presetRevision: c.presetRevision,
    name: c.name,
    locationKey: c.location || undefined
  })),
  mode:
    sel.role === 'player'
      ? { role: 'player', controlledKey: sel.controlledKey }
      : { role: 'watcher' },
  title: sel.title,
  tone: sel.tone || undefined
}))

const localIssues = computed(() => localDraftIssues(selections.value))
const canContinue = computed(() => {
  if (step.value === 1) return !!sel.worldId
  if (step.value === 2) return sel.cast.length > 0
  if (step.value === 3) return sel.role === 'watcher' || !!sel.controlledKey
  if (step.value === 4) return sel.title.trim().length > 0
  return true
})

function chooseWorld(world: { id: string; revision: number }): void {
  sel.worldId = world.id
  sel.worldRev = world.revision
}

function castKeyFor(presetId: string, index: number): string {
  const base =
    presetId === presets.characters.value.find((c) => c.id === presetId)?.id
      ? (presets.characters.value.find((c) => c.id === presetId)?.name ?? `cast-${index}`)
      : `cast-${index}`
  return (
    base
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-|-$/g, '') || `cast-${index}`
  )
}

function defaultLocation(presetId: string): string {
  const preset = presets.characters.value.find((c) => c.id === presetId)
  if (preset?.startKey && worldPlaces.value.some((p) => p.key === preset.startKey)) {
    return preset.startKey
  }
  return worldPlaces.value[0]?.key ?? ''
}

async function ensurePinned(): Promise<void> {
  const latest = selectedWorld.value
  if (!latest || sel.worldRev === latest.revision) {
    pinned.clearWorld()
    return
  }
  const wid = sel.worldId
  const rev = sel.worldRev
  await pinned.loadWorld(wid, rev, () => sel.worldId === wid && sel.worldRev === rev)
}

async function prefetchCharRevs(): Promise<void> {
  for (const member of sel.cast) {
    const latest = presets.characters.value.find((c) => c.id === member.presetId)
    if (latest && member.presetRevision < latest.revision) {
      await pinned.loadCharacter(member.presetId, member.presetRevision, latest.revision)
    }
  }
}

function pinnedCharName(member: {
  presetId: string
  presetRevision: number
  name: string
}): string {
  return pinned.characterName(member.presetId, member.presetRevision, member.name)
}

const controlledDisplay = computed(() => {
  const member = sel.cast.find((c) => c.key === sel.controlledKey)
  return member ? pinnedCharName(member) : '—'
})

const locationIssues = computed(() => {
  const valid = new Set(worldPlaces.value.map((p) => p.key))
  return sel.cast
    .filter((m) => m.location && !valid.has(m.location))
    .map((m) => `${pinnedCharName(m)} starts at “${m.location}”, which this map no longer has.`)
})

function toggleCast(def: CharacterDef): void {
  const at = sel.cast.findIndex((c) => c.presetId === def.id)
  if (at >= 0) {
    sel.cast.splice(at, 1)
    const kept = controlledAfterCastChange(
      sel.cast.map((c) => c.key),
      sel.controlledKey
    )
    if (kept !== sel.controlledKey) {
      sel.controlledKey = kept
      modeNotice.value = 'The controlled character left the cast — pick another to play.'
    }
    return
  }
  const preset = presets.characters.value.find((c) => c.id === def.id)
  if (!preset || sel.cast.length >= 6) return
  const key = castKeyFor(preset.id, sel.cast.length + 1)
  sel.cast.push({
    key,
    presetId: preset.id,
    presetRevision: preset.revision,
    name: preset.name,
    location: defaultLocation(preset.id)
  })
  if (sel.role === 'player' && !sel.controlledKey && preset.playerReady) {
    sel.controlledKey = key
  }
}

function hydrate(payload: Record<string, unknown>): void {
  const world = (payload['world'] ?? {}) as Record<string, unknown>
  if (typeof world['preset_id'] === 'string') sel.worldId = world['preset_id']
  if (typeof world['preset_revision'] === 'number') sel.worldRev = world['preset_revision']
  const cast = payload['cast']
  if (Array.isArray(cast)) {
    sel.cast = cast
      .filter((m): m is Record<string, unknown> => typeof m === 'object' && m !== null)
      .map((m, i) => ({
        key: typeof m['instance_key'] === 'string' ? m['instance_key'] : `cast-${i + 1}`,
        presetId: typeof m['preset_id'] === 'string' ? m['preset_id'] : '',
        presetRevision: typeof m['preset_revision'] === 'number' ? m['preset_revision'] : 1,
        name: typeof m['name'] === 'string' ? m['name'] : `Cast ${i + 1}`,
        location: typeof m['location_key'] === 'string' ? m['location_key'] : ''
      }))
  }
  const mode = (payload['mode'] ?? {}) as Record<string, unknown>
  sel.role = mode['role'] === 'player' ? 'player' : 'watcher'
  sel.controlledKey =
    typeof mode['controlled_cast_key'] === 'string' ? mode['controlled_cast_key'] : undefined
  const story = (payload['story'] ?? {}) as Record<string, unknown>
  if (typeof story['title'] === 'string') sel.title = story['title']
  if (typeof story['tone'] === 'string') sel.tone = story['tone']
}

const dirty = computed(
  () =>
    booted.value &&
    draftCtl.draft.value !== null &&
    !draftCtl.isAcked(selections.value, slugOf(step.value))
)

function beforeUnloadGuard(event: BeforeUnloadEvent): void {
  event.preventDefault()
}

watch(dirty, (isDirty) => {
  if (isDirty || draftCtl.saveState.value === 'failed') {
    window.addEventListener('beforeunload', beforeUnloadGuard)
  } else {
    window.removeEventListener('beforeunload', beforeUnloadGuard)
  }
})

watch(
  () => draftCtl.saveState.value,
  (state) => {
    if (state === 'failed' || dirty.value) {
      window.addEventListener('beforeunload', beforeUnloadGuard)
    } else {
      window.removeEventListener('beforeunload', beforeUnloadGuard)
    }
  }
)

onUnmounted(() => {
  window.removeEventListener('beforeunload', beforeUnloadGuard)
  // Leaving invalidates this controller's lifecycle: an outstanding create
  // may still reconcile its draft's receipt, but it can no longer redirect
  // this departed view.
  draftCtl.dispose()
})

function applyRecoverySelections(s: NewStorySelections): void {
  sel.worldId = s.world.presetId
  sel.worldRev = s.world.presetRevision
  sel.cast = s.cast.map((m) => ({
    key: m.key,
    presetId: m.presetId,
    presetRevision: m.presetRevision,
    name: m.name,
    location: m.locationKey ?? ''
  }))
  sel.role = s.mode.role === 'player' ? 'player' : 'watcher'
  sel.controlledKey = s.mode.controlledKey
  sel.title = s.title
  sel.tone = s.tone ?? 'hopeful mystery'
}

async function prefillQuickStart(): Promise<void> {
  const emberVale =
    presets.worlds.value.find((w) => w.name === 'Ember Vale') ?? presets.worlds.value[0]
  if (emberVale) {
    sel.worldId = emberVale.id
    sel.worldRev = emberVale.revision
  }
  const starters = ['Wren', 'Ash']
  sel.cast = presets.characters.value
    .filter((c) => starters.includes(c.name))
    .map((c, i) => ({
      key: starters[i].toLowerCase(),
      presetId: c.id,
      presetRevision: c.revision,
      name: c.name,
      location: c.startKey ?? ''
    }))
  sel.role = 'watcher'
  sel.controlledKey = undefined
  sel.title = 'A Morning in Ember Vale'
  // Quick Start lands on Review with everything filled in — and persists.
  // The result is checked: a failed save must not claim durability.
  step.value = 6
  const saved = await persist()
  bootNotice.value = saved
    ? 'Quick Start filled in Ember Vale with Wren and Ash — review and begin, or step back to change anything.'
    : 'Quick Start filled in Ember Vale with Wren and Ash, but the save failed — your choices are kept here, not yet on the server. Retry the save before leaving.'
}

async function boot(draftOverride?: string): Promise<void> {
  bootCycle += 1
  const seen = bootCycle
  booted.value = false
  bootError.value = null
  bootNotice.value = null
  worldNotice.value = null
  pinned.clearWorld()
  await presets.load()
  if (seen !== bootCycle) return
  if (presets.error.value) {
    bootError.value = presets.error.value
    return
  }
  const emberVale =
    presets.worlds.value.find((w) => w.name === 'Ember Vale') ?? presets.worlds.value[0]
  const queryDraft =
    draftOverride ?? (typeof route.query.draft === 'string' ? route.query.draft : null)
  try {
    if (queryDraft) {
      await draftCtl.openExisting(queryDraft)
    } else if (recalledId()) {
      try {
        await draftCtl.openExisting(recalledId() as string)
      } catch {
        await startFresh()
      }
    } else {
      await startFresh()
    }
  } catch {
    if (seen !== bootCycle) return
    bootError.value = draftCtl.notice.value ?? 'could not start a draft'
    return
  }
  if (seen !== bootCycle) return
  const opened = draftCtl.draft.value
  if (!opened) {
    bootError.value = 'could not start a draft'
    return
  }
  // A completed draft already has a story: lead to it instead of offering
  // a second creation from the same draft.
  if (opened.created_world_id) {
    await router.replace({
      name: 'story-play',
      params: { storyId: opened.created_world_id }
    })
    return
  }
  hydrate(opened.payload as Record<string, unknown>)
  step.value = stepOf(opened.current_step)
  // A stored recovery holds edits the server may not have. Timestamps
  // cannot decide that — the server can commit an older save after the
  // snapshot was taken — so arbitration is by version and content: restore
  // outstanding local edits, surface a conflict when the server moved
  // underneath them, and clear when the server already holds them.
  const recovery = draftCtl.readRecovery(opened.id)
  if (recovery) {
    const decision = resolveRecovery(opened.payload, opened.version, recovery)
    if (decision === 'covered') {
      draftCtl.clearRecovery(opened.id)
    } else {
      applyRecoverySelections(recovery.selections)
      step.value = stepOf(recovery.step)
      bootNotice.value =
        decision === 'conflict'
          ? 'The server changed since these locally kept choices were made — review them carefully before saving.'
          : 'Restored choices kept locally on this device — review them and save before leaving.'
    }
  }
  await ensurePinned()
  if (seen !== bootCycle) return
  await prefetchCharRevs()
  if (!queryDraft && route.query.quickstart !== undefined) await prefillQuickStart()
  if (!sel.worldId && emberVale) {
    sel.worldId = emberVale.id
    sel.worldRev = emberVale.revision
    await persist()
  }
  if (seen !== bootCycle) return
  booted.value = true
  void backend.refresh()
}

function recalledId(): string | null {
  return draftCtl.recalledDraftId()
}

async function startFresh(): Promise<void> {
  const emberVale =
    presets.worlds.value.find((w) => w.name === 'Ember Vale') ?? presets.worlds.value[0]
  sel.worldId = emberVale?.id ?? ''
  sel.worldRev = emberVale?.revision ?? 1
  await draftCtl.openNew(
    {
      world: { presetId: sel.worldId, presetRevision: sel.worldRev },
      cast: [],
      mode: { role: 'watcher' },
      title: '',
      tone: undefined
    },
    'world'
  )
  await router.replace({ query: { ...route.query, draft: draftCtl.draft.value?.id } })
}

function navBusy(): boolean {
  return draftCtl.busy.value || draftCtl.creating.value
}

async function persist(): Promise<boolean> {
  if (!draftCtl.draft.value) return false
  const ok = await draftCtl.save(selections.value, slugOf(step.value))
  // Review displays server validation: re-check after a successful save so
  // fixed issues clear instead of lingering from an earlier draft state.
  if (ok && step.value === 6) await draftCtl.validate()
  return ok
}

async function go(n: number): Promise<void> {
  if (navBusy()) return
  step.value = n
  await persist()
}

async function next(): Promise<void> {
  if (!canContinue.value || navBusy()) return
  if (step.value === 6) {
    await create()
    return
  }
  step.value += 1
  await persist()
}

async function back(): Promise<void> {
  if (navBusy()) return
  step.value = Math.max(1, step.value - 1)
  await persist()
}

async function create(): Promise<void> {
  const targetId = draftCtl.draft.value?.id
  if (!targetId || draftCtl.creating.value) return
  // The workflow is owned by the draft mounted here: a late completion
  // after a draft switch or after leaving the wizard navigates nowhere and
  // touches no other draft.
  const worldId = await draftCtl.createWorkflow(selections.value, slugOf(step.value))
  if (!worldId) return
  if (router.currentRoute.value.name !== 'new-story') return
  if (draftCtl.draft.value?.id !== targetId) {
    draftCtl.notice.value =
      'The previous draft finished creating — find its story on the Stories shelf.'
    return
  }
  await router.push({ name: 'story-play', params: { storyId: worldId } })
}

/**
 * In-app navigation does not fire beforeunload, so a dirty draft snapshots
 * its latest selections into its own recovery slot before leaving. Clean
 * navigation stays immediate; nothing here blocks the route.
 */
function snapshotForLeave(): void {
  const current = draftCtl.draft.value
  if (!current) return
  if (dirty.value || draftCtl.saveState.value === 'failed') {
    draftCtl.storeRecovery(current.id, selections.value, slugOf(step.value))
  }
}

onBeforeRouteLeave(() => {
  snapshotForLeave()
})

onBeforeRouteUpdate((to) => {
  snapshotForLeave()
  const next = typeof to.query.draft === 'string' ? to.query.draft : null
  if (next && next !== draftCtl.draft.value?.id && booted.value) {
    void boot(next)
  }
})

// The user changing worlds adopts the latest revision deliberately:
// pinned content is dropped, starting places absent from the new map are
// reset (and named), and the change persists.
watch([() => sel.worldId, () => sel.worldRev], async ([wid, rev], [prevId]) => {
  if (!booted.value) return
  if (wid !== prevId) {
    const latest = WORLD_BY_ID.value.get(wid)
    if (latest && rev !== latest.revision) {
      sel.worldRev = latest.revision
    }
    pinned.clearWorld()
    const reset = rehomeInvalidLocations(
      sel.cast,
      new Set(worldPlaces.value.map((p) => p.key)),
      (presetId) => defaultLocation(presetId)
    )
    worldNotice.value =
      reset > 0 ? `New world, new map — ${reset} starting place(s) were reset.` : null
    await persist()
  }
  await ensurePinned()
})

// Resolve older pinned character revisions for display as the cast changes;
// latest revisions need no fetch and stay correct for browsing.
watch(
  () => sel.cast.map((m) => `${m.presetId}@${m.presetRevision}`).join(','),
  () => {
    if (booted.value) void prefetchCharRevs()
  }
)

watch(
  () => sel.role,
  (role) => {
    if (role === 'watcher') {
      sel.controlledKey = undefined
      modeNotice.value = null
    } else if (!sel.controlledKey) {
      const first = sel.cast[0]?.key
      sel.controlledKey = first
      modeNotice.value = first ? null : 'Add cast members first, then choose who to play.'
    }
  }
)

watch(step, (next) => {
  if (next === 6) void draftCtl.validate()
})

onMounted(() => {
  void boot()
})
</script>

<template>
  <main class="nsv">
    <section class="nsv__band ev-card">
      <MountainRidge class="nsv__ridge" />
      <PageIntro
        title="Shape your next tale"
        sub="Your draft saves to the library as you go — leaving and coming back keeps every choice." />
    </section>
    <div v-if="bootError" class="nsv__state" role="alert">
      <p class="nsv__state-title">The library is unreachable</p>
      <p class="nsv__state-body">{{ bootError }} — check the backend and reload.</p>
    </div>
    <template v-else-if="booted">
      <StoryStepper :current="step" @go="go" />
      <p v-if="bootNotice" class="nsv__notice" role="status">{{ bootNotice }}</p>
      <p v-if="worldNotice" class="nsv__notice" role="status">{{ worldNotice }}</p>
      <p v-if="!draftCtl.storageOk.value" class="nsv__notice" role="alert">
        Browser storage is unavailable — your choices are kept in this tab only. Save successfully
        before leaving, or they will be lost on reload.
      </p>
      <p v-if="draftCtl.notice.value" class="nsv__notice" role="status">
        {{ draftCtl.notice.value }}
      </p>
      <p v-if="pinned.world.value" class="nsv__notice" role="status">
        This draft pins {{ pinned.world.value.name }} rev {{ pinned.world.value.revision }} —
        showing that revision's places, not the newer library map.
      </p>
      <p v-if="pinned.worldError.value" class="nsv__issues" role="alert">
        {{ pinned.worldError.value }} Places below are the current library map and cannot be
        submitted with this draft — pick the current world revision or retry.
      </p>

      <section v-if="step === 1" class="nsv__panel" aria-label="Choose a world">
        <h2 class="nsv__h">Where does the story begin?</h2>
        <ul class="nsv__worlds">
          <li v-for="world in presets.worlds.value" :key="world.id">
            <button
              type="button"
              class="nsv__world"
              :class="{ 'nsv__world--on': sel.worldId === world.id }"
              :aria-pressed="sel.worldId === world.id"
              @click="chooseWorld(world)">
              <span class="nsv__world-name">{{ world.name }}</span>
              <span class="nsv__world-rev">Preset rev {{ world.revision }}</span>
              <span class="nsv__world-desc">{{ world.description }}</span>
              <span class="nsv__world-places">{{
                world.places.map((p) => p.name).join(' · ')
              }}</span>
            </button>
          </li>
        </ul>
      </section>

      <section v-if="step === 2" class="nsv__panel" aria-label="Choose the cast">
        <div class="cast__layout">
          <div class="cast__main">
            <div class="cast__toolbar">
              <SearchField v-model="filters.search" />
              <ChipGroup v-model="filters.category" :options="categoryOptions" />
              <SortSelect v-model="sortProxy" :options="sortOptions" />
            </div>
            <div class="cast__grid">
              <CastCard
                v-for="def in visibleCharacters"
                :key="def.id"
                :character="def"
                :selected="selectedIds.has(def.id)"
                @toggle="toggleCast(def)" />
              <CreateCharacterTile />
            </div>
            <p class="nsv__hint">Only saved library presets can join a real story.</p>
          </div>
          <aside class="sel" aria-label="Selected cast">
            <div class="sel__head">
              <h2 class="sel__title">Selected</h2>
              <span class="sel__count">{{ sel.cast.length }} of 6 max</span>
            </div>
            <p v-if="!sel.cast.length" class="sel__empty">No one yet — pick from the library.</p>
            <ul v-else class="sel__list">
              <li v-for="member in sel.cast" :key="member.key" class="sel__row">
                <div class="sel__who">
                  <strong>{{ pinnedCharName(member) }}</strong>
                  <span class="sel__rev">preset rev {{ member.presetRevision }}</span>
                </div>
                <label class="sel__place">
                  Starts at
                  <select v-model="member.location" :disabled="!!pinned.worldError.value">
                    <option v-for="place in worldPlaces" :key="place.key" :value="place.key">
                      {{ place.name }}
                    </option>
                  </select>
                </label>
                <button
                  type="button"
                  class="sel__remove"
                  @click="
                    toggleCast(
                      characterDefs.find((d) => d.id === member.presetId) ?? characterDefs[0]
                    )
                  ">
                  Remove
                </button>
              </li>
            </ul>
          </aside>
        </div>
      </section>

      <section v-if="step === 3" class="nsv__panel" aria-label="Choose how to play">
        <h2 class="nsv__h">How do you want to play?</h2>
        <div class="nsv__modes">
          <button
            type="button"
            class="nsv__world"
            :class="{ 'nsv__world--on': sel.role === 'watcher' }"
            :aria-pressed="sel.role === 'watcher'"
            @click="sel.role = 'watcher'">
            <span class="nsv__world-name">Observer</span>
            <span class="nsv__world-desc"
              >Watch the vale unfold and guide the story between beats.</span
            >
          </button>
          <button
            type="button"
            class="nsv__world"
            :class="{ 'nsv__world--on': sel.role === 'player' }"
            :aria-pressed="sel.role === 'player'"
            @click="sel.role = 'player'">
            <span class="nsv__world-name">Player</span>
            <span class="nsv__world-desc"
              >Step into one character's shoes and decide their actions.</span
            >
          </button>
        </div>
        <label v-if="sel.role === 'player'" class="nsv__field">
          Play as
          <select v-model="sel.controlledKey">
            <option v-for="member in sel.cast" :key="member.key" :value="member.key">
              {{ pinnedCharName(member) }}
            </option>
          </select>
        </label>
        <p v-if="modeNotice" class="nsv__notice" role="status">{{ modeNotice }}</p>
      </section>

      <section v-if="step === 4" class="nsv__panel" aria-label="Name the story">
        <h2 class="nsv__h">What is this story called?</h2>
        <label class="nsv__field">
          Title
          <input
            v-model="sel.title"
            type="text"
            maxlength="128"
            placeholder="A Morning in Ember Vale" />
        </label>
        <label class="nsv__field">
          Tone
          <input v-model="sel.tone" type="text" maxlength="128" placeholder="hopeful mystery" />
        </label>
      </section>

      <section v-if="step === 5" class="nsv__panel" aria-label="Story art and model">
        <h2 class="nsv__h">Art and telling</h2>
        <p class="nsv__body">
          Stories open with curated starter art. Image generation arrives in a later milestone.
        </p>
        <p v-if="backend.status.value.modelProfile" class="nsv__notice" role="status">
          Development model active ({{ backend.status.value.modelProfile }}) — beats are
          deterministic stand-ins, not live provider prose.
        </p>
        <p v-else class="nsv__notice" role="status">
          Model profile unknown — beats will say what they used.
        </p>
      </section>

      <section v-if="step === 6" class="nsv__panel" aria-label="Review and create">
        <h2 class="nsv__h">Ready to begin?</h2>
        <dl class="nsv__review">
          <div>
            <dt>World</dt>
            <dd>{{ selectedWorld?.name ?? sel.worldId }} (rev {{ sel.worldRev }})</dd>
          </div>
          <div>
            <dt>Cast</dt>
            <dd>
              {{
                sel.cast.map((c) => `${pinnedCharName(c)} (rev ${c.presetRevision})`).join(', ') ||
                'None'
              }}
            </dd>
          </div>
          <div>
            <dt>Mode</dt>
            <dd>
              {{ sel.role === 'player' ? `Player as ${controlledDisplay}` : 'Observer' }}
            </dd>
          </div>
          <div>
            <dt>Title</dt>
            <dd>{{ sel.title || 'Untitled' }}</dd>
          </div>
        </dl>
        <ul v-if="localIssues.length" class="nsv__issues" role="alert">
          <li v-for="issue in localIssues" :key="issue">{{ issue }}</li>
        </ul>
        <ul v-if="draftCtl.issues.value.length" class="nsv__issues" role="alert">
          <li v-for="issue in draftCtl.issues.value" :key="issue">{{ issue }}</li>
        </ul>
        <ul v-if="locationIssues.length" class="nsv__issues" role="alert">
          <li v-for="issue in locationIssues" :key="issue">{{ issue }}</li>
        </ul>
        <p v-if="draftCtl.createError.value" class="nsv__notice" role="alert">
          {{ draftCtl.createError.value }}
        </p>
        <p v-if="draftCtl.ambiguous.value" class="nsv__notice" role="status">
          The last create may already have completed — pressing Begin again replays the same
          submission, never a duplicate story.
        </p>
      </section>

      <footer class="nsv__footer">
        <MenuButton
          v-if="step > 1"
          variant="outline"
          :icon="IconArrowLeft"
          :disabled="draftCtl.busy.value || draftCtl.creating.value"
          @click="back()"
          >Back</MenuButton
        >
        <MenuButton
          variant="outline"
          :icon="IconSave"
          :disabled="draftCtl.busy.value"
          @click="persist()">
          {{
            draftCtl.busy.value
              ? 'Saving…'
              : draftCtl.saveState.value === 'failed'
                ? 'Retry save'
                : 'Save draft'
          }}
        </MenuButton>
        <span class="nsv__draftstate">{{
          !draftCtl.draft.value
            ? 'No draft yet'
            : draftCtl.saveState.value === 'failed'
              ? `Draft rev ${draftCtl.draft.value.version} · save failed — choices kept locally`
              : dirty
                ? `Draft rev ${draftCtl.draft.value.version} · unsaved changes`
                : `Draft rev ${draftCtl.draft.value.version} · saved`
        }}</span>
        <MenuButton
          v-if="step < 6"
          :icon="IconArrowRight"
          :disabled="!canContinue || draftCtl.busy.value || draftCtl.creating.value"
          @click="next()">
          Continue
        </MenuButton>
        <MenuButton
          v-else
          :icon="IconPlay"
          :disabled="
            draftCtl.creating.value ||
            draftCtl.busy.value ||
            localIssues.length > 0 ||
            locationIssues.length > 0 ||
            !!pinned.worldError.value
          "
          @click="create()">
          {{ draftCtl.creating.value ? 'Creating…' : 'Begin the story' }}
        </MenuButton>
      </footer>
    </template>
    <div v-else class="nsv__state" role="status">
      <p class="nsv__state-title">Opening the library…</p>
    </div>
  </main>
</template>

<style scoped>
.nsv {
  max-width: 1440px;
  margin: 0 auto;
  padding: 14px 16px 40px;
}
.nsv__panel {
  margin-top: 14px;
  padding: 18px 20px 20px;
  border: 1px solid var(--line);
  border-radius: 14px;
  background: #fbf6e9;
}
.nsv__h {
  margin: 0;
  font-family: var(--font-display);
  font-size: 26px;
  font-weight: 600;
  color: #26200f;
}
.nsv__state {
  margin-top: 14px;
  padding: 18px;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: #fbf6e9;
}
.nsv__state-title {
  margin: 0;
  font-weight: 600;
}
.nsv__state-body {
  margin: 6px 0 0;
  color: #4a4436;
}
.nsv__notice {
  margin-top: 12px;
  padding: 10px 14px;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: #fffdf6;
  color: #4a4436;
}
.nsv__footer {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 14px;
  padding: 12px 18px;
  border: 1px solid var(--line);
  border-radius: 14px;
  background: #fbf6e9;
}
.cast__layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 340px;
  gap: 14px;
  align-items: start;
}
.cast__toolbar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 14px;
}
.cast__grid {
  margin-top: 16px;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(206px, 1fr));
  gap: 16px;
}
.sel {
  border: 1px solid var(--line);
  border-radius: 12px;
  background: linear-gradient(180deg, #fcf7ea, #f8f1df);
  padding: 14px 16px;
}
.sel__head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
}
.sel__title {
  margin: 0;
  font-family: var(--font-display);
  font-size: 22px;
}
.sel__count {
  font-size: 13px;
  color: #6b5d43;
}
.sel__empty {
  color: #6b5d43;
  font-size: 14px;
}
.sel__list {
  list-style: none;
  margin: 10px 0 0;
  padding: 0;
  display: grid;
  gap: 8px;
}
.nsv__worlds {
  list-style: none;
  margin: 12px 0 0;
  padding: 0;
  display: grid;
  gap: 10px;
}
@media (max-width: 1100px) {
  .cast__layout {
    grid-template-columns: 1fr;
  }
}
.nsv__world {
  display: grid;
  gap: 2px;
  width: 100%;
  text-align: left;
  padding: 12px 14px;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: linear-gradient(180deg, #fcf7ea, #f8f1df);
  cursor: pointer;
  font: inherit;
  color: inherit;
}
.nsv__world--on {
  border-color: #1f4d3f;
  box-shadow: 0 0 0 2px rgba(31, 77, 63, 0.25);
}
.nsv__world-name {
  font-family: 'Cormorant Garamond', Georgia, serif;
  font-size: 20px;
  font-weight: 600;
}
.nsv__world-rev {
  font-size: 12px;
  color: #6b5d43;
}
.nsv__world-desc {
  font-size: 14px;
  color: #4a4436;
}
.nsv__world-places {
  font-size: 13px;
  color: #6b5d43;
}
.nsv__band {
  position: relative;
  overflow: hidden;
  padding: 20px 26px;
  margin-bottom: 14px;
}
.nsv__ridge {
  position: absolute;
  right: 0;
  bottom: 0;
  width: 46%;
  height: 100%;
  color: #c9b58c;
  opacity: 0.5;
  pointer-events: none;
}
.nsv__modes {
  display: grid;
  gap: 10px;
  margin-top: 12px;
}
.nsv__field {
  display: grid;
  gap: 6px;
  margin-top: 12px;
  font-weight: 600;
}
.nsv__field input,
.nsv__field select,
.sel__place select {
  font: inherit;
  font-weight: 400;
  padding: 8px 10px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: #fffdf6;
  color: inherit;
  max-width: 420px;
}
.nsv__body {
  color: #4a4436;
}
.nsv__hint {
  margin-top: 12px;
  font-size: 13px;
  color: #6b5d43;
}
.nsv__review {
  display: grid;
  gap: 8px;
  margin: 12px 0 0;
}
.nsv__review > div {
  display: grid;
  grid-template-columns: 90px 1fr;
  gap: 8px;
}
.nsv__review dt {
  font-weight: 600;
  color: #6b5d43;
}
.nsv__review dd {
  margin: 0;
}
.nsv__issues {
  margin: 12px 0 0;
  padding: 10px 14px;
  border: 1px solid #b3543f;
  border-radius: 10px;
  background: #fbeee8;
  color: #7c3226;
  list-style: disc inside;
}
.nsv__draftstate {
  margin-left: auto;
  margin-right: 8px;
  font-size: 13px;
  color: #6b5d43;
}
.sel__row {
  display: grid;
  gap: 6px;
  padding: 10px 12px;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: linear-gradient(180deg, #fcf7ea, #f8f1df);
}
.sel__who {
  display: flex;
  align-items: baseline;
  gap: 8px;
}
.sel__rev {
  font-size: 12px;
  color: #6b5d43;
}
.sel__place {
  display: grid;
  gap: 4px;
  font-size: 13px;
}
.sel__remove {
  justify-self: start;
  font: inherit;
  font-size: 13px;
  color: #7c3226;
  background: none;
  border: none;
  cursor: pointer;
  text-decoration: underline;
  padding: 0;
}
</style>
