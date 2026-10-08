<script setup lang="ts">
import { computed, nextTick, onActivated, onMounted, onUnmounted, ref } from 'vue'
import type { Component } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { catalog, libraryUi, resetLibraryFilters } from '../game/catalog'
import { filterCharactersLibrary, filterPacks, filterWorlds } from '../game/filters'
import { toLibraryCharacter, toLibraryWorld, usePresets } from '../composables/usePresets'
import { duplicatePreset, setPresetArchived } from '../api/worldsim'
import type { CardMenuItem } from '../components/ui/CardMenu.vue'
import { useGameImage } from '../game/images'
import { useRouteQueryTab } from '../game/useTab'
import LibTabBar from '../components/library/LibTabBar.vue'
import CharacterLibCard from '../components/library/CharacterLibCard.vue'
import WorldLibCard from '../components/library/WorldLibCard.vue'
import PackLibCard from '../components/library/PackLibCard.vue'
import CreateLibTile from '../components/library/CreateLibTile.vue'
import SearchField from '../components/ui/SearchField.vue'
import ChipGroup from '../components/ui/ChipGroup.vue'
import SortSelect from '../components/ui/SortSelect.vue'
import ViewToggle from '../components/ui/ViewToggle.vue'
import IconArchive from '../components/icons/IconArchive.vue'
import IconGlobe from '../components/icons/IconGlobe.vue'
import IconPencil from '../components/icons/IconPencil.vue'
import IconStack from '../components/icons/IconStack.vue'
import IconGrid from '../components/icons/IconGrid.vue'
import IconList from '../components/icons/IconList.vue'
import IconSparkle from '../components/icons/IconSparkle.vue'
import EmberField from '../components/decor/EmberField.vue'
import { burst, flash } from '../composables/useEffects'

const route = useRoute()
const router = useRouter()
const tab = useRouteQueryTab(route, router, 'characters')

const bannerUrl = useGameImage('library.banner')

const viewOptions: { value: 'grid' | 'list'; label: string; short: string; icon: Component }[] = [
  { value: 'grid', label: 'Cards view', short: 'Cards', icon: IconGrid },
  { value: 'list', label: 'List view', short: 'List', icon: IconList }
]

/* Worlds and characters come from server presets (E3); style packs and
   templates stay on the local catalog until the backend models them. */
const presets = usePresets()
let presetAbort: AbortController | null = null
onMounted(() => {
  presetAbort = new AbortController()
  void presets.load(presetAbort.signal)
})
onUnmounted(() => presetAbort?.abort())
// Kept alive between visits: coming back refreshes quietly (usePresets
// only shows its loading line while it has nothing to show).
let opened = false
onActivated(() => {
  if (opened) retryPresets()
  opened = true
})

function retryPresets(): void {
  presetAbort?.abort()
  presetAbort = new AbortController()
  void presets.load(presetAbort.signal)
}

const tabs = computed(() => [
  { key: 'worlds', label: 'Worlds', count: presets.worlds.value.length },
  { key: 'characters', label: 'Characters', count: presets.characters.value.length },
  { key: 'style-packs', label: 'Style Packs · Preview', count: catalog.stylePacks.length },
  { key: 'templates', label: 'Templates · Preview', count: catalog.templates.length }
])

interface TabConfig {
  search: string
  chips: { value: string; label: string }[]
}

const configs: Record<string, TabConfig> = {
  characters: {
    search: 'Search your library…',
    chips: [
      { value: 'all', label: 'All' },
      { value: 'player', label: 'Player-ready' },
      { value: 'npc', label: 'NPC' }
    ]
  },
  worlds: {
    search: 'Search worlds…',
    chips: [
      { value: 'all', label: 'All' },
      { value: 'ready', label: 'Ready to use' },
      { value: 'draft', label: 'Drafts' }
    ]
  },
  'style-packs': {
    search: 'Search style packs…',
    chips: []
  },
  templates: {
    search: 'Search templates…',
    chips: []
  }
}

const config = computed(() => configs[tab.value] ?? configs.characters!)

/* Filtering + sorting live in game/filters.ts (pure, unit-tested). */
const libFilter = computed(() => ({
  search: libraryUi.search,
  chip: libraryUi.chip,
  sort: libraryUi.sort
}))

const characters = computed(() =>
  filterCharactersLibrary(presets.characters.value.map(toLibraryCharacter), libFilter.value)
)
const worlds = computed(() =>
  filterWorlds(presets.worlds.value.map(toLibraryWorld), libFilter.value)
)
const packs = computed(() => filterPacks(catalog.stylePacks, libFilter.value))
const templates = computed(() => filterPacks(catalog.templates, libFilter.value))

/* Server tabs offer no Recently Updated: the preset contract carries
   no update timestamp, and a revision number is not a recency key. */
const serverTab = computed(() => tab.value === 'characters' || tab.value === 'worlds')
const sortOptions = computed(() =>
  serverTab.value
    ? [{ value: 'name', label: 'Name' }]
    : [
        { value: 'recent', label: 'Recently Updated' },
        { value: 'name', label: 'Name' }
      ]
)

function setTab(key: string): void {
  resetLibraryFilters()
  tab.value = key
  if ((key === 'characters' || key === 'worlds') && libraryUi.sort !== 'name') {
    libraryUi.sort = 'name'
  }
}

/* The default tab is server-backed, while the shared default sort is not. */
if (serverTab.value && libraryUi.sort !== 'name') libraryUi.sort = 'name'

/* card menus ------------------------------------------------------------------ */
const notice = ref<{ text: string; undo?: () => void } | null>(null)
let noticeTimer: ReturnType<typeof setTimeout> | undefined
function tell(text: string, undo?: () => void): void {
  notice.value = { text, undo }
  clearTimeout(noticeTimer)
  noticeTimer = setTimeout(() => (notice.value = null), 7000)
}

function presetOf(kind: 'character' | 'world', id: string) {
  return kind === 'world'
    ? presets.worlds.value.find((w) => w.id === id)
    : presets.characters.value.find((c) => c.id === id)
}

function menuFor(kind: 'character' | 'world', id: string): CardMenuItem[] {
  const items: CardMenuItem[] = [{ key: 'open', label: 'Open in the studio', icon: IconPencil }]
  if (kind === 'world') items.push({ key: 'map', label: 'Draw the map', icon: IconGlobe })
  items.push({ key: 'copy', label: 'Make a copy', icon: IconStack })
  if (!presetOf(kind, id)?.builtin)
    items.push({ key: 'archive', label: 'Archive', icon: IconArchive, danger: true })
  return items
}

async function onPick(kind: 'character' | 'world', id: string, key: string): Promise<void> {
  const preset = presetOf(kind, id)
  if (!preset) return
  if (key === 'open') return kind === 'world' ? openWorld(id) : openCharacter(id)
  if (key === 'map') return void router.push(`/library/world/${id}/map`)
  try {
    if (key === 'copy') {
      const copy = await duplicatePreset(id)
      await presets.load()
      tell(`Made “${copy.name}”.`)
      // the new card glows and throws a few sparks where it lands
      await nextTick()
      const card = document.querySelector(`[data-preset="${copy.id}"]`)
      card?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
      flash(card)
      burst(card, { count: 12 })
    } else if (key === 'archive') {
      const done = await setPresetArchived(id, true, preset.version)
      await presets.load()
      tell(`Archived “${preset.name}”.`, () => void restore(id, done.version, preset.name))
    }
  } catch (err) {
    tell(err instanceof Error ? err.message : 'That did not work — try again.')
  }
}

async function restore(id: string, version: number, name: string): Promise<void> {
  try {
    await setPresetArchived(id, false, version)
    await presets.load()
    tell(`“${name}” is back.`)
    await nextTick()
    flash(document.querySelector(`[data-preset="${id}"]`))
  } catch (err) {
    tell(err instanceof Error ? err.message : 'Could not bring it back.')
  }
}

/** A card leaving the grid lifts out of the flow so the rest glide into place. */
function pinLeaving(el: Element): void {
  const e = el as HTMLElement
  e.style.width = `${e.offsetWidth}px`
  e.style.height = `${e.offsetHeight}px`
  e.style.left = `${e.offsetLeft}px`
  e.style.top = `${e.offsetTop}px`
}

/** Studios are shared pages — the library opens its own flavor of each. */
function openCharacter(id: string): void {
  router.push(`/library/character/${id}`)
}
function openWorld(id: string): void {
  router.push(`/library/world/${id}`)
}
</script>

<template>
  <main class="lib">
    <!-- banner ---------------------------------------------------------------- -->
    <section class="lib__banner ev-card">
      <img class="lib__art" :src="bannerUrl" alt="" aria-hidden="true" />
      <div class="lib__fade" aria-hidden="true"></div>
      <EmberField class="lib__dust" tone="dust" :count="12" :rise="180" />
      <div class="lib__banner-body">
        <div class="lib__heading ev-rise">
          <span class="ev-eyebrow"><IconSparkle :size="13" /> Your creative archive</span>
          <h1 class="lib__title">Library</h1>
          <p class="lib__sub">
            Build the places, people, and storytelling styles you can reuse across adventures.
          </p>
        </div>
      </div>
    </section>

    <!-- tabs, joined to the shelf they open ------------------------------------ -->
    <section
      class="lib__panel ev-card"
      :class="{ 'lib--list': libraryUi.view === 'list' }"
      :aria-label="`Library — ${tab}`">
      <LibTabBar :tabs="tabs" :model-value="tab" @update="setTab" />
      <div class="lib__shelf">
        <div class="lib__toolbar">
          <SearchField
            v-model="libraryUi.search"
            :placeholder="config.search"
            class="lib__search" />
          <ChipGroup v-if="config.chips.length" v-model="libraryUi.chip" :options="config.chips" />
          <span class="lib__spacer"></span>
          <SortSelect v-model="libraryUi.sort" label="Sort:" :options="sortOptions" />
          <ViewToggle v-model="libraryUi.view" label="View mode" :options="viewOptions" />
        </div>

        <Transition name="ev-swap" mode="out-in">
          <!-- characters -->
          <TransitionGroup
            v-if="tab === 'characters'"
            :key="`characters-${libraryUi.view}`"
            tag="div"
            name="ev-list"
            appear
            class="lib__cards lib__cards--people"
            @before-leave="pinLeaving">
            <p v-if="presets.loading.value" key="loading" class="lib__none" role="status">
              Reading the archive<span class="ev-dots" aria-hidden="true"
                ><span>.</span><span>.</span><span>.</span></span
              >
            </p>
            <p v-else-if="presets.error.value" key="error" class="lib__none" role="alert">
              The archive did not answer ({{ presets.error.value }}) —
              <button type="button" class="lib__link" @click="retryPresets()">retry</button>
            </p>
            <template v-else>
              <CharacterLibCard
                v-for="(c, i) in characters"
                :key="c.id"
                :data-preset="c.id"
                :style="{ '--i': i }"
                :character="c"
                :menu="menuFor('character', c.id)"
                @open="openCharacter(c.id)"
                @pick="onPick('character', c.id, $event)" />
              <p v-if="!characters.length" key="none" class="lib__none ev-empty">
                Nothing in the archive matches — try another word.
              </p>
            </template>
            <CreateLibTile
              key="create"
              :style="{ '--i': characters.length }"
              title="Create a character"
              copy="New companions.
New possibilities."
              @create="openCharacter('new')" />
          </TransitionGroup>

          <!-- worlds -->
          <TransitionGroup
            v-else-if="tab === 'worlds'"
            :key="`worlds-${libraryUi.view}`"
            tag="div"
            name="ev-list"
            appear
            class="lib__cards lib__cards--worlds"
            @before-leave="pinLeaving">
            <p v-if="presets.loading.value" key="loading" class="lib__none" role="status">
              Reading the archive<span class="ev-dots" aria-hidden="true"
                ><span>.</span><span>.</span><span>.</span></span
              >
            </p>
            <p v-else-if="presets.error.value" key="error" class="lib__none" role="alert">
              The archive did not answer ({{ presets.error.value }}) —
              <button type="button" class="lib__link" @click="retryPresets()">retry</button>
            </p>
            <template v-else>
              <WorldLibCard
                v-for="(w, i) in worlds"
                :key="w.id"
                :data-preset="w.id"
                :style="{ '--i': i }"
                :world="w"
                :menu="menuFor('world', w.id)"
                @open="openWorld(w.id)"
                @pick="onPick('world', w.id, $event)" />
              <p v-if="!worlds.length" key="none" class="lib__none ev-empty">
                No worlds match — the map is blank.
              </p>
            </template>
            <CreateLibTile
              key="create"
              :style="{ '--i': worlds.length }"
              title="Create a world"
              copy="Shape the setting of
your next story."
              @create="openWorld('new')" />
          </TransitionGroup>

          <!-- style packs -->
          <div
            v-else-if="tab === 'style-packs'"
            :key="`packs-${libraryUi.view}`"
            class="ev-rise lib__cards lib__cards--packs">
            <p class="lib__soon">
              Coming soon: style packs can be looked at, not made or changed yet. Every story uses
              the house style for now.
            </p>
            <PackLibCard v-for="p in packs" :key="p.id" :pack="p" />
            <CreateLibTile
              soon
              title="Create a style pack"
              copy="Find the voice
of your tales." />
          </div>

          <!-- templates -->
          <div
            v-else
            :key="`templates-${libraryUi.view}`"
            class="ev-rise lib__cards lib__cards--worlds">
            <p class="lib__soon">
              Coming soon: templates can be looked at, not made or changed yet. Start a story from
              New Story for now.
            </p>
            <PackLibCard v-for="p in templates" :key="p.id" :pack="p" />
            <CreateLibTile
              soon
              title="Create a template"
              copy="A first draft of
every future story." />
          </div>
        </Transition>
      </div>
    </section>

    <Transition name="toast">
      <div v-if="notice" class="lib__toast" role="status">
        <span>{{ notice.text }}</span>
        <button v-if="notice.undo" type="button" @click="notice.undo?.()">Undo</button>
        <!-- the time left to undo, running out -->
        <span :key="notice.text" class="lib__toast-clock" aria-hidden="true"></span>
      </div>
    </Transition>
  </main>
</template>

<style scoped>
.lib {
  max-width: 1440px;
  margin: 0 auto;
  padding: 14px 16px 24px;
  display: flex;
  flex-direction: column;
  gap: 14px;
  /* the shelf reaches the bottom of the window, whatever the tab holds */
  min-height: calc(100vh - 62px);
}

/* banner ---------------------------------------------------------------------- */
.lib__banner {
  position: relative;
  overflow: hidden;
  min-height: 184px;
  padding: 0;
}
.lib__art {
  position: absolute;
  inset: 0 0 0 auto;
  height: 100%;
  width: 72%;
  object-fit: cover;
  object-position: right center;
  /* the picture melts into the paper on its left */
  -webkit-mask-image: linear-gradient(90deg, transparent 0%, rgba(0, 0, 0, 0.35) 22%, #000 52%);
  mask-image: linear-gradient(90deg, transparent 0%, rgba(0, 0, 0, 0.35) 22%, #000 52%);
  /* the picture slides in from the right, then pans slowly */
  transform-origin: right center;
  animation:
    lib-art-in 1.3s var(--ease-settle) backwards,
    lib-art-pan 28s var(--ease-sine) 1.3s infinite alternate;
}
/* the entrance moves translate/scale and the pan moves transform: two
   animations on one property cannot both run on the compositor */
@keyframes lib-art-in {
  from {
    opacity: 0;
    translate: 6% 0;
    scale: 1.04;
  }
}
@keyframes lib-art-pan {
  to {
    transform: scale(1.07) translateX(-1.5%);
  }
}
.lib__dust {
  z-index: 0;
  left: 30%;
}
.lib__fade {
  position: absolute;
  inset: 0;
  background: linear-gradient(
    90deg,
    var(--surface-2) 18%,
    rgba(251, 246, 233, 0.6) 40%,
    transparent 62%
  );
  pointer-events: none;
}
.lib__banner-body {
  position: relative;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 26px;
  padding: 22px 26px 20px;
  min-height: inherit;
}
.lib__title {
  margin-top: 0;
  font-family: var(--font-display);
  font-size: 58px;
  font-weight: 700;
  line-height: 0.98;
  letter-spacing: 0.005em;
  color: #211b0e;
}
.lib__heading .ev-eyebrow {
  margin-bottom: 2px;
}
.lib__sub {
  margin-top: 10px;
  max-width: 46ch;
  font-size: 16.5px;
  color: var(--ink-2);
}

/* the shelf: tabs on top, then the toolbar and the cards ------------------------ */
.lib__panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  padding: 0;
  min-width: 0;
}
.lib__shelf {
  flex: 1;
  padding: 16px 18px 20px;
  display: flex;
  flex-direction: column;
}

.lib__toolbar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
}
.lib__search {
  flex: 1 1 250px;
  max-width: 380px;
}
.lib__spacer {
  flex: 1;
}

.lib__cards {
  position: relative;
  margin-top: 16px;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 16px;
  align-content: start;
}
.lib__cards--people {
  grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
}
.lib__cards--worlds {
  grid-template-columns: repeat(auto-fill, minmax(292px, 1fr));
}
.lib__cards--packs {
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
}
.lib--list .lib__cards,
.lib--list .lib__cards--people,
.lib--list .lib__cards--worlds,
.lib--list .lib__cards--packs {
  grid-template-columns: 1fr;
}
/* list mode: a character is one row, the portrait at the side */
.lib--list :deep(.libcard) {
  flex-direction: row;
  min-height: 150px;
}
.lib--list :deep(.libcard__img) {
  width: 120px;
  min-width: 120px;
  aspect-ratio: auto;
  max-height: none;
  border-radius: var(--radius-card) 0 0 var(--radius-card);
}
/* cards arrive one after another (capped so the shelf reads as one beat) */
.lib__cards > .ev-list-enter-active {
  transition:
    opacity 0.32s var(--ease-out),
    transform 0.46s var(--ease-settle);
  transition-delay: calc(min(var(--i, 0), 8) * 40ms);
}
.lib__cards > .ev-list-enter-from {
  opacity: 0;
  transform: translateY(14px) scale(0.97);
}
.lib__cards > .ev-list-leave-active {
  position: absolute;
  margin: 0;
  transition:
    opacity 0.18s var(--ease-in),
    transform 0.18s var(--ease-in);
}
.lib__cards > .ev-list-leave-to {
  opacity: 0;
  transform: scale(0.94);
}
.lib__cards > .ev-list-move {
  transition: transform 0.46s var(--ease-settle);
}
.lib__none {
  grid-column: 1 / -1;
  text-align: center;
  font-style: italic;
  color: var(--muted);
  padding: 18px 0 6px;
}
.lib__soon {
  grid-column: 1 / -1;
  padding: 10px 14px;
  border-radius: 10px;
  border: 1px dashed var(--line-strong);
  background: #fbf3e2;
  font-size: 15.5px;
  color: var(--ink-2);
}
.lib__link {
  font: inherit;
  color: #1f4d3f;
  background: none;
  border: none;
  cursor: pointer;
  text-decoration: underline;
  padding: 0;
}

/* a short note after a card action, with Undo when it can be taken back */
.lib__toast {
  position: fixed;
  left: 50%;
  bottom: 22px;
  z-index: 50;
  transform: translateX(-50%);
  display: flex;
  align-items: center;
  gap: 16px;
  max-width: calc(100vw - 32px);
  padding: 11px 14px 11px 18px;
  border-radius: 12px;
  background: #22302c;
  color: #f4ecd7;
  font-size: 15.5px;
  box-shadow: 0 14px 30px -12px rgba(0, 0, 0, 0.5);
  overflow: hidden;
}
.lib__toast-clock {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  height: 3px;
  background: var(--ember-hi);
  transform-origin: left center;
  animation: lib-toast-clock 7s linear both;
}
@keyframes lib-toast-clock {
  to {
    transform: scaleX(0);
  }
}
.lib__toast button {
  font-weight: 700;
  color: var(--ember-soft);
  padding: 4px 8px;
  border-radius: 7px;
}
.lib__toast button:hover {
  background: rgba(255, 255, 255, 0.08);
}
.toast-enter-active,
.toast-leave-active {
  transition:
    opacity 0.25s ease,
    transform 0.42s var(--ease-spring);
}
.toast-leave-active {
  transition:
    opacity 0.18s var(--ease-in),
    transform 0.2s var(--ease-in);
}
.toast-enter-from,
.toast-leave-to {
  opacity: 0;
  transform: translate(-50%, 14px);
}

@media (max-width: 860px) {
  .lib__banner-body {
    flex-direction: column;
  }
  .lib__art {
    width: 100%;
    opacity: 0.55;
  }
}
</style>
