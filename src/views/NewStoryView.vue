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
import { persistStepSlug, stepFromSlug } from '../game/wizardSteps'
import type { CharacterDef } from '../game/model'
import { useStorytellerPin } from '../composables/useStorytellerPin'

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
      ? { role: 'player', controlledKey: sel.controlledKey }
      : { role: 'watcher' },
  title: sel.title,
  tone: sel.tone || undefined,
  ...(pinCtl.pin.value ? { aiPin: pinCtl.pin.value } : {})
}))

// Storyteller pin (wizard step 5): an existing provider profile revision,
// persisted through the draft's `ai` section and executed by every beat.
// Request ownership lives in the composable: a late profile response can
// never stamp another provider's pin onto the current selection.
const pinCtl = useStorytellerPin()

watch(step, (next) => {
  if (next >= 5) void pinCtl.ensure()
})

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
  pinCtl.reset()
  sel.title = 'A Morning in Ember Vale'
  // Quick Start lands on Review with everything filled in — and persists.
  // The result is checked: a failed save must not claim durability.
  step.value = 6
  const saved = await persist()
  bootNotice.value = saved
    ? 'Quick Start filled in Ember Vale with Wren and Ash — review and begin, or step back to change anything.'
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

      <section v-if="step === 1" class="nsv__panel" aria-label="Choose a world">
        <h2 class="nsv__h">Where does the story begin?</h2>
        <p v-if="sel.worldId" class="nsv__hint">
          Shaping this world further?
          <router-link
            class="sel__refine"
            :to="{
              path: `/new-story/world/${sel.worldId}`,
              query: { draft: draftCtl.draft.value?.id }
            }">
            Refine it in the studio
          </router-link>
          — publishing returns here so the new revision can be adopted deliberately.
          <router-link
            class="sel__refine"
            :to="{
              path: '/new-story/world/new',
              query: { draft: draftCtl.draft.value?.id }
            }">
            Or shape a new world
          </router-link>
          — creating returns here so it can be adopted deliberately.
        </p>
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
              <CreateCharacterTile @create="goCreateCharacter" />
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
                <router-link
                  class="sel__refine"
                  :to="{
                    path: `/new-story/character/${member.presetId}`,
                    query: { draft: draftCtl.draft.value?.id }
                  }">
                  Refine
                </router-link>
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
        <h3 class="nsv__h">Storyteller model</h3>
        <p class="nsv__body">
          Pin the provider profile revision every beat executes. The pin saves with this draft and
          shows on Review; without one, beats use the environment default.
        </p>
        <p
          v-if="pinCtl.loading.value && !pinCtl.providers.value.length"
          class="nsv__notice"
          role="status">
          Loading providers…
        </p>
        <p v-if="pinCtl.error.value" class="nsv__notice" role="alert">
          {{ pinCtl.error.value }} —
          <button type="button" class="nsv__link" @click="pinCtl.retry()">retry</button>
        </p>
        <label v-if="pinCtl.providers.value.length" class="nsv__field">
          Provider
          <select
            :value="pinCtl.providerId.value"
            @change="pinCtl.selectProvider(($event.target as HTMLSelectElement).value)">
            <option value="">Environment default</option>
            <option
              v-for="connection in pinCtl.providers.value"
              :key="connection.id"
              :value="connection.id">
              {{ connection.name }} ({{ connection.adapter }})
            </option>
          </select>
        </label>
        <label v-if="pinCtl.providerId.value" class="nsv__field">
          Profile revision
          <select
            :value="pinCtl.profileId.value"
            :disabled="!pinCtl.profiles.value.length"
            @change="pinCtl.selectProfile(($event.target as HTMLSelectElement).value)">
            <option v-if="!pinCtl.profiles.value.length" value="">No profiles yet</option>
            <option v-for="profile in pinCtl.profiles.value" :key="profile.id" :value="profile.id">
              {{ profile.model_id }} · rev {{ profile.revision }}
            </option>
          </select>
        </label>
        <p class="nsv__notice" role="status">Selected: {{ pinCtl.summary.value }}</p>
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
          <div>
            <dt>Storyteller</dt>
            <dd>{{ pinCtl.summary.value }}</dd>
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
/* Studio entry links carry ?draft= so the return adoption binds to this draft. */
.sel__refine {
  justify-self: start;
  font-size: 13px;
  color: var(--teal-ink);
  text-decoration: underline;
}
</style>
