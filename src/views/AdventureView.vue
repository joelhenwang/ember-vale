<script setup lang="ts">
/**
 * Adventure: the player's seat as a game screen. You see where you are and
 * who is with you, read the story as it happens, and act in your own
 * words; every action runs one beat in which the whole world answers.
 */
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import WorldMap from '../components/observatory/WorldMap.vue'
import PlaceMap from '../components/observatory/PlaceMap.vue'
import IconArrowLeft from '../components/icons/IconArrowLeft.vue'
import IconArrowRight from '../components/icons/IconArrowRight.vue'
import IconFeather from '../components/icons/IconFeather.vue'
import IconClock from '../components/icons/IconClock.vue'
import IconSatchel from '../components/icons/IconSatchel.vue'
import IconImage from '../components/icons/IconImage.vue'
import IconExpand from '../components/icons/IconExpand.vue'
import IconGlobe from '../components/icons/IconGlobe.vue'
import IconDoc from '../components/icons/IconDoc.vue'
import IconBook from '../components/icons/IconBook.vue'
import IconUser from '../components/icons/IconUser.vue'
import IconX from '../components/icons/IconX.vue'
import IconGear from '../components/icons/IconGear.vue'
import IconChevronRight from '../components/icons/IconChevronRight.vue'
import MomentDialog from '../components/story/MomentDialog.vue'
import { momentTitle, readyMoments, type Speaker } from '../game/moments'
import PaintSceneDialog from '../components/story/PaintSceneDialog.vue'
import { assetUrl } from '../api/worldsim'
import FramedImage from '../components/ui/FramedImage.vue'
import { frameFromList } from '../game/framing'
import { useAdventure } from '../composables/useAdventure'
import {
  barFraction,
  cardDrives,
  doIntent,
  doPrompt,
  isFresh,
  phaseLight,
  leadChips,
  levelProgress,
  prologue,
  trimPlaceLead,
  turnChanges,
  type Glimpse,
  type TurnChange,
  sayIntent,
  sceneFocus,
  type LogLine
} from '../game/adventure'
import { beatTimeLabel, layoutTokens } from '../game/observatory'

const route = useRoute()
const storyId = computed(() => String(route.params.storyId ?? ''))
/** The scene whose "Paint this scene" dialog is open. */
const paintingScene = ref<string | null>(null)
const adv = useAdventure(storyId)

type Mode = 'do' | 'say'
const mode = ref<Mode>('do')
const text = ref('')
const sayTo = ref<string>('')
const logEl = ref<HTMLElement | null>(null)
const now = ref(Date.now())
const startedAt = ref<number | null>(null)
/** What changed on the last turn: shown under the story until the next one. */
const changes = ref<TurnChange[]>([])
function glimpse(): Glimpse {
  const stat = (key: string): number | null => {
    const v = stats.value?.[key]
    return typeof v === 'number' ? v : null
  }
  return {
    place: adv.here.value?.name ?? null,
    stamina: stat('stamina'),
    mana: stat('mana'),
    items: adv.items.value.flatMap((i) =>
      Array.from({ length: Math.max(1, i.quantity) }, () => i.name || i.item_key)
    ),
    present: adv.present.value.map((c) => c.name),
    rumours: (adv.presentation.value?.rumours ?? []).map((r) => r.title),
    settled: (adv.presentation.value?.settled ?? []).map((r) => r.title),
    renown: journey.value?.renown,
    level: journey.value?.level,
    title: journey.value?.title
  }
}
/** Run one turn: remember the world as it was, then say what changed. */
async function turn(run: () => Promise<boolean>): Promise<boolean> {
  const before = glimpse()
  changes.value = []
  const ok = await run()
  if (ok) changes.value = turnChanges(before, glimpse())
  return ok
}
/** The player's own action, shown at once while the world answers. */
const echo = ref<{ kind: 'say' | 'do'; text: string } | null>(null)

const names = computed(
  () => new Map((adv.presentation.value?.cast ?? []).map((c) => [c.character_id, c.name]))
)
const portraits = computed(
  () =>
    new Map(
      (adv.presentation.value?.cast ?? [])
        .filter((c) => c.portrait_asset_id)
        .map((c) => [
          c.character_id,
          {
            src: assetUrl(storyId.value, c.portrait_asset_id as string),
            face: frameFromList(c.face_frame)
          }
        ])
    )
)
const placeNames = computed(() => new Map(adv.places.value.map((p) => [p.id, p.name])))
const myName = computed(() => adv.self.value?.name ?? adv.sheet.value?.name ?? 'You')
const timeLabel = computed(() =>
  adv.presentation.value ? beatTimeLabel(adv.presentation.value.absolute_index) : ''
)
const sceneStyle = computed(() => {
  // The place's own art when it has some; else a close-up of the world map.
  const own = (adv.presentation.value?.place_art ?? []).find(
    (a) => a.location_id === adv.hereId.value
  )
  if (own) {
    return {
      backgroundImage: `url("${assetUrl(storyId.value, own.asset_id)}")`,
      backgroundSize: 'cover',
      backgroundPosition: '50% 40%'
    }
  }
  const art = adv.mapAssetId.value ? assetUrl(storyId.value, adv.mapAssetId.value) : null
  return art ? { backgroundImage: `url("${art}")`, ...sceneFocus(adv.anchor.value) } : {}
})
const tokens = computed(() =>
  adv.presentation.value
    ? layoutTokens(adv.presentation.value.manifest.anchors ?? [], adv.presentation.value.cast ?? [])
    : []
)
const card = computed(() => (adv.sheet.value?.card ?? null) as Record<string, unknown> | null)
const stats = computed(() => (adv.sheet.value?.state ?? null) as Record<string, unknown> | null)
const conditions = computed(() =>
  Array.isArray(stats.value?.conditions) ? (stats.value!.conditions as unknown[]).map(String) : []
)
const intro = computed(() => {
  if (!adv.me.value) return []
  return prologue({
    name: myName.value,
    place: adv.here.value?.name ?? null,
    appearance: typeof card.value?.appearance === 'string' ? card.value.appearance : null,
    others: (adv.presentation.value?.cast ?? [])
      .filter((c) => c.character_id !== adv.me.value && c.life_status === 'alive')
      .map((c) => ({ name: c.name, place: placeNames.value.get(c.location_id) ?? null }))
  })
})
const drives = computed(() => cardDrives(card.value?.personality))
const light = computed(() => phaseLight(adv.presentation.value?.phase))
const rumours = computed(() => adv.presentation.value?.rumours ?? [])
const settled = computed(() => adv.presentation.value?.settled ?? [])
const journey = computed(() => adv.presentation.value?.journey ?? null)
const levelFill = computed(() =>
  journey.value
    ? levelProgress(journey.value.renown, journey.value.level_floor, journey.value.next_level_at)
    : 0
)
const leads = computed(() =>
  adv.me.value
    ? leadChips(adv.me.value, rumours.value, adv.present.value, adv.places.value, adv.hereId.value)
    : []
)
const nowIndex = computed(() => adv.presentation.value?.absolute_index ?? 0)

/* ————— the picture: the latest painted moment, else the place ————— */
const moments = computed(() => readyMoments(adv.presentation.value?.scene_art))
const latest = computed(() => moments.value[moments.value.length - 1] ?? null)
const latestUrl = computed(() =>
  latest.value?.asset_id ? assetUrl(storyId.value, latest.value.asset_id) : null
)
/** Where the latest moment happened, when that is not where you are now. */
const latestElsewhere = computed(() => {
  const where = latest.value?.location_id
  return where && where !== adv.hereId.value ? (placeNames.value.get(where) ?? null) : null
})
const openedMoment = ref<number | null>(null)
function openMoment(): void {
  if (moments.value.length) openedMoment.value = moments.value.length - 1
}
function openPicture(pictureId: string): void {
  const at = moments.value.findIndex((m) => m.picture_id === pictureId)
  if (at >= 0) openedMoment.value = at
}
const speakers = computed(() => {
  const out = new Map<string, Speaker>()
  for (const c of adv.presentation.value?.cast ?? []) {
    out.set(c.character_id, {
      name: c.name,
      portraitUrl: c.portrait_asset_id ? assetUrl(storyId.value, c.portrait_asset_id) : null
    })
  }
  return out
})

/* ————— the lead: the newest rumour, the rest folded ————— */
const byNewest = computed(() =>
  [...rumours.value].sort((a, b) => (b.since_index ?? 0) - (a.since_index ?? 0))
)
const mainLead = computed(() => byNewest.value[0] ?? null)
const otherLeads = computed(() => byNewest.value.slice(1))
const leadsOpen = ref(false)

/* ————— the map: the whole world, or the place you are in ————— */
const localMap = computed(
  () =>
    (adv.presentation.value?.place_maps ?? []).find((m) => m.location_id === adv.hereId.value) ??
    null
)
const mapTab = ref<'world' | 'local'>('world')
const mapOpen = ref(false)
const detailsOpen = ref(false)

/** What Tab fills in: the first lead or suggestion, as plain words. */
const suggestion = computed(() => {
  if (mode.value !== 'do') return ''
  const first = leads.value[0]?.label ?? adv.chips.value[0]?.title ?? ''
  return first.split(' — ')[0]!.trim()
})
const elapsed = computed(() =>
  startedAt.value ? Math.max(0, Math.round((now.value - startedAt.value) / 1000)) : 0
)
const canSay = computed(() => adv.talkable.value.length > 0)
const sayTarget = computed(
  () =>
    adv.talkable.value.find((c) => c.character_id === sayTo.value) ?? adv.talkable.value[0] ?? null
)
const placeholder = computed(() =>
  mode.value === 'say'
    ? `What do you say to ${sayTarget.value?.name ?? 'them'}?`
    : suggestion.value
      ? `Suggested: ${suggestion.value} (Tab to fill)`
      : doPrompt(
          rumours.value[0]?.title ?? null,
          adv.present.value.map((c) => c.name)
        )
)
const ready = computed(() => !adv.acting.value && adv.alive.value && text.value.trim().length > 0)

function nameOf(id: string | null | undefined): string {
  return (id && names.value.get(id)) || 'Someone'
}
function initials(name: string): string {
  return name
    .split(/\s+/)
    .map((p) => p.charAt(0))
    .join('')
    .slice(0, 2)
    .toUpperCase()
}

async function submit(): Promise<void> {
  const me = adv.me.value
  if (!me || !ready.value) return
  const words = text.value.trim()
  const intent =
    mode.value === 'say' && sayTarget.value
      ? sayIntent(me, sayTarget.value.character_id, words)
      : doIntent(me, words)
  text.value = ''
  echo.value =
    mode.value === 'say' && sayTarget.value
      ? { kind: 'say', text: `"${words.replace(/^["“]|["”]$/g, '')}"` }
      : { kind: 'do', text: `You ${words.charAt(0).toLowerCase()}${words.slice(1)}` }
  const ok = await turn(() => adv.act(intent))
  echo.value = null
  if (!ok) text.value = words
}

async function pass(): Promise<void> {
  echo.value = { kind: 'do', text: 'You let a moment pass.' }
  await turn(() => adv.wait())
  echo.value = null
}

function talkTo(id: string): void {
  mode.value = 'say'
  sayTo.value = id
}

function onKey(event: KeyboardEvent): void {
  if (event.key === 'Tab' && !event.shiftKey && !text.value.trim() && suggestion.value) {
    event.preventDefault()
    text.value = suggestion.value
    return
  }
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    void submit()
  }
}

function lineClass(line: LogLine): string[] {
  return [`log__line`, `log__line--${line.kind}`, line.mine ? 'log__line--mine' : '']
}

/**
 * Lines that arrive after the page opened unfold one after another, so a
 * turn's answer reads like a story being told rather than a block appearing.
 */
const seen = new Set<string>()
let seeded = false
const reveal = computed(() => {
  const delays = new Map<string, number>()
  let order = 0
  for (const line of adv.log.value) {
    if (seen.has(line.key)) continue
    if (seeded) delays.set(line.key, order++ * 550)
  }
  return delays
})
watch(
  () => adv.log.value,
  (lines) => {
    // Remember after the reveal timing for this render has been read.
    void nextTick(() => {
      for (const line of lines) seen.add(line.key)
      seeded = true
    })
  }
)
function revealStyle(key: string): Record<string, string> {
  const delay = reveal.value.get(key)
  return delay ? { transitionDelay: `${delay}ms` } : {}
}

async function scrollToEnd(): Promise<void> {
  await nextTick()
  const el = logEl.value
  if (el) el.scrollTop = el.scrollHeight
}

watch(() => adv.log.value.length, scrollToEnd)
watch(
  () => adv.acting.value,
  (on) => {
    startedAt.value = on ? Date.now() : null
    void scrollToEnd()
  }
)
// The dropdown always shows who will hear you: never a blank that
// silently falls back to the first person here.
watch(
  () => adv.talkable.value.map((c) => c.character_id).join(','),
  () => {
    const ids = adv.talkable.value.map((c) => c.character_id)
    if (!ids.includes(sayTo.value)) sayTo.value = ids[0] ?? ''
  },
  { immediate: true }
)
watch(canSay, (yes) => {
  if (!yes && mode.value === 'say') mode.value = 'do'
})

let clock: ReturnType<typeof setInterval> | undefined
function onVisibility(): void {
  if (document.visibilityState === 'visible') adv.onVisible()
}
onUnmounted(() => {
  if (clock !== undefined) clearInterval(clock)
  document.removeEventListener('visibilitychange', onVisibility)
})
onMounted(() => {
  void adv.load().then(() => {
    // Portraits load after the first layout and push the end out of view.
    void scrollToEnd()
    setTimeout(() => void scrollToEnd(), 600)
  })
  clock = setInterval(() => (now.value = Date.now()), 1000)
  document.addEventListener('visibilitychange', onVisibility)
})
</script>

<template>
  <main class="adv">
    <header class="adv__bar">
      <RouterLink class="adv__back" to="/stories"><IconArrowLeft :size="16" /> Stories</RouterLink>
      <div class="adv__title">
        <h1>{{ adv.title.value ?? 'Adventure' }}</h1>
      </div>
      <nav class="adv__links">
        <RouterLink :to="{ name: 'story-watch', params: { storyId } }"
          ><IconGlobe :size="16" /> World map</RouterLink
        >
        <RouterLink :to="{ name: 'story-play', params: { storyId } }"
          ><IconBook :size="16" /> Story room</RouterLink
        >
        <RouterLink :to="{ name: 'story-settings', params: { storyId } }"
          ><IconGear :size="16" /> Story settings</RouterLink
        >
      </nav>
    </header>

    <p v-if="adv.loading.value" class="adv__note">Opening the story…</p>
    <section v-else-if="!adv.me.value" class="adv__note ev-card">
      <h2>This story is watched, not played.</h2>
      <p>
        Nobody here is yours to play. Watch it unfold on the
        <RouterLink :to="{ name: 'story-watch', params: { storyId } }">world map</RouterLink>, or
        start a new story as a player.
      </p>
    </section>

    <!-- one card: the picture, map and lead beside the story, who you are along the foot -->
    <div v-else class="adv__frame ev-card">
      <div class="adv__grid">
        <!-- left: what you see, the land around you, and the thread to pull -->
        <section class="adv__visual">
          <div class="stage">
            <img
              v-if="latest && latestUrl"
              class="stage__img"
              :src="latestUrl"
              :alt="latest.caption" />
            <div v-else class="stage__img" :style="sceneStyle" />
            <div
              v-if="light"
              class="scene__light"
              :style="{ background: light }"
              aria-hidden="true" />
            <div class="stage__shade" aria-hidden="true" />
            <span v-if="latest" class="stage__badge">
              Latest illustrated moment<template v-if="latestElsewhere">
                · {{ latestElsewhere }}</template
              >
            </span>
            <button
              v-if="latest"
              type="button"
              class="stage__expand"
              :title="`Open “${momentTitle(latest)}”`"
              aria-label="Open this moment"
              @click="openMoment()">
              <IconExpand :size="18" />
            </button>
            <div class="stage__foot">
              <div class="stage__where">
                <h2 class="scene__place">{{ adv.here.value?.name ?? 'On the road' }}</h2>
                <p class="stage__when">
                  {{ timeLabel
                  }}<template v-if="adv.present.value.length === 0">
                    · No one else is here</template
                  >
                </p>
              </div>
              <ul class="scene__people" aria-label="Here with you">
                <li v-for="c in adv.present.value" :key="c.character_id">
                  <button
                    type="button"
                    class="who"
                    :title="`Talk to ${c.name}`"
                    @click="talkTo(c.character_id)">
                    <FramedImage
                      v-if="portraits.get(c.character_id)"
                      :src="portraits.get(c.character_id)!.src"
                      :frame="portraits.get(c.character_id)!.face" />
                    <span v-else>{{ initials(c.name) }}</span>
                    <small>{{ c.name }}</small>
                  </button>
                </li>
                <li class="who who--me" :title="`${myName} (you)`">
                  <FramedImage
                    v-if="portraits.get(adv.me.value)"
                    :src="portraits.get(adv.me.value)!.src"
                    :frame="portraits.get(adv.me.value)!.face" />
                  <span v-else>{{ initials(myName) }}</span>
                  <small>You</small>
                </li>
              </ul>
            </div>
          </div>
          <div class="adv__under">
            <section v-if="adv.presentation.value" class="minimap">
              <header class="minimap__head">
                <div class="maptabs" role="tablist" aria-label="Which map">
                  <button
                    type="button"
                    role="tab"
                    :aria-selected="mapTab === 'world'"
                    @click="mapTab = 'world'">
                    World map
                  </button>
                  <button
                    type="button"
                    role="tab"
                    :aria-selected="mapTab === 'local'"
                    @click="mapTab = 'local'">
                    Local map
                  </button>
                </div>
                <button
                  type="button"
                  class="minimap__expand"
                  :aria-label="`Open the ${mapTab === 'world' ? 'world' : 'local'} map full screen`"
                  :title="`Open the ${mapTab === 'world' ? 'world' : 'local'} map full screen`"
                  @click="mapOpen = true">
                  <IconExpand :size="15" />
                </button>
              </header>
              <div class="minimap__map">
                <WorldMap
                  v-if="mapTab === 'world'"
                  :world-id="storyId"
                  :map-asset-id="adv.mapAssetId.value"
                  :anchors="adv.presentation.value.manifest.anchors ?? []"
                  :places="adv.places.value"
                  :roads="adv.presentation.value.manifest.roads ?? []"
                  :tokens="tokens"
                  :active-place-id="adv.hereId.value"
                  :focus-id="adv.me.value"
                  compact />
                <PlaceMap
                  v-else-if="localMap"
                  bare
                  :world-id="storyId"
                  :place-map="localMap"
                  :place-name="adv.here.value?.name ?? 'Here'"
                  :cast="adv.presentation.value.cast ?? []"
                  :activities="adv.presentation.value.activities ?? []"
                  :scenes="adv.entries.value"
                  :focus-id="adv.me.value"
                  @select="talkTo" />
                <p v-else class="minimap__none">
                  {{
                    adv.here.value
                      ? `${adv.here.value.name} has no map of its own yet.`
                      : 'You are on the road.'
                  }}
                </p>
              </div>
            </section>
            <section class="lead">
              <h3 class="panel__title"><IconDoc :size="16" /> Current story lead</h3>
              <template v-if="mainLead">
                <p class="lead__title">
                  {{ mainLead.title }}
                  <span v-if="isFresh(mainLead.since_index, nowIndex)" class="rumours__new"
                    >new</span
                  >
                </p>
                <p v-if="mainLead.purpose" class="lead__text">{{ mainLead.purpose }}</p>
              </template>
              <p v-else class="lead__text lead__quiet">
                No word yet. Look around, or talk to someone.
              </p>
              <button
                v-if="otherLeads.length || settled.length"
                type="button"
                class="lead__more"
                :aria-expanded="leadsOpen"
                @click="leadsOpen = !leadsOpen">
                {{
                  leadsOpen
                    ? 'Show less'
                    : [
                        otherLeads.length ? `${otherLeads.length} more` : '',
                        settled.length ? `${settled.length} settled` : ''
                      ]
                        .filter(Boolean)
                        .join(' · ')
                }}
              </button>
              <div v-if="leadsOpen" class="rumours">
                <ul>
                  <li v-for="r in otherLeads" :key="r.hook_id">
                    <b>{{ r.title }}</b>
                    <p v-if="r.purpose">{{ r.purpose }}</p>
                  </li>
                </ul>
                <ul v-if="settled.length" class="rumours__done">
                  <li v-for="r in settled" :key="r.hook_id">
                    <b>✓ {{ r.title }}</b>
                  </li>
                </ul>
              </div>
            </section>
          </div>
        </section>

        <!-- right: the story, and what you do next -->
        <section class="adv__stage">
          <div ref="logEl" class="log" aria-live="polite">
            <div v-if="intro.length" class="log__intro">
              <p>{{ intro[0] }}</p>
              <details v-if="intro.length > 1" class="log__more">
                <summary>Character introduction</summary>
                <p v-for="(text, i) in intro.slice(1)" :key="i">{{ text }}</p>
              </details>
              <p v-if="adv.log.value.length === 0" class="log__hint">
                Type what you do below — or look around, speak to someone, or set out.
              </p>
            </div>
            <TransitionGroup name="line" tag="div" class="log__lines">
              <div
                v-for="line in adv.log.value"
                :key="line.key"
                :class="lineClass(line)"
                :style="revealStyle(line.key)">
                <template v-if="line.kind === 'time'">
                  <span class="log__time">{{ line.text }}</span>
                </template>
                <template v-else-if="line.kind === 'dialogue'">
                  <span class="log__face" :title="nameOf(line.speakerId)">
                    <FramedImage
                      v-if="line.speakerId && portraits.get(line.speakerId)"
                      :src="portraits.get(line.speakerId)!.src"
                      :frame="portraits.get(line.speakerId)!.face" />
                    <span v-else>{{ initials(nameOf(line.speakerId)) }}</span>
                  </span>
                  <div class="log__bubble">
                    <b>{{ line.mine ? 'You' : nameOf(line.speakerId) }}</b>
                    <span>{{ line.text }}</span>
                  </div>
                </template>
                <template v-else-if="line.kind === 'paint'">
                  <button
                    type="button"
                    class="log__paint"
                    title="Paint a picture of this scene"
                    @click="paintingScene = line.paintScene ?? null">
                    <IconImage :size="14" /> Paint this scene
                  </button>
                </template>
                <template v-else-if="line.kind === 'picture' && line.picture">
                  <button
                    v-if="line.picture.status === 'ready' && line.picture.asset_id"
                    type="button"
                    class="log__picture"
                    :title="`Open “${momentTitle(line.picture)}”`"
                    @click="openPicture(line.picture.picture_id)">
                    <img
                      :src="assetUrl(storyId, line.picture.asset_id)"
                      :alt="line.picture.caption"
                      loading="lazy" />
                    <span class="log__picture-text">
                      <b>{{ momentTitle(line.picture) }}</b>
                      <i>{{ line.picture.caption }}</i>
                    </span>
                  </button>
                  <div v-else class="log__picture log__picture--wait" role="status">
                    <span class="log__picture-wait"><IconImage :size="20" /></span>
                    <span class="log__picture-text"><i>Painting this moment…</i></span>
                  </div>
                </template>
                <template v-else-if="line.kind === 'elsewhere'">
                  <span class="log__elsewhere">
                    Meanwhile{{
                      line.placeId && placeNames.get(line.placeId)
                        ? ` at ${placeNames.get(line.placeId)}`
                        : ''
                    }}
                    —
                    {{
                      trimPlaceLead(line.text, line.placeId ? placeNames.get(line.placeId) : null)
                    }}
                  </span>
                </template>
                <template v-else>
                  <p class="log__prose">{{ line.text }}</p>
                </template>
              </div>
            </TransitionGroup>
            <div
              v-if="adv.acting.value && echo"
              class="log__echo"
              :class="echo.kind === 'say' ? 'log__line--dialogue log__line--mine' : ''">
              <template v-if="echo.kind === 'say'">
                <span class="log__face">
                  <FramedImage
                    v-if="portraits.get(adv.me.value)"
                    :src="portraits.get(adv.me.value)!.src"
                    :frame="portraits.get(adv.me.value)!.face" />
                  <span v-else>{{ initials(myName) }}</span>
                </span>
                <div class="log__bubble">
                  <b>You</b>
                  <span>{{ echo.text }}</span>
                </div>
              </template>
              <p v-else class="log__prose log__mine">{{ echo.text }}</p>
            </div>
            <TransitionGroup
              v-if="changes.length && !adv.acting.value"
              name="badge"
              tag="ul"
              class="log__changes"
              aria-label="What changed">
              <li
                v-for="(c, i) in changes"
                :key="c.text"
                :class="`badge badge--${c.tone}`"
                :style="{ transitionDelay: `${i * 120}ms` }">
                {{ c.text }}
              </li>
            </TransitionGroup>
            <div v-if="adv.acting.value" class="log__thinking">
              <IconFeather :size="18" class="log__quill" />
              <span>{{ adv.stage.value }}… {{ elapsed }} s</span>
            </div>
          </div>

          <form class="composer" @submit.prevent="submit">
            <div class="composer__row">
              <!-- Do or Say: one sliding switch beside the words -->
              <div class="composer__side">
                <div
                  class="composer__modes"
                  :class="{ 'composer__modes--say': mode === 'say' }"
                  role="radiogroup"
                  aria-label="How you act">
                  <span class="composer__thumb" aria-hidden="true"></span>
                  <button
                    type="button"
                    role="radio"
                    :aria-checked="mode === 'do'"
                    @click="mode = 'do'">
                    Do
                  </button>
                  <button
                    type="button"
                    role="radio"
                    :aria-checked="mode === 'say'"
                    :disabled="!canSay"
                    :title="canSay ? '' : 'No one here to talk to'"
                    @click="mode = 'say'">
                    Say
                  </button>
                </div>
                <label v-if="mode === 'say' && adv.talkable.value.length > 1" class="composer__to">
                  to
                  <select v-model="sayTo">
                    <option
                      v-for="c in adv.talkable.value"
                      :key="c.character_id"
                      :value="c.character_id">
                      {{ c.name }}
                    </option>
                  </select>
                </label>
              </div>
              <textarea
                v-model="text"
                class="composer__input"
                rows="2"
                maxlength="250"
                :placeholder="placeholder"
                :aria-description="suggestion ? `Press Tab to fill: ${suggestion}` : undefined"
                :disabled="adv.acting.value || !adv.alive.value"
                @keydown="onKey" />
              <div class="composer__buttons">
                <button type="submit" class="composer__act" :disabled="!ready">
                  Act <IconArrowRight :size="16" />
                </button>
                <button
                  type="button"
                  class="composer__wait"
                  :disabled="adv.acting.value || !adv.alive.value"
                  title="Let a moment pass"
                  @click="pass()">
                  <IconClock :size="15" /> Wait
                </button>
              </div>
            </div>
            <p v-if="adv.actionError.value" class="composer__error" role="alert">
              {{ adv.actionError.value }}
            </p>
          </form>
        </section>
      </div>

      <!-- who you are, always in view -->
      <footer class="status">
        <span class="status__face">
          <FramedImage
            v-if="portraits.get(adv.me.value)"
            :src="portraits.get(adv.me.value)!.src"
            :frame="portraits.get(adv.me.value)!.face" />
          <span v-else>{{ initials(myName) }}</span>
        </span>
        <b class="status__name">{{ myName }}</b>
        <span v-if="journey" class="status__level" :title="`${journey.renown} renown`"
          >Level {{ journey.level }} · {{ journey.title }}</span
        >
        <div class="bar bar--stamina status__bar">
          <span>Stamina</span>
          <div><i :style="{ width: `${barFraction(stats?.stamina) * 100}%` }" /></div>
          <b>{{ stats?.stamina ?? '–' }}</b>
        </div>
        <div class="bar bar--mana status__bar">
          <span>Mana</span>
          <div><i :style="{ width: `${barFraction(stats?.mana) * 100}%` }" /></div>
          <b>{{ stats?.mana ?? '–' }}</b>
        </div>
        <span v-if="!adv.alive.value" class="sheet__fallen">Fallen</span>
        <button type="button" class="status__details" @click="detailsOpen = true">
          <IconUser :size="16" /> Character details <IconChevronRight :size="14" />
        </button>
      </footer>
    </div>

    <!-- the full sheet: renown, drives, what you carry -->
    <div
      v-if="detailsOpen && adv.me.value"
      class="drawer"
      role="dialog"
      aria-modal="true"
      :aria-label="`${myName}: character details`"
      @click.self="detailsOpen = false"
      @keydown.esc="detailsOpen = false">
      <div class="drawer__panel">
        <button type="button" class="drawer__close" aria-label="Close" @click="detailsOpen = false">
          <IconX :size="18" />
        </button>
        <section class="sheet ev-card">
          <div class="sheet__head">
            <div class="sheet__portrait">
              <FramedImage
                v-if="portraits.get(adv.me.value)"
                :src="portraits.get(adv.me.value)!.src"
                :frame="portraits.get(adv.me.value)!.face" />
              <span v-else>{{ initials(myName) }}</span>
            </div>
            <div>
              <h2>{{ myName }}</h2>
              <p v-if="card?.pronouns">{{ card.pronouns }}</p>
              <p>{{ adv.here.value?.name ?? 'On the road' }}</p>
            </div>
          </div>
          <div v-if="journey" class="renown" :title="`${journey.renown} renown`">
            <div class="renown__head">
              <b>{{ journey.title }}</b>
              <span>Level {{ journey.level }}</span>
            </div>
            <div class="renown__bar"><i :style="{ width: `${levelFill * 100}%` }" /></div>
            <p class="renown__counts">
              {{ journey.places }} place{{ journey.places === 1 ? '' : 's' }} · {{ journey.people }}
              {{ journey.people === 1 ? 'person' : 'people' }} met · {{ journey.deeds }} deed{{
                journey.deeds === 1 ? '' : 's'
              }}
              · {{ journey.settled }} settled
            </p>
          </div>
          <div class="bars">
            <div class="bar bar--stamina">
              <span>Stamina</span>
              <div><i :style="{ width: `${barFraction(stats?.stamina) * 100}%` }" /></div>
              <b>{{ stats?.stamina ?? '–' }}</b>
            </div>
            <div class="bar bar--mana">
              <span>Mana</span>
              <div><i :style="{ width: `${barFraction(stats?.mana) * 100}%` }" /></div>
              <b>{{ stats?.mana ?? '–' }}</b>
            </div>
          </div>
          <p v-if="conditions.length" class="sheet__conditions">{{ conditions.join(' · ') }}</p>
          <p v-if="!adv.alive.value" class="sheet__fallen">
            {{ myName }} has fallen. The story goes on without you.
          </p>
          <template v-if="drives.length">
            <h3>What drives you</h3>
            <ul class="sheet__drives">
              <li v-for="d in drives" :key="d">
                <b>{{ d.slice(0, d.indexOf(':') + 1) }}</b
                >{{ d.slice(d.indexOf(':') + 1) }}
              </li>
            </ul>
          </template>
          <h3><IconSatchel :size="16" /> Carrying</h3>
          <ul v-if="adv.items.value.length" class="sheet__items">
            <li v-for="item in adv.items.value" :key="item.id" :title="item.description">
              {{ item.name || item.item_key
              }}<span v-if="item.quantity > 1"> ×{{ item.quantity }}</span>
            </li>
          </ul>
          <p v-else class="sheet__empty">Empty pockets.</p>
        </section>
      </div>
    </div>

    <div
      v-if="mapOpen && adv.presentation.value"
      class="mapdlg"
      role="dialog"
      aria-modal="true"
      :aria-label="mapTab === 'world' ? 'World map' : 'Local map'"
      @click.self="mapOpen = false"
      @keydown.esc="mapOpen = false">
      <div class="mapdlg__card">
        <header class="mapdlg__head">
          <div class="maptabs" role="tablist" aria-label="Which map">
            <button
              type="button"
              role="tab"
              :aria-selected="mapTab === 'world'"
              @click="mapTab = 'world'">
              World map
            </button>
            <button
              type="button"
              role="tab"
              :aria-selected="mapTab === 'local'"
              @click="mapTab = 'local'">
              Local map
            </button>
          </div>
          <h2 class="mapdlg__title">
            {{
              mapTab === 'world'
                ? (adv.title.value ?? 'The world')
                : (adv.here.value?.name ?? 'Here')
            }}
          </h2>
          <button type="button" class="mapdlg__close" aria-label="Close" @click="mapOpen = false">
            <IconX :size="20" />
          </button>
        </header>
        <div class="mapdlg__body">
          <WorldMap
            v-if="mapTab === 'world'"
            :world-id="storyId"
            :map-asset-id="adv.mapAssetId.value"
            :anchors="adv.presentation.value.manifest.anchors ?? []"
            :places="adv.places.value"
            :roads="adv.presentation.value.manifest.roads ?? []"
            :tokens="tokens"
            :active-place-id="adv.hereId.value"
            :focus-id="adv.me.value" />
          <PlaceMap
            v-else-if="localMap"
            bare
            :world-id="storyId"
            :place-map="localMap"
            :place-name="adv.here.value?.name ?? 'Here'"
            :cast="adv.presentation.value.cast ?? []"
            :activities="adv.presentation.value.activities ?? []"
            :scenes="adv.entries.value"
            :focus-id="adv.me.value"
            @select="talkTo" />
          <p v-else class="minimap__none">
            {{
              adv.here.value
                ? `${adv.here.value.name} has no map of its own yet.`
                : 'You are on the road.'
            }}
          </p>
        </div>
      </div>
    </div>

    <MomentDialog
      v-if="adv.me.value"
      :world-id="storyId"
      :moments="moments"
      :index="openedMoment"
      :speakers="speakers"
      :places="placeNames"
      :opts="adv.opts.value"
      @update:index="openedMoment = $event"
      @repainted="adv.onVisible()"
      @close="openedMoment = null" />
    <PaintSceneDialog
      :world-id="storyId"
      :scene-id="paintingScene"
      :opts="adv.opts.value"
      @close="paintingScene = null"
      @painted="adv.onVisible()" />
  </main>
</template>

<style scoped>
.adv {
  max-width: 1440px;
  margin: 0 auto;
  padding: 10px 16px 10px;
  /* one screen: the story scrolls inside, the bars stay in view */
  height: calc(100vh - 62px);
  min-height: 640px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.adv__bar {
  flex: none;
  display: flex;
  align-items: center;
  gap: 18px;
}
.adv__back,
.adv__links a {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--teal-ink);
  font-size: 15px;
}
.adv__title {
  flex: 1;
  min-width: 0;
}
.adv__title h1 {
  font-family: var(--font-display);
  font-size: 26px;
  font-weight: 600;
  color: var(--ink);
  line-height: 1.1;
}
.adv__title p {
  color: var(--muted);
  font-size: 14px;
}
.adv__links {
  display: flex;
  gap: 18px;
}
.adv__note {
  max-width: 640px;
  margin: 60px auto;
  padding: 28px;
  text-align: center;
  color: var(--ink-3);
}
.adv__note h2 {
  font-family: var(--font-display);
  color: var(--ink);
  margin-bottom: 8px;
}
.adv__note a {
  color: var(--teal-ink);
  text-decoration: underline;
}
/* One card holds everything; its parts are divided by hairlines, not gaps. */
.adv__frame {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  padding: 0;
  overflow: hidden;
}
/* one clean edge: no inner frame line on this card */
.adv__frame::after {
  display: none;
}
.adv__grid {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: minmax(0, 0.9fr) minmax(0, 1.1fr);
}
.adv__visual {
  min-height: 0;
  display: grid;
  grid-template-rows: minmax(0, 1fr) clamp(170px, 23vh, 220px);
  border-right: 1px solid var(--line);
}
.adv__stage {
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* The picture --------------------------------------------------------------- */
.stage {
  position: relative;
  overflow: hidden;
  padding: 0;
  border-radius: 0;
  background: #3a3220;
}
.stage__img {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
  background-color: #6b7f55;
  background-repeat: no-repeat;
}
.stage__shade {
  position: absolute;
  inset: 0;
  background: linear-gradient(
    180deg,
    rgba(20, 15, 6, 0.35) 0%,
    transparent 22%,
    transparent 55%,
    rgba(20, 15, 6, 0.78) 100%
  );
  pointer-events: none;
}
.stage__badge {
  position: absolute;
  top: 14px;
  left: 14px;
  padding: 5px 11px;
  border-radius: 8px;
  background: rgba(24, 19, 9, 0.62);
  color: #f7efd9;
  font-family: var(--font-ui);
  font-size: 14px;
}
.stage__expand {
  position: absolute;
  top: 12px;
  right: 12px;
  display: grid;
  place-items: center;
  width: 36px;
  height: 36px;
  border-radius: 8px;
  background: rgba(24, 19, 9, 0.55);
  color: #f7efd9;
}
.stage__expand:hover {
  background: rgba(24, 19, 9, 0.8);
}
.stage__foot {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
  padding: 18px 20px;
  color: #f7efd9;
}
.stage__foot .scene__place {
  font-size: 40px;
}
.stage__when {
  font-size: 18px;
  text-shadow: 0 1px 4px rgba(0, 0, 0, 0.5);
}

/* Under the picture: the map and the lead ----------------------------------------- */
.adv__under {
  min-height: 0;
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  border-top: 1px solid var(--line);
}
.adv__under > .minimap {
  border-right: 1px solid var(--line-soft);
}
.panel__title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  font-family: var(--font-display);
  font-size: 20px;
  font-weight: 600;
  color: var(--ink);
}
.panel__title svg {
  color: var(--gold);
}
.minimap__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
}
.maptabs {
  display: inline-flex;
  padding: 3px;
  border-radius: 999px;
  border: 1px solid var(--line);
  background: var(--surface-2);
}
.maptabs [role='tab'] {
  padding: 4px 13px;
  border-radius: 999px;
  font-family: var(--font-ui);
  font-size: 14px;
  font-weight: 600;
  color: var(--ink-3);
}
.maptabs [role='tab'][aria-selected='true'] {
  background: var(--teal);
  color: var(--cream-on-teal);
}
.minimap__expand {
  display: grid;
  place-items: center;
  width: 30px;
  height: 30px;
  border-radius: 8px;
  border: 1px solid var(--line);
  color: var(--ink-3);
}
.minimap__expand:hover {
  color: var(--teal-ink);
  border-color: var(--gold-soft);
}
.minimap__none {
  padding: 12px;
  font-style: italic;
  color: var(--muted);
}
/* a place's own map fits the panel's height, centred */
.minimap__map :deep(.pm),
.mapdlg__body :deep(.pm) {
  height: 100%;
  display: flex;
  justify-content: center;
  border: 0;
  box-shadow: none;
  background: none;
}
.minimap__map :deep(.pm__frame),
.mapdlg__body :deep(.pm__frame) {
  height: 100%;
}
.minimap__map :deep(.pm__art),
.mapdlg__body :deep(.pm__art) {
  height: 100%;
  width: auto;
  max-width: none;
}
.mapdlg {
  position: fixed;
  inset: 0;
  z-index: 58;
  display: grid;
  place-items: center;
  padding: 24px;
  background: rgba(36, 29, 16, 0.55);
}
.mapdlg__card {
  display: flex;
  flex-direction: column;
  width: min(1400px, 100%);
  height: min(900px, calc(100vh - 48px));
  border-radius: 14px;
  overflow: hidden;
  border: 2px solid var(--gold-soft);
  background: var(--surface-2);
  box-shadow: 0 24px 60px rgba(30, 22, 8, 0.45);
}
.mapdlg__head {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--line);
}
.mapdlg__title {
  flex: 1;
  font-family: var(--font-display);
  font-size: 26px;
  font-weight: 600;
  color: var(--ink);
}
.mapdlg__close {
  display: inline-flex;
  padding: 6px;
  border-radius: 50%;
  color: var(--ink-3);
}
.mapdlg__close:hover {
  background: var(--panel-2);
}
.mapdlg__body {
  flex: 1;
  min-height: 0;
  overflow: auto;
  display: flex;
  justify-content: center;
}
.mapdlg__body > * {
  width: 100%;
  height: 100%;
}
.minimap {
  display: flex;
  flex-direction: column;
  min-height: 0;
  padding: 10px 12px 12px;
}
.minimap__map {
  flex: 1;
  min-height: 0;
  border-radius: 8px;
  overflow: hidden;
}
.lead {
  min-height: 0;
  padding: 10px 16px 14px;
  overflow-y: auto;
  scrollbar-width: thin;
}
.lead__title {
  font-family: var(--font-display);
  font-size: 22px;
  font-weight: 600;
  line-height: 1.15;
  color: var(--ink);
}
.lead__text {
  margin-top: 4px;
  font-size: 15.5px;
  line-height: 1.45;
  color: var(--ink-2);
}
.lead__quiet {
  font-style: italic;
  color: var(--muted);
}
.lead__more {
  margin-top: 8px;
  font-family: var(--font-ui);
  font-size: 14.5px;
  color: var(--teal-ink);
  text-decoration: underline;
  text-underline-offset: 3px;
}
.lead .rumours {
  margin-top: 8px;
  padding: 0;
}

/* The story ----------------------------------------------------------------------- */
.log__more summary {
  cursor: pointer;
  font-family: var(--font-ui);
  font-size: 15px;
  color: var(--teal-ink);
}
.log__more p {
  margin-top: 6px;
}

/* Who you are, along the foot ---------------------------------------------------- */
.status {
  flex: none;
  display: flex;
  align-items: center;
  gap: 22px;
  padding: 7px 16px;
  border-top: 1px solid var(--line);
  background: linear-gradient(180deg, var(--panel), var(--panel-2));
}
.status__face img,
.status__face > span {
  display: grid;
  place-items: center;
  width: 44px;
  height: 44px;
  border-radius: 50%;
  object-fit: cover;
  border: 2px solid var(--gold-soft);
  background: var(--teal);
  color: var(--cream-on-teal);
}
.status__face {
  flex: none;
  width: 44px;
  height: 44px;
  border-radius: 50%;
  overflow: hidden;
}
.status__name {
  font-family: var(--font-display);
  font-size: 22px;
  font-weight: 600;
  color: var(--ink);
}
.status__level {
  padding-left: 18px;
  border-left: 1px solid var(--line);
  font-family: var(--font-ui);
  font-size: 15.5px;
  color: var(--ink-2);
}
.status__bar {
  flex: 1;
  max-width: 340px;
}
.status__details {
  margin-left: auto;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-family: var(--font-ui);
  font-size: 15.5px;
  color: var(--teal-ink);
}
.status__details:hover {
  text-decoration: underline;
  text-underline-offset: 3px;
}

/* The full sheet, sliding in from the side ---------------------------------------- */
.drawer {
  position: fixed;
  inset: 0;
  z-index: 55;
  display: flex;
  justify-content: flex-end;
  background: rgba(36, 29, 16, 0.4);
}
.drawer__panel {
  position: relative;
  width: min(420px, 100%);
  height: 100%;
  overflow-y: auto;
  padding: 16px;
  background: var(--bg);
  box-shadow: -10px 0 30px rgba(30, 22, 8, 0.3);
  animation: drawer-in 0.25s var(--ease-out);
}
.drawer__close {
  position: absolute;
  top: 22px;
  right: 24px;
  z-index: 1;
  display: inline-flex;
  padding: 6px;
  border-radius: 50%;
  color: var(--ink-3);
}
.drawer__close:hover {
  background: var(--panel-2);
}
@keyframes drawer-in {
  from {
    transform: translateX(30px);
    opacity: 0;
  }
}

/* Scene banner ---------------------------------------------------------- */
.scene {
  position: relative;
  flex: none;
  height: 150px;
  background-color: #6b7f55;
  background-repeat: no-repeat;
  transition: background-position 1.2s ease;
  border-bottom: 1px solid var(--line);
}
.scene__light {
  position: absolute;
  inset: 0;
  mix-blend-mode: multiply;
  transition: background 2s ease;
}
.scene__shade {
  position: absolute;
  inset: 0;
  background: linear-gradient(
    90deg,
    rgba(30, 24, 12, 0.72) 0%,
    rgba(30, 24, 12, 0.35) 55%,
    rgba(30, 24, 12, 0.1) 100%
  );
}
.scene__body {
  position: relative;
  height: 100%;
  padding: 16px 22px;
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
  color: #f7efd9;
}
.scene__eyebrow {
  font-size: 12px;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  opacity: 0.85;
}
.scene__place {
  font-family: var(--font-display);
  font-size: 34px;
  font-weight: 600;
  line-height: 1.05;
  text-shadow: 0 2px 8px rgba(0, 0, 0, 0.45);
}
.scene__people {
  list-style: none;
  display: flex;
  gap: 12px;
}
.scene__alone {
  font-size: 13px;
  opacity: 0.8;
  margin-top: 4px;
}
.who {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  color: #f7efd9;
}
.who img,
.who > span {
  width: 56px;
  height: 56px;
  border-radius: 50%;
  object-fit: cover;
  border: 2px solid #f1e3bd;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.4);
  background: var(--teal);
  display: grid;
  place-items: center;
  font-size: 15px;
  transition: transform 0.15s ease;
}
button.who:hover img,
button.who:hover > span {
  transform: translateY(-2px) scale(1.05);
}
.who small {
  font-size: 12px;
  text-shadow: 0 1px 4px rgba(0, 0, 0, 0.6);
}
.who--me img,
.who--me > span {
  border-color: #e8c66f;
}

/* Story log ------------------------------------------------------------- */
.log {
  flex: 1;
  overflow-y: auto;
  padding: 12px 24px 8px;
  scroll-behavior: smooth;
}
.log__intro {
  border: 1px solid var(--line-soft);
  border-radius: 10px;
  background: linear-gradient(180deg, rgba(255, 252, 240, 0.7), rgba(246, 236, 212, 0.5));
  padding: 14px 18px;
  margin-bottom: 12px;
  font-size: 17px;
  line-height: 1.55;
  color: var(--ink-2);
  font-style: italic;
}
.log__intro p:first-child {
  font-style: normal;
  font-family: var(--font-display);
  font-size: 22px;
  color: var(--ink);
}
.log__hint {
  margin-top: 8px;
  color: var(--teal-ink);
  font-size: 15px;
}
.log__empty {
  color: var(--muted);
  font-style: italic;
  text-align: center;
  margin-top: 30px;
}
.log__lines {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.log__line--time {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 10px 0 2px;
}
.log__line--time::before,
.log__line--time::after {
  content: '';
  flex: 1;
  height: 1px;
  background: var(--line-soft);
}
.log__time {
  font-size: 12px;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: var(--gold);
}
.log__prose {
  font-size: 18px;
  line-height: 1.6;
  color: var(--ink);
  max-width: 68ch;
}
.log__paint {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-top: -4px;
  padding: 3px 10px;
  border-radius: 999px;
  border: 1px solid transparent;
  font-size: 13px;
  color: var(--muted);
  opacity: 0.75;
  transition:
    opacity 0.15s ease,
    border-color 0.15s ease,
    color 0.15s ease;
}
.log__paint:hover,
.log__paint:focus-visible {
  opacity: 1;
  color: var(--teal-ink);
  border-color: var(--line);
  background: #fbf6e9;
}
/* pictures in the story are small: the large one is beside it */
.log__picture {
  display: flex;
  align-items: center;
  gap: 14px;
  width: 100%;
  max-width: 560px;
  margin: 6px 0 4px;
  padding: 6px;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: #fbf6e9;
  text-align: left;
}
button.log__picture:hover {
  border-color: var(--gold-soft);
}
.log__picture img,
.log__picture-wait {
  flex: none;
  width: 150px;
  aspect-ratio: 16 / 9;
  border-radius: 8px;
  object-fit: cover;
}
.log__picture-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
.log__picture-text b {
  font-family: var(--font-display);
  font-size: 18px;
  font-weight: 600;
  color: var(--ink);
}
.log__picture-text i {
  font-size: 14.5px;
  color: var(--ink-2);
}
.log__picture-wait {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  color: var(--muted);
  font-style: italic;
  background: linear-gradient(110deg, #f3ead3 30%, #fbf6e9 50%, #f3ead3 70%);
  background-size: 250% 100%;
  animation: shimmer 2.2s linear infinite;
}

@keyframes shimmer {
  to {
    background-position: -150% 0;
  }
}
@media (prefers-reduced-motion: reduce) {
  .log__picture-wait {
    animation: none;
  }
}
.log__line--pending .log__prose {
  color: var(--muted);
  font-style: italic;
  animation: breathe 1.6s ease-in-out infinite;
}
.log__line--dialogue {
  display: flex;
  align-items: flex-end;
  gap: 10px;
}
.log__line--mine {
  flex-direction: row-reverse;
}
.log__face img,
.log__face > span {
  width: 38px;
  height: 38px;
  border-radius: 50%;
  object-fit: cover;
  border: 1px solid var(--line-strong);
  background: var(--panel-2);
  display: grid;
  place-items: center;
  font-size: 13px;
  color: var(--ink-3);
}
.log__bubble {
  max-width: 70%;
  background: var(--surface-2);
  border: 1px solid var(--line);
  border-radius: 14px 14px 14px 4px;
  padding: 8px 14px;
  font-size: 17px;
  line-height: 1.45;
  color: var(--ink);
  box-shadow: var(--card-shadow);
}
.log__bubble b {
  display: block;
  font-size: 12px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--gold);
  font-weight: 600;
}
.log__line--mine .log__bubble {
  background: var(--teal);
  border-color: var(--teal-hi);
  color: var(--cream-on-teal);
  border-radius: 14px 14px 4px 14px;
}
.log__line--mine .log__bubble b {
  color: #e8c66f;
}
.log__elsewhere {
  display: block;
  font-size: 14.5px;
  font-style: italic;
  color: var(--muted);
  padding-left: 12px;
  border-left: 2px solid var(--line-soft);
}
.log__echo {
  margin-top: 10px;
  opacity: 0.75;
}
.log__echo.log__line--dialogue {
  display: flex;
  align-items: flex-end;
  gap: 10px;
  flex-direction: row-reverse;
}
.log__mine {
  font-style: italic;
  color: var(--teal-ink);
}
.log__changes {
  list-style: none;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin: 12px 0 4px;
}
.badge {
  font-size: 13.5px;
  padding: 2px 10px;
  border-radius: 99px;
  border: 1px solid var(--line);
  background: var(--surface-2);
}
.badge--gain {
  color: #2f6b3a;
  border-color: #9cc2a3;
  background: #eef6ec;
}
.badge--loss {
  color: #8a3b2b;
  border-color: #d7a99c;
  background: #f8ece6;
}
.badge--level {
  color: #fff8e6;
  border-color: #b8913f;
  background: linear-gradient(90deg, #a07a2f, #d0a64e);
  font-weight: 600;
  box-shadow: 0 0 0 0 rgba(208, 166, 78, 0.6);
  animation: levelup 1.6s ease-out 2;
}
@keyframes levelup {
  70% {
    box-shadow: 0 0 0 10px rgba(208, 166, 78, 0);
  }
}
.badge--news {
  color: var(--gold);
  border-color: var(--gold-soft);
}
.badge-enter-active {
  transition:
    opacity 0.4s ease,
    transform 0.4s ease;
}
.badge-enter-from {
  opacity: 0;
  transform: scale(0.85);
}
.log__thinking {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 14px 0 4px;
  color: var(--teal-ink);
  font-style: italic;
}
.log__quill {
  animation: write 1.1s ease-in-out infinite;
}
.line-enter-active {
  transition:
    opacity 0.5s ease,
    transform 0.5s ease;
}
.line-enter-from {
  opacity: 0;
  transform: translateY(8px);
}
@keyframes breathe {
  50% {
    opacity: 0.45;
  }
}
@keyframes write {
  0%,
  100% {
    transform: rotate(-8deg) translateX(0);
  }
  50% {
    transform: rotate(6deg) translateX(4px);
  }
}

/* Composer --------------------------------------------------------------- */
.composer {
  flex: none;
  border-top: 1px solid var(--line);
  background: linear-gradient(180deg, var(--panel), var(--panel-2));
  padding: 8px 14px 10px;
}
.composer__side {
  flex: none;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
}
/* a two-way switch: the teal thumb slides under the chosen word */
.composer__modes {
  position: relative;
  display: grid;
  grid-template-rows: 1fr 1fr;
  width: 64px;
  padding: 3px;
  border-radius: 18px;
  border: 1px solid var(--line);
  background: var(--surface-2);
  box-shadow: inset 0 1px 2px rgba(96, 74, 40, 0.12);
}
.composer__thumb {
  position: absolute;
  top: 3px;
  left: 3px;
  right: 3px;
  height: calc(50% - 3px);
  border-radius: 15px;
  background: linear-gradient(180deg, var(--teal-hi), var(--teal));
  box-shadow: 0 1px 3px rgba(16, 46, 46, 0.35);
  transition: transform 0.25s var(--ease-out);
}
.composer__modes--say .composer__thumb {
  transform: translateY(100%);
}
.composer__modes [role='radio'] {
  position: relative;
  z-index: 1;
  padding: 7px 0;
  border-radius: 15px;
  font-family: var(--font-ui);
  font-size: 15px;
  font-weight: 600;
  color: var(--ink-3);
  transition: color 0.2s ease;
}
.composer__modes [role='radio'][aria-checked='true'] {
  color: var(--cream-on-teal);
}
.composer__modes [role='radio']:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}
.composer__to {
  font-size: 14px;
  color: var(--ink-3);
  display: inline-flex;
  gap: 6px;
  align-items: center;
}
.composer__to select {
  font: inherit;
  background: var(--surface-2);
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: 1px 6px;
}
.composer__row {
  display: flex;
  gap: 10px;
}
.composer__input {
  flex: 1;
  resize: none;
  font: inherit;
  font-size: 17px;
  color: var(--ink);
  background: var(--surface-2);
  border: 1px solid var(--line-strong);
  border-radius: 10px;
  padding: 9px 12px;
}
.composer__input:focus-visible {
  outline: 2px solid var(--teal-ink);
}
.composer__buttons {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.composer__act {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  background: linear-gradient(180deg, var(--teal-hi), var(--teal));
  color: var(--cream-on-teal);
  border-radius: 10px;
  padding: 8px 18px;
  font-size: 17px;
  box-shadow: var(--card-shadow);
}
.composer__wait {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 4px 10px;
  font-size: 14px;
  color: var(--ink-3);
}
.composer__act:disabled,
.composer__wait:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.composer__error {
  margin-top: 6px;
  color: #9a3b2b;
  font-size: 14px;
}

/* Side ------------------------------------------------------------------- */
.adv__side {
  display: flex;
  flex-direction: column;
  gap: 16px;
  /* as tall as the story beside it: the column scrolls on its own, so
     the page never runs on past the story */
  height: calc(100vh - 150px);
  min-height: 560px;
  overflow-y: auto;
  overscroll-behavior: contain;
  scrollbar-width: thin;
  scrollbar-color: var(--line-strong) transparent;
  padding: 0 4px 2px 0;
}
.adv__side > * {
  flex: none;
}
.sheet {
  padding: 16px 18px;
}
.sheet__head {
  display: flex;
  gap: 14px;
  align-items: center;
}
.sheet__portrait img,
.sheet__portrait > span {
  width: 86px;
  height: 86px;
  border-radius: 12px;
  object-fit: cover;
  border: 2px solid var(--gold-soft);
  background: var(--teal);
  color: var(--cream-on-teal);
  display: grid;
  place-items: center;
  font-size: 26px;
}
.sheet__head h2 {
  font-family: var(--font-display);
  font-size: 26px;
  color: var(--ink);
  line-height: 1.1;
}
.sheet__head p {
  color: var(--muted);
  font-size: 14px;
}
.renown {
  margin-top: 12px;
}
.renown__head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  font-size: 14px;
}
.renown__head b {
  font-family: var(--font-display);
  font-size: 18px;
  color: var(--gold);
}
.renown__head span {
  color: var(--muted);
}
.renown__bar {
  height: 6px;
  border-radius: 99px;
  background: var(--line-soft);
  overflow: hidden;
  margin: 4px 0 3px;
}
.renown__bar i {
  display: block;
  height: 100%;
  background: linear-gradient(90deg, #b8913f, #e4bf68);
  transition: width 1s ease;
}
.renown__counts {
  font-size: 12.5px;
  color: var(--muted);
}
.bars {
  margin: 14px 0 6px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.bar {
  display: grid;
  grid-template-columns: 62px 1fr 28px;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--ink-3);
}
.bar div {
  height: 8px;
  border-radius: 99px;
  background: var(--line-soft);
  overflow: hidden;
}
.bar i {
  display: block;
  height: 100%;
  border-radius: 99px;
  transition: width 0.8s ease;
}
.bar--stamina i {
  background: linear-gradient(90deg, #b5803a, #d6a14d);
}
.bar--mana i {
  background: linear-gradient(90deg, #2f6f8f, #4f95b5);
}
.bar b {
  font-weight: 500;
  text-align: right;
}
.sheet h3 {
  display: flex;
  align-items: center;
  gap: 6px;
  font-family: var(--font-display);
  font-size: 18px;
  color: var(--ink);
  margin: 12px 0 4px;
}
.sheet__items {
  list-style: none;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.sheet__items li {
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 2px 8px;
  font-size: 14px;
  background: var(--surface-2);
}
.sheet__empty,
.sheet__conditions {
  color: var(--muted);
  font-size: 14px;
  font-style: italic;
}
.sheet__fallen {
  margin-top: 8px;
  color: #9a3b2b;
}
.sheet__drives {
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 3px;
  font-size: 14.5px;
  color: var(--ink-2);
}
.rumours {
  padding: 14px 18px;
}
.rumours h3 {
  font-family: var(--font-display);
  font-size: 18px;
  color: var(--ink);
  margin-bottom: 6px;
}
.rumours ul {
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.rumours li {
  font-size: 14.5px;
  border-left: 2px solid var(--line);
  padding-left: 10px;
}
.rumours li.fresh {
  border-left-color: var(--gold);
  animation: glow 2.4s ease-in-out 2;
}
.rumours b {
  color: var(--ink);
  font-weight: 600;
}
.rumours p {
  color: var(--ink-3);
  margin-top: 2px;
}
.rumours__done-title {
  margin-top: 10px;
}
.rumours__done li {
  border-left-color: #9cc2a3;
}
.rumours__done b {
  color: #2f6b3a;
}
.rumours__new {
  margin-left: 6px;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  color: var(--cream-on-teal);
  background: var(--gold);
  border-radius: 99px;
  padding: 1px 7px;
}
@keyframes glow {
  50% {
    background: rgba(232, 198, 111, 0.18);
  }
}
.minimap {
  padding: 6px;
  overflow: hidden;
}

@media (max-width: 1100px) {
  .adv {
    height: auto;
  }
  .adv__grid {
    grid-template-columns: 1fr;
  }
  .adv__frame {
    overflow: visible;
  }
  .adv__visual {
    grid-template-rows: auto auto;
    border-right: 0;
    border-top: 1px solid var(--line);
  }
  .stage {
    aspect-ratio: 16 / 10;
  }
  .adv__under {
    min-height: 220px;
  }
  /* The story fills the screen with the composer always in reach. */
  .adv__stage {
    order: -1;
    height: calc(100dvh - 260px);
    min-height: 420px;
  }
  .status {
    position: sticky;
    bottom: 0;
    z-index: 4;
    border-radius: 0 0 var(--radius-card) var(--radius-card);
    flex-wrap: wrap;
    gap: 8px 16px;
  }
  .status__bar {
    flex: 1 1 140px;
  }
}
@media (max-width: 960px) {
  .adv {
    padding: 8px 8px 16px;
  }
  .adv__under {
    grid-template-columns: 1fr;
  }
  .stage__foot .scene__place {
    font-size: 28px;
  }
  .status__level {
    display: none;
  }
  .scene {
    height: 118px;
  }
  .scene__place {
    font-size: 26px;
  }
  .who img,
  .who > span {
    width: 40px;
    height: 40px;
  }
  .log {
    padding: 12px 14px 8px;
  }
  .log__prose {
    font-size: 16.5px;
  }
  .log__bubble {
    max-width: 85%;
  }
  .adv__links {
    display: none;
  }
}
</style>
