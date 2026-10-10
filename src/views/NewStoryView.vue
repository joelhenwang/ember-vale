<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { storyLocation } from '../game/storyRoute'
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRoute, useRouter } from 'vue-router'
import CreateCharacterTile from '../components/newstory/CreateCharacterTile.vue'
import SearchField from '../components/ui/SearchField.vue'
import FramedImage from '../components/ui/FramedImage.vue'
import ChipGroup from '../components/ui/ChipGroup.vue'
import SortSelect from '../components/ui/SortSelect.vue'
import CastCard from '../components/newstory/CastCard.vue'
import InlineStepper from '../components/studio/InlineStepper.vue'
import CollapseBox from '../components/studio/CollapseBox.vue'
import StoryImage from '../components/StoryImage.vue'
import IconCheck from '../components/icons/IconCheck.vue'
import IconBook from '../components/icons/IconBook.vue'
import IconEmblem from '../components/icons/IconEmblem.vue'
import { DEFAULT_HERO, HERO_CLASSES, HERO_RACES, heroLine } from '../game/party'
import IconPlus from '../components/icons/IconPlus.vue'
import IconEye from '../components/icons/IconEye.vue'
import IconUser from '../components/icons/IconUser.vue'
import IconUsers from '../components/icons/IconUsers.vue'
import IconGlobe from '../components/icons/IconGlobe.vue'
import IconFeather from '../components/icons/IconFeather.vue'
import IconSparkle from '../components/icons/IconSparkle.vue'
import MenuButton from '../components/MenuButton.vue'
import IconArrowLeft from '../components/icons/IconArrowLeft.vue'
import IconSave from '../components/icons/IconSave.vue'
import IconPlay from '../components/icons/IconPlay.vue'
import MountainRidge from '../components/decor/MountainRidge.vue'
import EmberField from '../components/decor/EmberField.vue'
import { burst } from '../composables/useEffects'
import { useBackend } from '../composables/useBackend'
import {
  applyAdoption,
  MAX_CAST,
  offerTargetsDraft,
  pinsEqual,
  planAdoption,
  parseAdoptionOffer,
  restoreSnapshot,
  snapshotPins,
  type AdoptionOffer,
  type PinSnapshot
} from '../game/adoption'
import { usePresets, type PresetCharacter } from '../composables/usePresets'
import { planBootRecovery, useStoryDraft } from '../composables/useStoryDraft'
import { usePinnedPresets } from '../composables/usePinnedPresets'
import {
  controlledAfterCastChange,
  localDraftIssues,
  rehomeInvalidLocations,
  type NewStorySelections
} from '../game/drafting'
import { filterCast, type CastFilter } from '../game/filters'
import { WIZARD_STEP_LABELS, persistStepSlug, stepFromSlug } from '../game/wizardSteps'
import {
  NEW_STORY_HEADS,
  TONE_PRESETS,
  placesLine,
  searchWorlds,
  namesLine,
  storytellerName,
  toneLabel,
  watchedParty
} from '../game/newStory'
import type { CharacterDef } from '../game/model'
import { useStorytellerPin } from '../composables/useStorytellerPin'
import { describeEnvironment } from '../composables/useStoryProvider'

const route = useRoute()
const router = useRouter()
const presets = usePresets()
const backend = useBackend()
const draftCtl = useStoryDraft()

// current_step is the persisted step identifier: saved on every
// navigation, restored on reload so return visits land where the draft
// left off. Labels render in the stepper; only backend-accepted
// identifiers persist (see game/wizardSteps).
const slugOf = persistStepSlug
const stepOf = stepFromSlug
const step = ref(1)
const booted = ref(false)
const bootError = ref<string | null>(null)
const bootNotice = ref<string | null>(null)
/** Independent server state preserved while a recovery conflict awaits choice. */
const serverAlternative = ref<{ payload: Record<string, unknown>; step: number } | null>(null)
/**
 * Nested return from a studio publish or first-preset creation: adopting
 * is deliberate, never automatic. The offer pins the exact offered
 * revision, not the head, and belongs to exactly one story draft.
 * `rollback` snapshots the pins at accept time so dismissing a failed
 * accept restores them (including removing an added cast member).
 */
interface PendingAdoption {
  offer: AdoptionOffer
  /** Pins before the accept attempt: the restoration target on dismiss. */
  rollback: PinSnapshot | null
  /** Pins the accept attempt produced: dismiss restores only while live still matches these. */
  attempted: PinSnapshot | null
}
const adoptOffer = ref<PendingAdoption | null>(null)
/** True while acceptAdoption drives pin changes itself (watcher stands down). */
let adoptingWorld = false
let bootCycle = 0

function keepLocalRecovery(): void {
  // The kept choices stay applied; their entry still clears only via a
  // covering save. The server alternative is dropped with the choice.
  serverAlternative.value = null
  bootNotice.value =
    'Restored choices kept locally on this device — review them and save before leaving.'
}

function useServerVersion(): void {
  const alt = serverAlternative.value
  const opened = draftCtl.draft.value
  if (!alt || !opened) return
  hydrate(alt.payload)
  step.value = alt.step
  draftCtl.clearRecovery(opened.id)
  serverAlternative.value = null
  bootNotice.value = null
}

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
  /** A story with fights: played, your hero's people and calling; watched, a party of the cast. */
  fights: false,
  race: DEFAULT_HERO.race,
  characterClass: DEFAULT_HERO.characterClass,
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
    portrait: p.portrait,
    categories: [p.playerReady ? 'companions' : 'locals'],
    playerReady: p.playerReady,
    usedInStories: null,
    revision: p.revision,
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
      ? {
          role: 'player',
          controlledKey: sel.controlledKey,
          ...(sel.fights
            ? { adventure: { race: sel.race, characterClass: sel.characterClass } }
            : {})
        }
      : { role: 'watcher', ...(sel.fights ? { adventure: {} } : {}) },
  title: sel.title,
  tone: sel.tone || undefined,
  ...(pinCtl.pin.value ? { aiPin: pinCtl.pin.value } : {})
}))

// Storyteller pin (wizard step 5): an existing provider profile revision,
// persisted through the draft's `ai` section and executed by every beat.
// Request ownership lives in the composable: a late profile response can
// never stamp another provider's pin onto the current selection.
const pinCtl = useStorytellerPin()

// Environment honesty on the AI step: deterministic stand-ins are claimed
// only for an actually fake active profile; a live default says live.
const envNotice = computed(
  () => describeEnvironment(backend.status.value.modelProfile)?.text ?? null
)

watch(step, (next) => {
  if (next >= 5) void pinCtl.ensure()
})

const localIssues = computed(() => localDraftIssues(selections.value))
const canContinue = computed(() => {
  if (step.value === 1) return !!sel.worldId
  if (step.value === 2) return sel.cast.length > 0
  if (step.value === 3) return sel.role === 'watcher' || !!sel.controlledKey
  if (step.value === 4) return sel.title.trim().length > 0
  // A selected provider must resolve to an exact profile before leaving
  // the AI step: otherwise Begin would silently create an unpinned story.
  if (step.value === 5) return pinCtl.pinValid.value
  return true
})

function chooseWorld(world: { id: string; revision: number }): void {
  sel.worldId = world.id
  sel.worldRev = world.revision
}
/** A world picked by hand: its tick throws a few sparks. */
function pickWorld(world: { id: string; revision: number }, event: Event): void {
  const fresh = sel.worldId !== world.id
  chooseWorld(world)
  if (fresh) {
    const card = event.currentTarget as HTMLElement | null
    burst(card?.querySelector('.wcard__tick'), { count: 12, spread: 52 })
  }
}
/** A choice card (play mode, who you play) answers the click with sparks. */
function cheer(event: Event): void {
  const card = event.currentTarget as HTMLElement | null
  burst(card?.querySelector('.mode__tick, .wcard__tick'), { count: 8, spread: 38 })
}
function chooseFights(fights: boolean, event: Event): void {
  const fresh = sel.fights !== fights
  sel.fights = fights
  if (fresh) cheer(event)
}
const heroSummary = computed(() =>
  sel.role === 'player' && sel.fights ? heroLine(sel.race, sel.characterClass) : null
)
/** A watched adventure's party (the first four of the cast) and who stays out. */
const watchedPartyNames = computed(() =>
  sel.role === 'watcher' && sel.fights ? watchedParty(sel.cast.map(pinnedCharName)) : null
)
function chooseRole(role: 'watcher' | 'player', event: Event): void {
  const fresh = sel.role !== role
  sel.role = role
  if (fresh) cheer(event)
}
function choosePlayer(key: string, event: Event): void {
  const fresh = sel.controlledKey !== key
  sel.controlledKey = key
  if (fresh) cheer(event)
}

/* Steps slide the way you are going: forward from the right, back from the left. */
const stepMotion = ref<'ev-step-next' | 'ev-step-prev'>('ev-step-next')
watch(step, (now, was) => {
  stepMotion.value = now >= was ? 'ev-step-next' : 'ev-step-prev'
})

/**
 * Enter the character creation studio bound to this draft: leaving
 * snapshots unsaved choices, and creating returns here with an adoption
 * offer for revision 1. Without a draft the studio still opens, but the
 * return carries no offer.
 */
function goCreateCharacter(): void {
  const draftId = draftCtl.draft.value?.id
  void router.push({
    path: '/new-story/character/new',
    query: { ...(draftId ? { draft: draftId } : {}) }
  })
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

/* ————— what each step shows ————— */
const head = computed(() => NEW_STORY_HEADS[step.value - 1] ?? NEW_STORY_HEADS[0]!)
const SIDE_TITLES = [
  'World preview',
  'Your cast',
  'Your role in the story',
  'Story preview',
  'Your storyteller',
  'Story preview'
]
const sideTitle = computed(() => SIDE_TITLES[step.value - 1] ?? '')
const nextLabel = computed(() => WIZARD_STEP_LABELS[step.value] ?? 'Review')
const worldSearch = ref('')
const shownWorlds = computed(() => searchWorlds(presets.worlds.value, worldSearch.value))

function defOf(member: { presetId: string }): CharacterDef | undefined {
  return characterDefs.value.find((d) => d.id === member.presetId)
}
function placeName(key: string): string {
  return worldPlaces.value.find((p) => p.key === key)?.name ?? 'a place not chosen yet'
}
const playerMember = computed(() =>
  sel.role === 'player' ? sel.cast.find((c) => c.key === sel.controlledKey) : undefined
)
const playerDef = computed(() => (playerMember.value ? defOf(playerMember.value) : undefined))
/** Everyone but the character you play. */
const others = computed(() =>
  sel.cast.filter((c) => !(sel.role === 'player' && c.key === sel.controlledKey))
)

/** The app's storyteller by name ("Venice"), and whether this story picks its own. */
const appTeller = computed(() => storytellerName(backend.status.value.modelProfile))
const customTeller = ref(false)
watch(
  () => pinCtl.providerId.value,
  (id) => {
    if (id) customTeller.value = true
  },
  { immediate: true }
)
function useAppTeller(): void {
  customTeller.value = false
  pinCtl.selectProvider('')
}

/** A line of context beside the draft state. */
const footerNote = computed(() => {
  if (step.value === 1 && selectedWorld.value)
    return `${selectedWorld.value.name} · ${worldPlaces.value.length} places`
  if (step.value === 2)
    return `${sel.cast.length} ${sel.cast.length === 1 ? 'character' : 'characters'} selected`
  if (step.value >= 4 && sel.title.trim()) return sel.title.trim()
  return ''
})

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
  const adventure = mode['adventure'] as Record<string, unknown> | null | undefined
  sel.fights = !!adventure && typeof adventure === 'object'
  if (adventure && typeof adventure === 'object') {
    if (typeof adventure['race'] === 'string') sel.race = adventure['race']
    if (typeof adventure['character_class'] === 'string')
      sel.characterClass = adventure['character_class']
  }
  const story = (payload['story'] ?? {}) as Record<string, unknown>
  if (typeof story['title'] === 'string') sel.title = story['title']
  if (typeof story['tone'] === 'string') sel.tone = story['tone']
  const ai = (payload['ai'] ?? {}) as Record<string, unknown>
  if (typeof ai['profile_id'] === 'string' && ai['profile_id']) {
    pinCtl.restorePin(
      ai['profile_id'],
      typeof ai['profile_revision'] === 'number' ? ai['profile_revision'] : 1
    )
  } else {
    pinCtl.reset()
  }
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
  sel.fights = !!s.mode.adventure
  if (s.mode.adventure) {
    sel.race = s.mode.adventure.race ?? sel.race
    sel.characterClass = s.mode.adventure.characterClass ?? sel.characterClass
  }
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
    .map((c) => ({
      // Keyed by name: presets arrive in their own order, not the starters'.
      key: c.name.toLowerCase(),
      presetId: c.id,
      presetRevision: c.revision,
      name: c.name,
      location: c.startKey ?? ''
    }))
  // Quick Start puts you in the story: you play Wren, Ash is nearby.
  const playable = sel.cast.find((c) => c.key === 'wren') ?? sel.cast[0]
  sel.role = playable ? 'player' : 'watcher'
  sel.controlledKey = playable?.key
  pinCtl.reset()
  sel.title = 'A Morning in Ember Vale'
  // Quick Start lands on Review with everything filled in — and persists.
  // The result is checked: a failed save must not claim durability.
  step.value = 6
  const saved = await persist()
  bootNotice.value = saved
    ? 'Quick Start: you play Wren in Ember Vale, with Ash nearby — begin, or step back to change anything.'
    : 'Quick Start filled in Ember Vale with Wren and Ash, but the save failed — your choices are kept here, not yet on the server. Retry the save before leaving.'
}

async function openRecalled(): Promise<void> {
  if (recalledId()) {
    try {
      await draftCtl.openExisting(recalledId() as string)
    } catch {
      await startFresh()
    }
  } else {
    await startFresh()
  }
}

async function boot(
  draftOverride?: string,
  queryOverride?: Record<string, unknown>
): Promise<void> {
  bootCycle += 1
  const seen = bootCycle
  booted.value = false
  bootError.value = null
  bootNotice.value = null
  serverAlternative.value = null
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
  // A studio return carries its originating draft: boot it explicitly so
  // the offer lands on its own draft even when another flow recalled a
  // different one meanwhile. An explicit ?draft= always wins.
  const incomingAdopt = parseAdoptionOffer(
    (queryOverride ?? route.query) as Record<string, unknown>
  )
  const queryDraft =
    draftOverride ??
    (typeof route.query.draft === 'string' ? route.query.draft : null) ??
    incomingAdopt?.draftId ??
    null
  let adoptDead = false
  try {
    if (queryDraft) {
      try {
        await draftCtl.openExisting(queryDraft)
      } catch {
        if (incomingAdopt && !draftOverride && queryDraft === incomingAdopt.draftId) {
          // The originating draft no longer opens: fall back to the
          // recalled flow and drop the orphaned offer below.
          adoptDead = true
          await openRecalled()
        } else {
          throw new Error(draftCtl.notice.value ?? 'could not start a draft')
        }
      }
    } else {
      await openRecalled()
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
    const mode = (opened.payload as { mode?: { role?: string } } | null)?.mode?.role
    await router.replace(storyLocation(opened.created_world_id, mode))
    return
  }
  hydrate(opened.payload as Record<string, unknown>)
  step.value = stepOf(opened.current_step)
  // A stored recovery holds edits the server may not have. Timestamps
  // cannot decide that — the server can commit an older save after the
  // snapshot was taken — so arbitration is by version and content: restore
  // outstanding local edits, offer both versions when the server moved
  // underneath them, and clear when the server already holds them.
  const recovery = draftCtl.readRecovery(opened.id)
  const plan = planBootRecovery(
    { payload: opened.payload, version: opened.version, step: opened.current_step },
    recovery
  )
  if (plan.kind === 'covered') {
    draftCtl.clearRecovery(opened.id)
  } else if (plan.kind === 'restore') {
    applyRecoverySelections(plan.selections)
    step.value = stepOf(plan.step)
    if (plan.conflict) {
      serverAlternative.value = {
        payload: opened.payload as Record<string, unknown>,
        step: stepOf(opened.current_step)
      }
      bootNotice.value =
        'The server changed since these locally kept choices were made — your kept choices are shown. Keep them or switch to the server version, then save.'
    } else {
      bootNotice.value =
        'Restored choices kept locally on this device — review them and save before leaving.'
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
  // A studio publish returns here with an adoption offer. It presents
  // only when it belongs to the mounted draft; anything else is cleared
  // so a delayed return can never modify another wizard draft.
  if (incomingAdopt && !adoptDead && offerTargetsDraft(incomingAdopt, opened.id)) {
    adoptOffer.value = { offer: incomingAdopt, rollback: null, attempted: null }
  } else {
    // Clearing targets the live query: while booting from a pending
    // navigation the route query is stale, so leave it — the next mount
    // parses (and clears, if still foreign) against the settled URL.
    if (incomingAdopt && !queryOverride) clearAdoptQuery()
    adoptOffer.value = null
  }
  if (seen !== bootCycle) return
  booted.value = true
  void backend.refresh()
}

function clearAdoptQuery(): void {
  const next = { ...route.query }
  delete next['adopt_kind']
  delete next['adopt_preset']
  delete next['adopt_revision']
  delete next['adopt_draft']
  delete next['adopt_created']
  void router.replace({ query: next })
}

/**
 * Reconcile cast starting locations against the exact adopted world
 * revision: members whose location the new map no longer has are reset
 * to the revision's default and named, like a manual world change.
 */
async function reconcileAdoptedWorld(): Promise<void> {
  await ensurePinned()
  const reset = rehomeInvalidLocations(
    sel.cast,
    new Set(worldPlaces.value.map((p) => p.key)),
    (presetId) => defaultLocation(presetId)
  )
  worldNotice.value =
    reset > 0
      ? `Revision ${sel.worldRev} no longer has ${reset} starting place(s) — reset to the new map.`
      : null
}

async function acceptAdoption(): Promise<void> {
  const pending = adoptOffer.value
  if (!pending) return
  // A creation return may name a preset younger than this shelf: refresh
  // once so a brand-new world or character is not mistaken for unknown.
  const shelfKnows =
    pending.offer.kind === 'world'
      ? WORLD_BY_ID.value.has(pending.offer.presetId)
      : presets.characters.value.some((c) => c.id === pending.offer.presetId)
  if (!shelfKnows) await presets.load()
  const draftId = draftCtl.draft.value?.id ?? null
  const plan = planAdoption(
    pending.offer,
    selections.value,
    draftId,
    WORLD_BY_ID.value.has(pending.offer.presetId),
    presets.characters.value.some((c) => c.id === pending.offer.presetId)
  )
  if (plan.kind === 'stale-draft') {
    adoptOffer.value = null
    clearAdoptQuery()
    bootNotice.value = 'That adoption belongs to another story draft — nothing was changed.'
    return
  }
  if (plan.kind === 'unknown-target') {
    adoptOffer.value = null
    clearAdoptQuery()
    bootNotice.value =
      pending.offer.kind === 'world'
        ? 'That world is no longer on the shelf — nothing was adopted.'
        : 'That cast member is no longer in this draft — nothing was adopted.'
    return
  }
  if (plan.kind === 'cast-full') {
    // Keep the offer: removing a member and accepting again must work.
    bootNotice.value = 'The cast is full (6 max) — remove a member, then accept again.'
    return
  }
  if (pending.rollback === null) pending.rollback = snapshotPins(selections.value)
  const applied = applyAdoption(selections.value, pending.offer)
  adoptingWorld = true
  let addedName: string | null = null
  try {
    if (pending.offer.kind === 'world') {
      sel.worldId = applied.world.presetId
      sel.worldRev = applied.world.presetRevision
      await reconcileAdoptedWorld()
    } else {
      const target = sel.cast.find((c) => c.presetId === pending.offer.presetId)
      const member = applied.cast.find((m) => m.presetId === pending.offer.presetId)
      if (target && member) {
        target.presetRevision = member.presetRevision
        await prefetchCharRevs()
      } else if (plan.kind === 'apply-character-add') {
        // A created character joins the cast on explicit accept, like a
        // manual pick: keyed, named, and placed by the same rules.
        const preset = presets.characters.value.find((c) => c.id === pending.offer.presetId)
        if (preset && sel.cast.length < MAX_CAST) {
          const key = castKeyFor(preset.id, sel.cast.length + 1)
          sel.cast.push({
            key,
            presetId: preset.id,
            presetRevision: pending.offer.revision,
            name: preset.name,
            location: defaultLocation(preset.id)
          })
          addedName = preset.name
          if (sel.role === 'player' && !sel.controlledKey && preset.playerReady) {
            sel.controlledKey = key
          }
          await prefetchCharRevs()
        }
      }
    }
    // Record what this attempt produced (pins and reconciled starting
    // locations): dismissal restores the rollback only while live still
    // matches exactly this.
    pending.attempted = snapshotPins(selections.value)
    if (!(await persist())) {
      // The pins changed locally but did not persist: keep the offer
      // (and its query) so accepting again retries, and say so plainly.
      bootNotice.value =
        'Adoption could not save — your pins are unchanged on the server. Accept again to retry.'
      return
    }
  } finally {
    adoptingWorld = false
  }
  adoptOffer.value = null
  clearAdoptQuery()
  bootNotice.value =
    addedName !== null
      ? `Added ${addedName} to the cast at revision ${pending.offer.revision} — everything else in this draft is unchanged.`
      : `Adopted revision ${pending.offer.revision} — everything else in this draft is unchanged.`
}

async function dismissAdoption(): Promise<void> {
  const pending = adoptOffer.value
  if (pending?.rollback && pending.attempted && pinsEqual(pending.attempted, selections.value)) {
    // A failed accept changed the pins (and possibly reconciled
    // starting locations) but never persisted: put the originals back
    // and save the restoration. Anything the user edited themselves
    // meanwhile no longer matches the attempt, so it stands untouched.
    // The world watcher stands down while the rollback drives, so the
    // restoration persists exactly once.
    adoptingWorld = true
    try {
      // An accepted character add introduced a member the rollback
      // predates: remove it so dismissal truly restores the originals.
      for (let i = sel.cast.length - 1; i >= 0; i--) {
        if (!(sel.cast[i]!.key in pending.rollback.castRevs)) sel.cast.splice(i, 1)
      }
      restoreSnapshot(sel, pending.rollback)
      await ensurePinned()
      if (!(await persist())) {
        // The restoration is local-only: retain the offer and its
        // recovery state so dismissing again retries the save instead
        // of abandoning the pins.
        pending.attempted = snapshotPins(selections.value)
        bootNotice.value =
          'Could not save the restored pins — they are kept locally. Dismiss again to retry.'
        return
      }
    } finally {
      adoptingWorld = false
    }
  }
  adoptOffer.value = null
  clearAdoptQuery()
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
  const query: Record<string, string | string[] | null | undefined> = {
    ...route.query,
    draft: draftCtl.draft.value?.id
  }
  delete query['adopt_kind']
  delete query['adopt_preset']
  delete query['adopt_revision']
  delete query['adopt_draft']
  delete query['adopt_created']
  await router.replace({ query })
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
  // Backstop for the disabled Begin button: never create while a
  // deliberately selected provider has no resolved profile.
  if (!pinCtl.pinValid.value) {
    draftCtl.notice.value = pinCtl.pinIssue.value ?? 'Storyteller selection is not ready yet.'
    return
  }
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
  await router.push(storyLocation(worldId, sel.role))
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
    return
  }
  // A studio return onto the already-mounted route carries no draft
  // switch: present its offer when it belongs here, or boot its draft.
  if (!booted.value) return
  const incoming = parseAdoptionOffer(to.query as Record<string, unknown>)
  if (!incoming) return
  const current = draftCtl.draft.value?.id ?? null
  if (incoming.draftId === current) {
    adoptOffer.value = { offer: incoming, rollback: null, attempted: null }
  } else {
    void boot(incoming.draftId, to.query as Record<string, unknown>)
  }
})

// The user changing worlds adopts the latest revision deliberately, and an
// adopted revision change within the same world reconciles the same way:
// pinned content is dropped, starting places absent from the exact
// revision's map are reset (and named), and the change persists.
watch([() => sel.worldId, () => sel.worldRev], async ([wid, rev], [prevId, prevRev]) => {
  if (!booted.value || adoptingWorld) return
  if (wid !== prevId) {
    const latest = WORLD_BY_ID.value.get(wid)
    if (latest && rev !== latest.revision) {
      // Re-fire reconciles against the latest revision's exact map.
      sel.worldRev = latest.revision
      return
    }
    pinned.clearWorld()
  } else if (rev === prevRev) {
    await ensurePinned()
    return
  }
  await ensurePinned()
  const reset = rehomeInvalidLocations(
    sel.cast,
    new Set(worldPlaces.value.map((p) => p.key)),
    (presetId) => defaultLocation(presetId)
  )
  worldNotice.value =
    reset > 0
      ? wid !== prevId
        ? `New world, new map — ${reset} starting place(s) were reset.`
        : `Revision ${rev} no longer has ${reset} starting place(s) — reset to the new map.`
      : null
  await persist()
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
    <div v-if="bootError" class="nsv__state" role="alert">
      <p class="nsv__state-title">The library is unreachable</p>
      <p class="nsv__state-body">{{ bootError }} — check the backend and reload.</p>
    </div>
    <template v-else-if="booted">
      <!-- the step's own heading, and the steps across the page -->
      <header class="nsx__top">
        <h1 class="nsx__title">{{ head.title }}</h1>
        <p class="nsx__intro">
          {{ head.sub }}
          <span class="nsx__saves"><IconCheck :size="13" /> Your choices save as you go.</span>
        </p>
        <InlineStepper
          class="nsx__stepper"
          stretch
          :steps="[...WIZARD_STEP_LABELS]"
          :current="step"
          @go="go" />
      </header>
      <p v-if="bootNotice" class="nsv__notice" role="status">{{ bootNotice }}</p>
      <div v-if="serverAlternative" class="nsv__modes" role="group" aria-label="Recovery choice">
        <button
          type="button"
          class="nsv__world nsv__world--on"
          :aria-pressed="true"
          @click="keepLocalRecovery">
          <span class="nsv__world-name">Keep my kept choices</span>
          <span class="nsv__world-desc">Shown now — still local until you save.</span>
        </button>
        <button type="button" class="nsv__world" :aria-pressed="false" @click="useServerVersion">
          <span class="nsv__world-name">Use server version</span>
          <span class="nsv__world-desc"
            >Discard the kept choices and show what the server holds.</span
          >
        </button>
      </div>
      <div
        v-if="adoptOffer"
        class="nsv__modes"
        role="group"
        :aria-label="
          adoptOffer.offer.created ? 'Adopt created preset' : 'Adopt published revision'
        ">
        <button type="button" class="nsv__world" :aria-pressed="false" @click="acceptAdoption">
          <span class="nsv__world-name"
            >Adopt revision {{ adoptOffer.offer.revision }} ({{
              adoptOffer.offer.kind === 'world' ? 'world' : 'character'
            }})</span
          >
          <span class="nsv__world-desc"
            >Pins exactly this revision. Everything else in the draft stays as it is.</span
          >
        </button>
        <button type="button" class="nsv__world" :aria-pressed="false" @click="dismissAdoption">
          <span class="nsv__world-name">Keep current pins</span>
          <span class="nsv__world-desc">Stay on the revisions this draft already uses.</span>
        </button>
      </div>
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

      <div class="nsx__body">
        <!-- ————— the step ————— -->
        <section class="nsx__main card ev-card" :aria-label="head.title">
          <Transition :name="stepMotion">
            <div :key="step" class="nsx__step">
              <!-- 1 · world -->
              <template v-if="step === 1">
                <header class="nsx__head">
                  <h2 class="nsx__h">Your worlds</h2>
                  <span class="nsx__count">{{ presets.worlds.value.length }} worlds</span>
                  <SearchField
                    v-model="worldSearch"
                    class="nsx__search"
                    placeholder="Search worlds…" />
                  <router-link
                    class="ghost nsx__create"
                    :to="{
                      path: '/new-story/world/new',
                      query: { draft: draftCtl.draft.value?.id }
                    }">
                    <IconPlus :size="14" /> Create a world
                  </router-link>
                </header>
                <ul class="nsx__worlds">
                  <li v-for="world in shownWorlds" :key="world.id">
                    <button
                      type="button"
                      class="wcard"
                      :class="{ 'wcard--on': sel.worldId === world.id }"
                      :aria-pressed="sel.worldId === world.id"
                      @click="pickWorld(world, $event)">
                      <span class="wcard__pic">
                        <FramedImage
                          v-if="world.cover"
                          :src="world.cover.src"
                          :frame="world.cover.frame"
                          alt="" />
                        <span v-else class="wcard__nopic">
                          <MountainRidge class="wcard__ridge" />
                          <span>No picture yet</span>
                        </span>
                        <span class="wcard__tick" aria-hidden="true">
                          <IconCheck v-if="sel.worldId === world.id" :size="13" />
                        </span>
                      </span>
                      <span class="wcard__name">{{ world.name }}</span>
                      <span
                        v-if="presets.worlds.value.filter((w) => w.name === world.name).length > 1"
                        class="wcard__rev"
                        >Version {{ world.revision }}</span
                      >
                      <span class="wcard__places">{{ placesLine(world.places) }}</span>
                      <span class="wcard__desc">{{ world.description }}</span>
                    </button>
                  </li>
                  <li v-if="!shownWorlds.length" class="nsx__none">
                    No world matches that search.
                  </li>
                </ul>
              </template>

              <!-- 2 · cast -->
              <template v-else-if="step === 2">
                <div class="cast__toolbar">
                  <SearchField v-model="filters.search" />
                  <ChipGroup v-model="filters.category" :options="categoryOptions" />
                  <SortSelect v-model="sortProxy" :options="sortOptions" />
                </div>
                <TransitionGroup name="ev-list" tag="div" class="cast__grid">
                  <CastCard
                    v-for="def in visibleCharacters"
                    :key="def.id"
                    :character="def"
                    :selected="selectedIds.has(def.id)"
                    @toggle="toggleCast(def)" />
                  <CreateCharacterTile key="create" @create="goCreateCharacter" />
                </TransitionGroup>
              </template>

              <!-- 3 · play mode -->
              <template v-else-if="step === 3">
                <h2 class="nsx__h">Choose your play mode</h2>
                <div class="modes">
                  <button
                    type="button"
                    class="mode"
                    :class="{ 'mode--on': sel.role === 'watcher' }"
                    :aria-pressed="sel.role === 'watcher'"
                    @click="chooseRole('watcher', $event)">
                    <span class="mode__tick" aria-hidden="true">
                      <IconCheck v-if="sel.role === 'watcher'" :size="13" />
                    </span>
                    <IconEye :size="40" class="mode__icon" />
                    <span class="mode__name">Observer</span>
                    <span class="mode__desc"
                      >Watch the cast and guide the story between turns.</span
                    >
                    <span class="mode__foot">No character of your own.</span>
                  </button>
                  <button
                    type="button"
                    class="mode"
                    :class="{ 'mode--on': sel.role === 'player' }"
                    :aria-pressed="sel.role === 'player'"
                    @click="chooseRole('player', $event)">
                    <span class="mode__tick" aria-hidden="true">
                      <IconCheck v-if="sel.role === 'player'" :size="13" />
                    </span>
                    <IconUser :size="40" class="mode__icon" />
                    <span class="mode__name">Player</span>
                    <span class="mode__desc">Play one character and decide what they do.</span>
                    <span class="mode__foot">You choose their actions.</span>
                  </button>
                </div>
                <template v-if="sel.role === 'player'">
                  <h2 class="nsx__h nsx__h--gap">Who will you play?</h2>
                  <div class="whos">
                    <button
                      v-for="member in sel.cast"
                      :key="member.key"
                      type="button"
                      class="who"
                      :class="{ 'who--on': sel.controlledKey === member.key }"
                      :aria-pressed="sel.controlledKey === member.key"
                      @click="choosePlayer(member.key, $event)">
                      <span class="who__pic">
                        <FramedImage
                          v-if="defOf(member)?.portrait"
                          :src="defOf(member)!.portrait!.src"
                          :frame="defOf(member)!.portrait!.portrait"
                          alt="" />
                        <StoryImage
                          v-else
                          :image-slot="defOf(member)?.imageSlot ?? 'character.ash'"
                          alt="" />
                      </span>
                      <span class="who__text">
                        <span class="who__name">{{ pinnedCharName(member) }}</span>
                        <span v-if="defOf(member)?.role" class="who__role">{{
                          defOf(member)?.role
                        }}</span>
                        <span class="who__start">Starts at {{ placeName(member.location) }}</span>
                      </span>
                      <span class="wcard__tick" aria-hidden="true">
                        <IconCheck v-if="sel.controlledKey === member.key" :size="13" />
                      </span>
                    </button>
                  </div>
                </template>
                <h2 class="nsx__h nsx__h--gap">What kind of story?</h2>
                <div class="modes modes--kind">
                  <button
                    type="button"
                    class="mode mode--small"
                    :class="{ 'mode--on': !sel.fights }"
                    :aria-pressed="!sel.fights"
                    @click="chooseFights(false, $event)">
                    <span class="mode__tick" aria-hidden="true">
                      <IconCheck v-if="!sel.fights" :size="13" />
                    </span>
                    <IconBook :size="30" class="mode__icon" />
                    <span class="mode__name">A tale</span>
                    <span class="mode__desc">Talk, travel and discover. No dice, no fights.</span>
                  </button>
                  <button
                    type="button"
                    class="mode mode--small"
                    :class="{ 'mode--on': sel.fights }"
                    :aria-pressed="sel.fights"
                    @click="chooseFights(true, $event)">
                    <span class="mode__tick" aria-hidden="true">
                      <IconCheck v-if="sel.fights" :size="13" />
                    </span>
                    <IconEmblem :size="30" class="mode__icon" />
                    <span class="mode__name">An adventure with fights</span>
                    <span class="mode__desc"
                      >{{
                        sel.role === 'player'
                          ? 'Your hero gets health, armour and weapons.'
                          : 'The cast travels as a party with health, armour and weapons.'
                      }}
                      The storyteller starts fights; the dice decide them.</span
                    >
                  </button>
                </div>
                <Transition name="ev-rise">
                  <div v-if="sel.fights && sel.role === 'player'" class="hero">
                    <h3 class="hero__h">{{ controlledDisplay || 'Your hero' }}'s people</h3>
                    <div class="hero__picks" role="radiogroup" aria-label="People">
                      <button
                        v-for="r in HERO_RACES"
                        :key="r.key"
                        type="button"
                        role="radio"
                        class="hero__pick ev-press"
                        :class="{ 'hero__pick--on': sel.race === r.key }"
                        :aria-checked="sel.race === r.key"
                        :title="r.blurb"
                        @click="sel.race = r.key">
                        {{ r.name }}
                      </button>
                    </div>
                    <p class="hero__blurb">
                      {{ HERO_RACES.find((r) => r.key === sel.race)?.blurb }}
                    </p>
                    <h3 class="hero__h">Calling</h3>
                    <div class="hero__picks" role="radiogroup" aria-label="Calling">
                      <button
                        v-for="c in HERO_CLASSES"
                        :key="c.key"
                        type="button"
                        role="radio"
                        class="hero__pick ev-press"
                        :class="{ 'hero__pick--on': sel.characterClass === c.key }"
                        :aria-checked="sel.characterClass === c.key"
                        :title="c.blurb"
                        @click="sel.characterClass = c.key">
                        {{ c.name }}
                      </button>
                    </div>
                    <p class="hero__blurb">
                      {{ HERO_CLASSES.find((c) => c.key === sel.characterClass)?.blurb }}
                    </p>
                    <p class="nsx__lead">
                      {{ controlledDisplay || 'Your hero' }} starts as a {{ heroSummary }}.
                      Companions can join the party along the way.
                    </p>
                  </div>
                </Transition>
                <Transition name="ev-rise">
                  <div v-if="watchedPartyNames" class="hero">
                    <h3 class="hero__h">The party</h3>
                    <p class="nsx__lead">
                      {{ namesLine(watchedPartyNames.party) }}
                      {{ watchedPartyNames.party.length === 1 ? 'sets' : 'set' }} out as an
                      adventuring party. Each takes the people and calling that suit their
                      character, and they level up as they win. You watch the dice.
                    </p>
                    <p v-if="watchedPartyNames.left.length" class="hero__blurb">
                      A party is four at most: {{ namesLine(watchedPartyNames.left) }}
                      {{ watchedPartyNames.left.length === 1 ? 'is' : 'are' }} in the story but not
                      in the party.
                    </p>
                  </div>
                </Transition>
                <p v-if="modeNotice" class="nsv__notice" role="status">{{ modeNotice }}</p>
              </template>

              <!-- 4 · story -->
              <template v-else-if="step === 4">
                <div class="grp">
                  <h2 class="nsx__h">Title</h2>
                  <p class="nsx__lead">Give your story a title. You can change it later.</p>
                  <input
                    v-model="sel.title"
                    class="ev-input nsx__input"
                    type="text"
                    maxlength="128"
                    aria-label="Title"
                    placeholder="A Morning in Ember Vale" />
                </div>
                <div class="grp">
                  <h2 class="nsx__h">Tone</h2>
                  <p class="nsx__lead">
                    Describe the mood in your own words, or choose a starting point.
                  </p>
                  <input
                    v-model="sel.tone"
                    class="ev-input nsx__input"
                    type="text"
                    maxlength="128"
                    aria-label="Tone"
                    placeholder="hopeful mystery" />
                  <div class="tones">
                    <button
                      v-for="tone in TONE_PRESETS"
                      :key="tone.value"
                      type="button"
                      class="tone"
                      :class="{ 'tone--on': sel.tone.trim().toLowerCase() === tone.value }"
                      :aria-pressed="sel.tone.trim().toLowerCase() === tone.value"
                      @click="sel.tone = tone.value">
                      <span class="tone__dot" aria-hidden="true"></span>
                      <span class="tone__title">{{ tone.title }}</span>
                      <span class="tone__line">{{ tone.line }}</span>
                    </button>
                  </div>
                </div>
              </template>

              <!-- 5 · storyteller -->
              <template v-else-if="step === 5">
                <h2 class="nsx__h">Storyteller</h2>
                <div class="opts">
                  <button
                    type="button"
                    class="opt"
                    :class="{ 'opt--on': !customTeller }"
                    :aria-pressed="!customTeller"
                    @click="useAppTeller">
                    <span class="tone__dot" aria-hidden="true"></span>
                    <span class="opt__title"
                      >Use the app's storyteller <span class="opt__tag">Default</span></span
                    >
                    <span class="opt__line">The storyteller set in Settings: {{ appTeller }}.</span>
                  </button>
                  <button
                    type="button"
                    class="opt"
                    :class="{ 'opt--on': customTeller }"
                    :aria-pressed="customTeller"
                    @click="customTeller = true">
                    <span class="tone__dot" aria-hidden="true"></span>
                    <span class="opt__title">Choose a provider profile</span>
                    <span class="opt__line"
                      >Keep this story on one exact profile, even if Settings change.</span
                    >
                  </button>
                </div>
                <Transition name="ev-rise">
                  <div v-if="customTeller" class="grp nsx__pick">
                    <p
                      v-if="pinCtl.loading.value && !pinCtl.providers.value.length"
                      class="nsv__notice"
                      role="status">
                      Loading providers<span class="ev-dots" aria-hidden="true"
                        ><span>.</span><span>.</span><span>.</span></span
                      >
                    </p>
                    <p v-if="pinCtl.error.value" class="nsv__notice" role="alert">
                      {{ pinCtl.error.value }} —
                      <button type="button" class="nsv__link" @click="pinCtl.retry()">retry</button>
                    </p>
                    <p
                      v-if="
                        !pinCtl.loading.value &&
                        !pinCtl.error.value &&
                        !pinCtl.providers.value.length
                      "
                      class="nsx__lead">
                      No provider profiles yet. Add one in Settings, or use the app's storyteller.
                    </p>
                    <div class="grid2">
                      <label v-if="pinCtl.providers.value.length" class="nsv__field">
                        Provider
                        <select
                          :value="pinCtl.providerId.value"
                          @change="
                            pinCtl.selectProvider(($event.target as HTMLSelectElement).value)
                          ">
                          <option value="">Choose a provider…</option>
                          <option
                            v-for="connection in pinCtl.providers.value"
                            :key="connection.id"
                            :value="connection.id">
                            {{ connection.name }} ({{ connection.adapter }})
                          </option>
                        </select>
                      </label>
                      <label v-if="pinCtl.providerId.value" class="nsv__field">
                        Profile
                        <select
                          :value="pinCtl.profileId.value"
                          :disabled="!pinCtl.profiles.value.length"
                          @change="
                            pinCtl.selectProfile(($event.target as HTMLSelectElement).value)
                          ">
                          <option v-if="!pinCtl.profiles.value.length" value="">
                            No profiles yet
                          </option>
                          <option
                            v-for="profile in pinCtl.profiles.value"
                            :key="profile.id"
                            :value="profile.id">
                            {{ profile.model_id }} · version {{ profile.revision }}
                          </option>
                        </select>
                      </label>
                    </div>
                  </div>
                </Transition>
                <CollapseBox class="nsx__more" title="Advanced details">
                  <p class="nsx__lead">
                    Choosing a profile saves its exact version with this story, so later changes in
                    Settings never change how it is told.
                  </p>
                  <p v-if="envNotice" class="nsx__lead">{{ envNotice }}</p>
                  <p class="nsx__lead">Selected: {{ pinCtl.summary.value }}</p>
                </CollapseBox>
              </template>

              <!-- 6 · review -->
              <template v-else>
                <h2 class="nsx__h">Your story setup</h2>
                <ul class="setup ev-rise">
                  <li class="setup__row">
                    <span class="setup__label">World</span>
                    <span class="setup__what">
                      <span v-if="selectedWorld?.cover" class="setup__pic setup__pic--wide">
                        <FramedImage
                          :src="selectedWorld.cover.src"
                          :frame="selectedWorld.cover.frame"
                          alt="" />
                      </span>
                      <span class="setup__text">
                        <b>{{ selectedWorld?.name ?? 'No world chosen' }}</b>
                        <span>{{ worldPlaces.length }} places</span>
                      </span>
                    </span>
                    <button type="button" class="setup__edit" @click="go(1)">Edit</button>
                  </li>
                  <li class="setup__row">
                    <span class="setup__label">Characters</span>
                    <span class="setup__what">
                      <span v-for="member in sel.cast" :key="member.key" class="setup__face">
                        <FramedImage
                          v-if="defOf(member)?.portrait"
                          :src="defOf(member)!.portrait!.src"
                          :frame="defOf(member)!.portrait!.face"
                          alt="" />
                        <StoryImage
                          v-else
                          :image-slot="defOf(member)?.imageSlot ?? 'character.ash'"
                          alt="" />
                        <span>{{ pinnedCharName(member) }}</span>
                      </span>
                      <span v-if="!sel.cast.length" class="setup__text">No one yet</span>
                    </span>
                    <button type="button" class="setup__edit" @click="go(2)">Edit</button>
                  </li>
                  <li class="setup__row">
                    <span class="setup__label">Play mode</span>
                    <span class="setup__text">
                      <b>{{ sel.role === 'player' ? 'Player' : 'Observer' }}</b>
                      <span>{{
                        sel.role === 'player'
                          ? `You play ${controlledDisplay}.`
                          : 'You watch the story unfold.'
                      }}</span>
                      <span v-if="heroSummary"
                        >An adventure with fights: {{ controlledDisplay }} is a
                        {{ heroSummary }}.</span
                      >
                      <span v-if="watchedPartyNames"
                        >An adventure with fights: {{ namesLine(watchedPartyNames.party) }}
                        {{ watchedPartyNames.party.length === 1 ? 'travels' : 'travel' }} as a
                        party.</span
                      >
                    </span>
                    <button type="button" class="setup__edit" @click="go(3)">Edit</button>
                  </li>
                  <li class="setup__row">
                    <span class="setup__label">Story</span>
                    <span class="setup__text">
                      <b>{{ sel.title || 'Untitled' }}</b>
                      <span v-if="sel.tone">Tone: {{ toneLabel(sel.tone) }}</span>
                    </span>
                    <button type="button" class="setup__edit" @click="go(4)">Edit</button>
                  </li>
                  <li class="setup__row">
                    <span class="setup__label">Storyteller</span>
                    <span class="setup__text">
                      <b>{{ customTeller ? pinCtl.summary.value : "The app's storyteller" }}</b>
                      <span v-if="!customTeller">Currently {{ appTeller }}</span>
                    </span>
                    <button type="button" class="setup__edit" @click="go(5)">Edit</button>
                  </li>
                </ul>
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
              </template>
            </div>
          </Transition>
        </section>

        <!-- ————— what the step adds up to ————— -->
        <aside class="nsx__side card ev-card" :aria-label="sideTitle">
          <header class="nsx__sidehead">
            <h2 class="nsx__sidetitle">{{ sideTitle }}</h2>
            <span v-if="step === 1 && selectedWorld" class="nsx__pill"
              ><IconCheck :size="12" /> Selected</span
            >
            <span v-if="step === 2" class="nsx__count">{{ sel.cast.length }} of 6 selected</span>
          </header>

          <!-- the banner: the world, with your character on it from step 3 -->
          <Transition name="ev-fade">
            <div v-if="step !== 2 && step !== 5" class="banner">
              <span :key="selectedWorld?.id ?? 'none'" class="banner__pan">
                <FramedImage
                  v-if="selectedWorld?.cover"
                  class="banner__world ev-drift"
                  :src="selectedWorld.cover.src"
                  :frame="selectedWorld.cover.frame"
                  alt="" />
                <span v-else class="banner__world banner__world--none"><MountainRidge /></span>
              </span>
              <EmberField :count="9" :rise="140" tone="dust" />
              <span v-if="step >= 3 && playerDef" class="banner__you">
                <FramedImage
                  v-if="playerDef.portrait"
                  :key="playerDef.portrait.src"
                  :src="playerDef.portrait.src"
                  :frame="playerDef.portrait.portrait"
                  alt="" />
                <StoryImage
                  v-else
                  :key="playerDef.imageSlot"
                  :image-slot="playerDef.imageSlot"
                  alt="" />
              </span>
            </div>
          </Transition>

          <div class="nsx__swap">
            <Transition name="ev-swap">
              <div :key="step" class="nsx__sidebody">
                <!-- 1 -->
                <template v-if="step === 1">
                  <template v-if="selectedWorld">
                    <h3 class="nsx__big">{{ selectedWorld.name }}</h3>
                    <p class="nsx__meta">{{ worldPlaces.length }} places</p>
                    <p class="nsx__text">{{ selectedWorld.description }}</p>
                    <div class="nsx__sub2">
                      <h4>Places you'll find</h4>
                      <router-link
                        class="nsx__link"
                        :to="{
                          path: `/new-story/world/${sel.worldId}`,
                          query: { draft: draftCtl.draft.value?.id }
                        }"
                        >Edit this world</router-link
                      >
                    </div>
                    <ul class="chips ev-pop-stagger">
                      <li v-for="place in worldPlaces.slice(0, 8)" :key="place.key">
                        {{ place.name }}
                      </li>
                      <li v-if="worldPlaces.length > 8" class="chips__more">
                        +{{ worldPlaces.length - 8 }} more
                      </li>
                    </ul>
                  </template>
                  <p v-else class="nsx__quiet">Pick a world to see it here.</p>
                </template>

                <!-- 2 -->
                <template v-else-if="step === 2">
                  <p v-if="selectedWorld" class="nsx__meta">{{ selectedWorld.name }}</p>
                  <p v-if="!sel.cast.length" class="nsx__quiet">
                    No one yet. Pick from the library.
                  </p>
                  <TransitionGroup v-else name="ev-list" tag="ul" class="crew">
                    <li v-for="member in sel.cast" :key="member.key" class="crew__row">
                      <span class="crew__pic">
                        <FramedImage
                          v-if="defOf(member)?.portrait"
                          :src="defOf(member)!.portrait!.src"
                          :frame="defOf(member)!.portrait!.portrait"
                          alt="" />
                        <StoryImage
                          v-else
                          :image-slot="defOf(member)?.imageSlot ?? 'character.ash'"
                          alt="" />
                      </span>
                      <span class="crew__body">
                        <b class="crew__name">{{ pinnedCharName(member) }}</b>
                        <span v-if="defOf(member)?.role" class="crew__role">{{
                          defOf(member)?.role
                        }}</span>
                        <label class="sel__place">
                          Starts at
                          <select v-model="member.location" :disabled="!!pinned.worldError.value">
                            <option
                              v-for="place in worldPlaces"
                              :key="place.key"
                              :value="place.key">
                              {{ place.name }}
                            </option>
                          </select>
                        </label>
                      </span>
                      <span class="crew__acts">
                        <router-link
                          class="nsx__link"
                          :to="{
                            path: `/new-story/character/${member.presetId}`,
                            query: { draft: draftCtl.draft.value?.id }
                          }"
                          >Edit character</router-link
                        >
                        <button
                          type="button"
                          class="crew__remove"
                          @click="toggleCast(defOf(member) ?? characterDefs[0]!)">
                          Remove
                        </button>
                      </span>
                    </li>
                  </TransitionGroup>
                  <p class="nsx__note">
                    <IconUsers :size="16" /> Everyone you add can appear in the story.
                  </p>
                </template>

                <!-- 3 -->
                <template v-else-if="step === 3">
                  <h3 class="nsx__big">
                    {{
                      sel.role === 'player'
                        ? `You play ${controlledDisplay}`
                        : 'You watch the story'
                    }}
                  </h3>
                  <ul class="chips chips--teal">
                    <li>{{ sel.role === 'player' ? 'Player' : 'Observer' }}</li>
                    <li v-if="heroSummary">With fights · {{ heroSummary }}</li>
                    <li v-if="watchedPartyNames">
                      With fights · a party of {{ watchedPartyNames.party.length }}
                    </li>
                    <li v-if="sel.role === 'player' && playerMember">
                      Starts at {{ placeName(playerMember.location) }}
                    </li>
                    <li v-if="selectedWorld">{{ selectedWorld.name }}</li>
                  </ul>
                  <p class="nsx__text">
                    {{
                      sel.role === 'player'
                        ? `${controlledDisplay}'s actions are yours. The storyteller answers through the world and the other characters.`
                        : 'Every character acts on their own. You can step in between turns to guide the story.'
                    }}
                  </p>
                  <template v-if="others.length">
                    <h4 class="nsx__h4">
                      {{ sel.role === 'player' ? 'Also in your story' : 'In your story' }}
                    </h4>
                    <ul class="mini">
                      <li v-for="member in others" :key="member.key">
                        <span class="mini__face">
                          <FramedImage
                            v-if="defOf(member)?.portrait"
                            :src="defOf(member)!.portrait!.src"
                            :frame="defOf(member)!.portrait!.face"
                            alt="" />
                          <StoryImage
                            v-else
                            :image-slot="defOf(member)?.imageSlot ?? 'character.ash'"
                            alt="" />
                        </span>
                        <span>
                          <b>{{ pinnedCharName(member) }}</b>
                          <span>{{
                            [defOf(member)?.role, `Starts at ${placeName(member.location)}`]
                              .filter(Boolean)
                              .join(' · ')
                          }}</span>
                        </span>
                      </li>
                    </ul>
                  </template>
                </template>

                <!-- 4 and 6 -->
                <template v-else-if="step === 4 || step === 6">
                  <h3 class="nsx__big">{{ sel.title || 'Untitled story' }}</h3>
                  <ul class="facts">
                    <li v-if="selectedWorld"><IconGlobe :size="16" /> {{ selectedWorld.name }}</li>
                    <li>
                      <IconUser :size="16" />
                      {{ sel.role === 'player' ? `You play ${controlledDisplay}` : 'You watch' }}
                    </li>
                    <li v-if="others.length">
                      <IconUsers :size="16" /> With
                      {{ others.map((m) => pinnedCharName(m)).join(', ') }}
                    </li>
                    <li v-if="playerMember">Starts at {{ placeName(playerMember.location) }}</li>
                  </ul>
                  <ul v-if="sel.tone" class="chips chips--teal">
                    <li>{{ toneLabel(sel.tone) }}</li>
                  </ul>
                  <template v-if="step === 4">
                    <h4 class="nsx__h4">Your cast</h4>
                    <ul class="mini">
                      <li v-for="member in sel.cast" :key="member.key">
                        <span class="mini__face">
                          <FramedImage
                            v-if="defOf(member)?.portrait"
                            :src="defOf(member)!.portrait!.src"
                            :frame="defOf(member)!.portrait!.face"
                            alt="" />
                          <StoryImage
                            v-else
                            :image-slot="defOf(member)?.imageSlot ?? 'character.ash'"
                            alt="" />
                        </span>
                        <span>
                          <b>{{ pinnedCharName(member) }}</b>
                          <span>{{
                            member.key === sel.controlledKey && sel.role === 'player'
                              ? 'You play them'
                              : (defOf(member)?.role ?? '')
                          }}</span>
                        </span>
                      </li>
                    </ul>
                  </template>
                </template>

                <!-- 5 -->
                <template v-else>
                  <div class="teller">
                    <span class="teller__icon"><IconFeather :size="34" /></span>
                    <span>
                      <b class="nsx__big nsx__big--sm">{{
                        customTeller ? 'Your chosen profile' : "The app's storyteller"
                      }}</b>
                      <span class="nsx__meta">{{
                        customTeller ? pinCtl.summary.value : `Currently ${appTeller}`
                      }}</span>
                      <span class="nsx__text">{{
                        customTeller
                          ? 'This story keeps that profile version, whatever Settings say later.'
                          : 'Whatever storyteller Settings name will tell this story.'
                      }}</span>
                    </span>
                  </div>
                  <h4 class="nsx__h4">Your story</h4>
                  <div class="mini-story">
                    <span class="mini-story__pic">
                      <FramedImage
                        v-if="selectedWorld?.cover"
                        :src="selectedWorld.cover.src"
                        :frame="selectedWorld.cover.frame"
                        alt="" />
                    </span>
                    <ul class="facts facts--col">
                      <li>
                        <b>{{ sel.title || 'Untitled story' }}</b>
                      </li>
                      <li v-if="selectedWorld">
                        <IconGlobe :size="15" /> {{ selectedWorld.name }}
                      </li>
                      <li>
                        <IconUser :size="15" />
                        {{ sel.role === 'player' ? `Player · ${controlledDisplay}` : 'Observer' }}
                      </li>
                      <li v-if="sel.tone"><IconSparkle :size="15" /> {{ toneLabel(sel.tone) }}</li>
                    </ul>
                  </div>
                </template>
              </div>
            </Transition>
          </div>
        </aside>
      </div>

      <footer class="nsv__footer">
        <span
          class="nsv__draftstate"
          :class="{
            'nsv__draftstate--warn': draftCtl.draft.value && dirty,
            'nsv__draftstate--bad': draftCtl.saveState.value === 'failed',
            'nsv__draftstate--ok':
              draftCtl.draft.value && !dirty && draftCtl.saveState.value !== 'failed'
          }"
          role="status">
          <span class="nsv__draftdot" aria-hidden="true"></span>
          {{
            !draftCtl.draft.value
              ? 'No draft yet'
              : draftCtl.saveState.value === 'failed'
                ? 'Save failed — choices kept here'
                : dirty
                  ? 'Unsaved changes'
                  : 'Draft saved'
          }}
        </span>
        <span class="nsx__footnote">{{ footerNote }}</span>
        <MenuButton
          class="nsv__btn"
          v-if="step > 1"
          variant="outline"
          :icon="IconArrowLeft"
          arrow="none"
          :disabled="draftCtl.busy.value || draftCtl.creating.value"
          @click="back()"
          >Back</MenuButton
        >
        <MenuButton
          class="nsv__btn"
          variant="outline"
          :icon="IconSave"
          arrow="none"
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
        <MenuButton
          class="nsv__btn"
          v-if="step < 6"
          :disabled="!canContinue || draftCtl.busy.value || draftCtl.creating.value"
          @click="next()">
          Continue to {{ nextLabel }}
        </MenuButton>
        <MenuButton
          class="nsv__btn ev-sheen"
          v-else
          :icon="IconPlay"
          arrow="none"
          :disabled="
            draftCtl.creating.value ||
            draftCtl.busy.value ||
            localIssues.length > 0 ||
            locationIssues.length > 0 ||
            !!pinned.worldError.value ||
            !pinCtl.pinValid.value
          "
          @click="create()">
          {{ draftCtl.creating.value ? 'Creating…' : 'Begin the story' }}
        </MenuButton>
      </footer>

      <!-- Begin: the world opens while the story is being made -->
      <Transition name="ev-fade">
        <div v-if="draftCtl.creating.value" class="launch" role="status">
          <span class="launch__art">
            <FramedImage
              v-if="selectedWorld?.cover"
              class="launch__world"
              :src="selectedWorld.cover.src"
              :frame="selectedWorld.cover.frame"
              alt="" />
          </span>
          <EmberField :count="26" :rise="420" />
          <span class="launch__card">
            <span class="launch__ring" aria-hidden="true">
              <span class="ev-progress-spin"></span><span class="ev-progress-spin"></span>
            </span>
            <b class="launch__title ev-stamp">{{ sel.title || 'Untitled story' }}</b>
            <span class="launch__label">Creating…</span>
          </span>
        </div>
      </Transition>
    </template>
    <div v-else class="nsv__state" role="status">
      <p class="nsv__state-title">
        Opening the library<span class="ev-dots" aria-hidden="true"
          ><span>.</span><span>.</span><span>.</span></span
        >
      </p>
    </div>
  </main>
</template>

<style scoped>
.nsv {
  max-width: 1440px;
  margin: 0 auto;
  padding: 14px 16px 24px;
  /* the step fills the window, so the actions sit at its foot */
  min-height: calc(100vh - 62px);
  display: flex;
  flex-direction: column;
}
.nsv__panel {
  flex: 1;
  margin-top: 14px;
  padding: 20px 22px 22px;
  border: 1px solid var(--line);
  border-radius: 14px;
  background: linear-gradient(180deg, var(--surface-2), var(--surface));
  box-shadow: var(--card-shadow);
  animation: ev-rise 0.4s var(--ease-out) both;
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
  position: sticky;
  bottom: 12px;
  z-index: 5;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 14px;
  padding: 12px 14px 12px 20px;
  border: 1px solid var(--line);
  border-radius: 14px;
  background: linear-gradient(180deg, #fdf8ec, #f8f0dc);
  box-shadow: var(--card-shadow-hover);
}
.nsv__btn {
  width: auto;
  min-width: 132px;
}
.nsv__footer .nsv__btn:last-child {
  min-width: 190px;
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
  font-size: 14.5px;
  color: #6b5d43;
}
.sel__empty {
  color: #6b5d43;
  font-size: 15.5px;
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
  gap: 3px;
  width: 100%;
  text-align: left;
  padding: 14px 16px;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: linear-gradient(180deg, #fcf7ea, #f8f1df);
  cursor: pointer;
  font: inherit;
  color: inherit;
  transition:
    transform 0.22s var(--ease-out),
    box-shadow 0.22s var(--ease-out),
    border-color 0.2s ease;
}
.nsv__world:hover {
  transform: translateY(-2px);
  border-color: #c4a86f;
  box-shadow: var(--card-shadow-hover);
}
.nsv__world--pictured {
  grid-template-columns: 168px minmax(0, 1fr);
  column-gap: 14px;
}
.nsv__world--pictured > :not(.nsv__world-pic) {
  grid-column: 2;
}
.nsv__world-pic {
  grid-column: 1;
  grid-row: 1 / span 4;
  align-self: center;
  aspect-ratio: 16 / 7;
  height: auto;
  border-radius: 8px;
}
@media (max-width: 520px) {
  .nsv__world--pictured {
    grid-template-columns: minmax(0, 1fr);
  }
  .nsv__world--pictured > :not(.nsv__world-pic) {
    grid-column: 1;
  }
  .nsv__world-pic {
    grid-row: auto;
  }
}
.nsv__world--on,
.nsv__world--on:hover {
  border-color: var(--teal-ink);
  background: linear-gradient(180deg, #fdfaf0, #f3f0e0);
  box-shadow:
    0 0 0 2px rgba(31, 106, 94, 0.28),
    0 0 0 6px var(--ember-glow),
    var(--card-shadow);
}
.nsv__world-name {
  font-family: var(--font-display);
  font-size: 23px;
  font-weight: 600;
  line-height: 1.15;
}
.nsv__world-rev {
  font-family: var(--font-ui);
  font-size: 14px;
  color: #6b5d43;
}
.nsv__world-desc {
  font-size: 16px;
  color: #4a4436;
}
.nsv__world-places {
  font-family: var(--font-ui);
  font-size: 15px;
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
  margin-top: 10px;
  font-size: 16px;
  color: #6b5d43;
}
.nsv__link {
  font: inherit;
  color: #1f4d3f;
  background: none;
  border: none;
  cursor: pointer;
  text-decoration: underline;
  padding: 0;
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
  display: inline-flex;
  align-items: center;
  gap: 8px;
  margin-right: auto;
  font-family: var(--font-ui);
  font-size: 15.5px;
  color: #6b5d43;
}
.nsv__draftdot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: var(--faint);
}
.nsv__draftstate--ok .nsv__draftdot {
  background: #3f8f6b;
  box-shadow: 0 0 0 3px rgba(63, 143, 107, 0.18);
}
.nsv__draftstate--warn .nsv__draftdot {
  background: var(--ember-hi);
  box-shadow: 0 0 0 3px var(--ember-glow);
  position: relative;
}
.nsv__draftstate--warn .nsv__draftdot::after {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: 50%;
  pointer-events: none;
  box-shadow: 0 0 0 3px rgba(214, 112, 48, 0.35);
  opacity: 0;
  --ev-ring-scale: 1.7;
  animation: ev-ring 1.6s var(--ease-out) infinite;
}
.nsv__draftstate--bad {
  color: #7c3226;
}
.nsv__draftstate--bad .nsv__draftdot {
  background: #b3543f;
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
  font-size: 14px;
  color: #6b5d43;
}
.sel__place {
  display: grid;
  gap: 4px;
  font-size: 15px;
}
.sel__remove {
  justify-self: start;
  font: inherit;
  font-size: 14.5px;
  color: #7c3226;
  background: none;
  border: none;
  cursor: pointer;
  text-decoration: underline;
  padding: 0;
}
/* Studio entry links carry ?draft= so the return adoption binds to this draft. */
.sel__refine {
  justify-self: start;
  font-size: inherit;
  color: var(--teal-ink);
  text-decoration: underline;
}
</style>

<!-- The step-by-step layout: a heading and steps across the page, then the
     step beside what it adds up to; both columns end together. -->
<style scoped>
.nsx__top {
  container-type: inline-size;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.nsx__title {
  font-family: var(--font-display);
  font-size: 44px;
  font-weight: 600;
  line-height: 1.05;
  color: var(--ink);
}
.nsx__intro {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 16px;
  font-size: 18px;
  color: var(--ink-2);
}
.nsx__saves {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding-left: 16px;
  border-left: 1px solid var(--line);
  font-family: var(--font-ui);
  font-size: 15px;
  color: var(--ink-3);
}
.nsx__stepper {
  margin-top: 6px;
}
.nsx__body {
  flex: 1;
  display: grid;
  grid-template-columns: minmax(0, 1.55fr) minmax(360px, 1fr);
  gap: 14px;
  align-items: stretch;
  margin-top: 14px;
}
.nsx__main,
.nsx__side {
  min-width: 0;
  padding: 20px 22px 22px;
}
.nsx__head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px 14px;
  margin-bottom: 14px;
}
.nsx__h {
  font-family: var(--font-display);
  font-size: 26px;
  font-weight: 600;
  color: var(--ink);
}
.nsx__h--gap {
  margin-top: 22px;
}
.nsx__h + .modes,
.nsx__h + .whos,
.nsx__h + .setup,
.nsx__h + .opts {
  margin-top: 12px;
}
.nsx__count {
  font-family: var(--font-ui);
  font-size: 15px;
  color: var(--ink-3);
}
.nsx__search {
  flex: 1 1 200px;
  max-width: 280px;
  margin-left: auto;
}
.nsx__create {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  text-decoration: none;
}
.nsx__lead {
  margin: 4px 0 10px;
  font-size: 16px;
  color: var(--ink-3);
}
.nsx__input {
  width: 100%;
}
.nsx__none,
.nsx__quiet {
  font-style: italic;
  color: var(--muted);
}
.grp + .grp {
  margin-top: 22px;
  padding-top: 20px;
  border-top: 1px solid var(--line-soft);
}

/* worlds */
.nsx__worlds {
  list-style: none;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 14px;
}
.wcard {
  display: flex;
  flex-direction: column;
  gap: 3px;
  width: 100%;
  height: 100%;
  padding: 8px 8px 14px;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: linear-gradient(180deg, #fcf7ea, #f8f1df);
  text-align: left;
  transition:
    border-color 0.15s ease,
    box-shadow 0.15s ease;
}
.wcard:hover {
  border-color: #c6b48a;
}
.wcard--on {
  border-color: var(--teal);
  box-shadow: 0 0 0 1px var(--teal);
}
.wcard__pic {
  position: relative;
  display: block;
  aspect-ratio: 16 / 7;
  margin-bottom: 8px;
  border-radius: 8px;
  overflow: hidden;
  background: #efe5cc;
}
.wcard__pic > :first-child {
  width: 100%;
  height: 100%;
}
.wcard__nopic {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: flex-end;
  padding-bottom: 10px;
  font-family: var(--font-ui);
  font-size: 13.5px;
  color: var(--ink-3);
}
.wcard__ridge {
  position: absolute;
  inset: 20% 0 0;
  opacity: 0.6;
}
.wcard__tick {
  position: absolute;
  top: 8px;
  right: 8px;
  display: grid;
  place-items: center;
  width: 26px;
  height: 26px;
  border-radius: 50%;
  border: 1.5px solid #c9b791;
  background: rgba(253, 249, 238, 0.92);
  color: var(--cream-on-teal);
}
.wcard--on .wcard__tick,
.who--on .wcard__tick {
  border-color: var(--teal);
  background: var(--teal);
}
.wcard__name,
.wcard__rev,
.wcard__places,
.wcard__desc {
  padding: 0 6px;
}
.wcard__name {
  font-family: var(--font-display);
  font-size: 23px;
  font-weight: 600;
  color: var(--ink);
}
.wcard__rev,
.wcard__places {
  font-family: var(--font-ui);
  font-size: 14px;
  color: var(--ink-3);
}
.wcard__desc {
  font-size: 15.5px;
  line-height: 1.4;
  color: var(--ink-2);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

/* play mode, tone, storyteller choices */
.modes,
.whos,
.tones,
.opts {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 14px;
}
.tones {
  margin-top: 14px;
  grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
}
.opts {
  grid-template-columns: 1fr;
  gap: 10px;
}
.mode,
.who,
.tone,
.opt {
  position: relative;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: linear-gradient(180deg, #fcf7ea, #f8f1df);
  text-align: left;
  transition:
    border-color 0.15s ease,
    box-shadow 0.15s ease,
    background-color 0.15s ease;
}
.mode:hover,
.who:hover,
.tone:hover,
.opt:hover {
  border-color: #c6b48a;
}
.mode--on,
.who--on,
.tone--on,
.opt--on {
  border-color: var(--teal);
  box-shadow: 0 0 0 1px var(--teal);
  background: linear-gradient(180deg, #f1f4ec, #eaf0e6);
}
.mode {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 26px 22px 18px;
  text-align: center;
}
.mode__tick {
  position: absolute;
  top: 12px;
  right: 12px;
  display: grid;
  place-items: center;
  width: 26px;
  height: 26px;
  border-radius: 50%;
  border: 1.5px solid #c9b791;
  color: var(--cream-on-teal);
}
.mode--on .mode__tick {
  border-color: var(--teal);
  background: var(--teal);
}
.mode__icon {
  color: var(--gold);
}
.mode--on .mode__icon {
  color: var(--teal-ink);
}
.mode__name {
  font-family: var(--font-display);
  font-size: 30px;
  font-weight: 600;
  color: var(--ink);
}
.mode__desc {
  max-width: 32ch;
  font-size: 16.5px;
  color: var(--ink-2);
}
.mode--small {
  padding: 18px 18px 14px;
}
.mode--small .mode__name {
  font-size: 23px;
}
.mode--small .mode__desc {
  font-size: 15px;
}
/* A story with fights: the hero's people and calling. */
.hero {
  margin-top: 16px;
  padding: 14px 16px 6px;
  border: 1px solid var(--line-soft);
  border-radius: 12px;
  background: var(--surface-2);
}
.hero__h {
  margin: 0 0 8px;
  font-family: var(--font-display);
  font-size: 20px;
  font-weight: 600;
  color: var(--ink);
}
.hero__picks {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.hero__pick {
  padding: 5px 12px;
  border: 1px solid var(--line);
  border-radius: 99px;
  background: var(--panel);
  font-family: var(--font-ui);
  font-size: 15px;
  color: var(--ink-2);
  cursor: pointer;
}
.hero__pick:hover {
  border-color: var(--line-strong);
}
.hero__pick--on {
  border-color: var(--teal);
  color: var(--cream-on-teal);
  background: var(--teal);
}
.hero__blurb {
  margin: 6px 0 14px;
  font-size: 15px;
  color: var(--ink-3);
}
.mode__foot {
  margin-top: 6px;
  padding-top: 10px;
  border-top: 1px solid var(--line-soft);
  font-size: 15px;
  color: var(--ink-3);
}
.who {
  display: flex;
  gap: 16px;
  align-items: stretch;
  padding: 8px;
}
.who__pic {
  flex: none;
  width: 110px;
  aspect-ratio: 2 / 3;
  border-radius: 8px;
  overflow: hidden;
}
.who__pic > * {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.who__text {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 10px 30px 10px 0;
}
.who__name {
  font-family: var(--font-display);
  font-size: 26px;
  font-weight: 600;
  color: var(--ink);
}
.who__role {
  font-family: var(--font-ui);
  font-size: 15px;
  color: var(--ink-3);
}
.who__start {
  margin-top: auto;
  font-size: 15px;
  color: var(--ink-2);
}
.tone,
.opt {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 2px 12px;
  padding: 14px 16px;
}
.tone__dot {
  grid-row: span 2;
  width: 20px;
  height: 20px;
  margin-top: 3px;
  border-radius: 50%;
  border: 1.5px solid #b9a679;
  background: #fffdf6;
}
.tone--on .tone__dot,
.opt--on .tone__dot {
  border: 6px solid var(--teal);
}
.tone__title,
.opt__title {
  font-family: var(--font-display);
  font-size: 21px;
  font-weight: 600;
  color: var(--ink);
}
.tone__line,
.opt__line {
  font-size: 15px;
  color: var(--ink-2);
}
.opt__tag {
  margin-left: 8px;
  padding: 2px 9px;
  border-radius: 6px;
  background: rgba(20, 84, 90, 0.12);
  font-family: var(--font-ui);
  font-size: 13px;
  font-weight: 500;
  color: var(--teal-ink);
  vertical-align: middle;
}
.nsx__pick {
  margin-top: 16px;
}
.nsx__more {
  margin-top: 18px;
}

/* review */
.setup {
  list-style: none;
  display: grid;
}
.setup__row {
  display: grid;
  grid-template-columns: 130px minmax(0, 1fr) auto;
  align-items: center;
  gap: 14px;
  padding: 14px 4px;
  border-bottom: 1px solid var(--line-soft);
}
.setup__label {
  font-family: var(--font-display);
  font-size: 21px;
  font-weight: 600;
  color: var(--ink);
}
.setup__what {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
}
.setup__text {
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: 15.5px;
  color: var(--ink-2);
}
.setup__text b {
  font-size: 17px;
  font-weight: 500;
  color: var(--ink);
}
.setup__pic--wide {
  width: 150px;
  aspect-ratio: 16 / 9;
  border-radius: 8px;
  overflow: hidden;
}
.setup__face {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  font-size: 14px;
  color: var(--ink-2);
}
.setup__face > :first-child {
  width: 54px;
  height: 54px;
  border-radius: 50%;
  overflow: hidden;
  border: 2px solid var(--gold-soft);
}
.setup__edit {
  font-family: var(--font-ui);
  font-size: 15px;
  color: var(--teal-ink);
  text-decoration: underline;
  text-underline-offset: 3px;
}

/* the side panel */
.nsx__side {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.nsx__sidehead {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}
.nsx__sidetitle {
  font-family: var(--font-display);
  font-size: 26px;
  font-weight: 600;
  color: var(--ink);
}
.nsx__pill {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 3px 10px;
  border-radius: 999px;
  background: rgba(20, 84, 90, 0.12);
  font-family: var(--font-ui);
  font-size: 13.5px;
  color: var(--teal-ink);
}
.banner {
  position: relative;
  aspect-ratio: 16 / 8;
  border-radius: 10px;
  overflow: hidden;
  background: #efe5cc;
}
.banner__world {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
}
.banner__world--none {
  display: block;
  opacity: 0.6;
}
.banner__you {
  position: absolute;
  right: 14px;
  bottom: 12px;
  width: 26%;
  aspect-ratio: 2 / 3;
  border-radius: 10px;
  overflow: hidden;
  border: 3px solid var(--surface-2);
  box-shadow: 0 6px 18px rgba(40, 30, 12, 0.35);
}
.nsx__big {
  font-family: var(--font-display);
  font-size: 32px;
  font-weight: 600;
  line-height: 1.1;
  color: var(--ink);
}
.nsx__big--sm {
  display: block;
  font-size: 25px;
}
.nsx__meta {
  display: block;
  font-family: var(--font-ui);
  font-size: 15px;
  color: var(--ink-3);
}
.nsx__text {
  display: block;
  font-size: 16px;
  line-height: 1.5;
  color: var(--ink-2);
}
.nsx__sub2 {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-top: 6px;
  padding-top: 12px;
  border-top: 1px solid var(--line-soft);
}
.nsx__sub2 h4,
.nsx__h4 {
  font-family: var(--font-ui);
  font-size: 16px;
  font-weight: 700;
  color: var(--ink);
}
.nsx__h4 {
  margin-top: 6px;
  padding-top: 12px;
  border-top: 1px solid var(--line-soft);
}
.nsx__link {
  font-family: var(--font-ui);
  font-size: 15px;
  color: var(--teal-ink);
  text-decoration: underline;
  text-underline-offset: 3px;
}
.chips {
  list-style: none;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.chips li {
  padding: 4px 11px;
  border-radius: 999px;
  background: #f3e5c8;
  border: 1px solid #e2cfa3;
  font-family: var(--font-ui);
  font-size: 14px;
  color: #6a5328;
}
.chips--teal li {
  background: rgba(20, 84, 90, 0.1);
  border-color: rgba(20, 84, 90, 0.18);
  color: var(--teal-ink);
}
.chips__more {
  font-style: italic;
}
.crew {
  list-style: none;
  display: grid;
  gap: 10px;
}
.crew__row {
  display: grid;
  grid-template-columns: 76px minmax(0, 1fr) auto;
  gap: 14px;
  align-items: start;
  padding: 10px;
  border: 1px solid var(--line-soft);
  border-radius: 12px;
  background: #fbf6e9;
}
.crew__pic {
  width: 76px;
  aspect-ratio: 2 / 3;
  border-radius: 8px;
  overflow: hidden;
}
.crew__pic > * {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.crew__body {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}
.crew__name {
  font-family: var(--font-display);
  font-size: 22px;
  font-weight: 600;
  color: var(--ink);
}
.crew__role {
  font-family: var(--font-ui);
  font-size: 14.5px;
  color: var(--ink-3);
}
.crew__acts {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 8px;
}
.crew__remove {
  font-family: var(--font-ui);
  font-size: 14.5px;
  color: #a2432c;
  text-decoration: underline;
  text-underline-offset: 3px;
}
.nsx__note {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: auto;
  font-family: var(--font-ui);
  font-size: 14.5px;
  color: var(--ink-3);
}
.mini {
  list-style: none;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(190px, 1fr));
  gap: 10px;
}
.mini li {
  display: flex;
  gap: 10px;
  align-items: center;
}
.mini li > span:last-child {
  display: flex;
  flex-direction: column;
  font-size: 14px;
  color: var(--ink-3);
}
.mini b {
  font-size: 16.5px;
  font-weight: 500;
  color: var(--ink);
}
.mini__face > *,
.setup__face > :first-child > *,
.banner__you > * {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.mini__face {
  flex: none;
  width: 48px;
  height: 48px;
  border-radius: 50%;
  overflow: hidden;
  border: 2px solid var(--gold-soft);
  background: #efe5cc;
}
.facts {
  list-style: none;
  display: flex;
  flex-wrap: wrap;
  gap: 8px 18px;
  font-size: 15.5px;
  color: var(--ink-2);
}
.facts li {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.facts svg {
  color: var(--gold);
}
.facts--col {
  flex-direction: column;
  gap: 6px;
}
.teller {
  display: flex;
  gap: 18px;
  align-items: center;
}
.teller > span:last-child {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.teller__icon {
  flex: none;
  display: grid;
  place-items: center;
  width: 110px;
  height: 110px;
  border-radius: 50%;
  background: radial-gradient(circle at 40% 35%, #f6ead0, #ead9b4);
  color: var(--teal-ink);
}
.mini-story {
  display: flex;
  gap: 16px;
  align-items: center;
}
.mini-story__pic {
  flex: none;
  width: 44%;
  aspect-ratio: 4 / 3;
  border-radius: 10px;
  overflow: hidden;
  background: #efe5cc;
}

/* footer context */
.nsv__footer .nsv__draftstate {
  margin-right: 0;
}
.nsx__footnote:empty {
  border: 0;
}
.nsx__footnote {
  margin-right: auto;
  padding-left: 14px;
  border-left: 1px solid var(--line);
  font-family: var(--font-ui);
  font-size: 15.5px;
  color: var(--ink-2);
}

@media (max-width: 1100px) {
  .nsx__body {
    grid-template-columns: minmax(0, 1fr);
  }
}
@media (max-width: 640px) {
  .nsx__title {
    font-size: 32px;
  }
  .setup__row {
    grid-template-columns: minmax(0, 1fr) auto;
  }
  .setup__what,
  .setup__text {
    grid-column: 1 / -1;
    grid-row: 2;
  }
  .crew__row {
    grid-template-columns: 60px minmax(0, 1fr);
  }
  .crew__acts {
    grid-column: 1 / -1;
    flex-direction: row;
    justify-content: flex-end;
  }
  .nsx__footnote {
    display: none;
  }
}
/* ————— motion ————— */

/* the step and the panel beside it change in place: old and new share one
   cell while one leaves and the other arrives, so nothing below jumps */
.nsx__main {
  display: grid;
  overflow-x: clip;
}
.nsx__step {
  grid-area: 1 / 1;
  min-width: 0;
}
.nsx__swap {
  display: grid;
}
.nsx__sidebody {
  grid-area: 1 / 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

/* world cards lift and their picture leans in */
.wcard {
  transition:
    border-color 0.15s ease,
    box-shadow 0.3s var(--ease-settle),
    transform 0.3s var(--ease-settle);
}
.wcard:hover {
  transform: translateY(-3px);
  box-shadow: 0 12px 22px -16px rgba(96, 74, 40, 0.55);
}
.wcard:active {
  transform: translateY(-1px) scale(0.985);
  transition-duration: 0.12s;
}
.wcard--on {
  box-shadow:
    0 0 0 1px var(--teal),
    0 12px 22px -16px rgba(23, 82, 86, 0.55);
}
.wcard__pic > :first-child {
  transition: transform 0.7s var(--ease-settle);
}
.wcard:hover .wcard__pic > :first-child {
  transform: scale(1.05);
}
.wcard__tick,
.mode__tick {
  transition:
    background-color 0.2s ease,
    border-color 0.2s ease;
}
.wcard--on .wcard__tick,
.who--on .wcard__tick,
.mode--on .mode__tick {
  animation: nsx-tick 0.45s var(--ease-spring);
}
.wcard__tick svg,
.mode__tick svg {
  animation: nsx-check 0.4s var(--ease-spring) both;
}
@keyframes nsx-tick {
  from {
    transform: scale(0.6);
  }
}
@keyframes nsx-check {
  from {
    opacity: 0;
    transform: scale(0.2) rotate(-25deg);
  }
}

/* choice cards: lift, press, and the chosen one comes alive */
.mode,
.who,
.tone,
.opt {
  transition:
    border-color 0.15s ease,
    box-shadow 0.3s var(--ease-settle),
    background-color 0.2s ease,
    transform 0.3s var(--ease-settle);
}
.mode:hover,
.who:hover,
.tone:hover,
.opt:hover {
  transform: translateY(-2px);
}
.mode:active,
.who:active,
.tone:active,
.opt:active {
  transform: scale(0.985);
  transition-duration: 0.12s;
}
.mode__icon {
  transition:
    color 0.2s ease,
    transform 0.4s var(--ease-settle);
}
.mode:hover .mode__icon {
  transform: translateY(-3px) scale(1.06);
}
.mode--on .mode__icon {
  animation:
    nsx-icon 0.55s var(--ease-spring),
    ev-float 4.5s var(--ease-sine) 0.55s infinite;
}
@keyframes nsx-icon {
  from {
    transform: scale(0.7) rotate(-8deg);
  }
}
.who__pic > * {
  transition: transform 0.6s var(--ease-settle);
}
.who:hover .who__pic > * {
  transform: scale(1.06);
}
.tone__dot {
  transition:
    border-width 0.3s var(--ease-spring),
    border-color 0.2s ease;
}

/* the review: each Edit nudges toward its step */
.setup__edit {
  transition:
    color 0.15s ease,
    transform 0.25s var(--ease-settle);
}
.setup__edit:hover {
  transform: translateX(3px);
}

/* the cast list: removed cards leave at once, the rest glide into place */
.cast__grid > .ev-list-leave-active {
  display: none;
}
.crew {
  position: relative;
}
.crew__row.ev-list-leave-active {
  position: absolute;
  left: 0;
  right: 0;
}

/* the side banner: the world drifts, its new picture fades in, you step in */
.banner__pan {
  position: absolute;
  inset: 0;
  overflow: hidden;
  animation: nsx-banner 0.9s var(--ease-settle) both;
}
@keyframes nsx-banner {
  from {
    opacity: 0;
    transform: scale(1.08);
  }
}
.banner__you > * {
  animation: nsx-you 0.6s var(--ease-settle) both;
}
@keyframes nsx-you {
  from {
    opacity: 0;
    transform: translateY(16px) scale(0.94);
  }
}
.banner__you {
  z-index: 2;
}

/* Begin: the world opens while the story is made */
.launch {
  position: fixed;
  inset: 0;
  z-index: 60;
  display: grid;
  place-items: center;
  background: #1d1810;
  overflow: hidden;
}
.launch__art {
  position: absolute;
  inset: 0;
  animation: nsx-launch 6s var(--ease-settle) both;
}
.launch__world {
  width: 100%;
  height: 100%;
  opacity: 0.55;
}
.launch__art::after {
  content: '';
  position: absolute;
  inset: 0;
  background: radial-gradient(
    80% 70% at 50% 50%,
    rgba(29, 24, 16, 0.15),
    rgba(29, 24, 16, 0.85) 100%
  );
}
@keyframes nsx-launch {
  from {
    transform: scale(1.18);
    filter: blur(8px);
  }
  to {
    transform: scale(1);
    filter: blur(0);
  }
}
.launch__card {
  position: relative;
  z-index: 2;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  color: #f6ecd6;
  text-align: center;
}
.launch__ring {
  position: relative;
  width: 64px;
  height: 64px;
}
.launch__ring span {
  position: absolute;
  inset: 0;
  border-radius: 50%;
  border: 3px solid transparent;
  border-top-color: var(--ember-hi);
  border-right-color: rgba(220, 122, 60, 0.3);
  animation: nsx-turn 1.4s linear infinite;
}
.launch__ring span:nth-child(2) {
  inset: 12px;
  border-top-color: #e9d38a;
  animation-duration: 2.1s;
  animation-direction: reverse;
}
@keyframes nsx-turn {
  to {
    transform: rotate(360deg);
  }
}
.launch__title {
  font-family: var(--font-display);
  font-size: clamp(32px, 5vw, 54px);
  font-weight: 600;
  line-height: 1.05;
  text-shadow: 0 2px 18px rgba(0, 0, 0, 0.5);
}
.launch__label {
  font-family: var(--font-ui);
  font-size: 16px;
  letter-spacing: 0.08em;
  color: #e7d6b0;
}
</style>
