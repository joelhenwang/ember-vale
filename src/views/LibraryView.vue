<script setup lang="ts">
import { computed, onMounted, onUnmounted } from 'vue'
import type { Component } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { catalog, libraryUi, resetLibraryFilters } from '../game/catalog'
import { filterCharactersLibrary, filterPacks, filterWorlds } from '../game/filters'
import { toLibraryCharacter, toLibraryWorld, usePresets } from '../composables/usePresets'
import { useGameImage } from '../game/images'
import { useRouteQueryTab } from '../game/useTab'
import LibTabBar from '../components/library/LibTabBar.vue'
import CharacterLibCard from '../components/library/CharacterLibCard.vue'
import WorldLibCard from '../components/library/WorldLibCard.vue'
import PackLibCard from '../components/library/PackLibCard.vue'
import CreateLibTile from '../components/library/CreateLibTile.vue'
import InspireRail from '../components/library/InspireRail.vue'
import SearchField from '../components/ui/SearchField.vue'
import ChipGroup from '../components/ui/ChipGroup.vue'
import SortSelect from '../components/ui/SortSelect.vue'
import ViewToggle from '../components/ui/ViewToggle.vue'
import IconPlus from '../components/icons/IconPlus.vue'
import IconChevronDown from '../components/icons/IconChevronDown.vue'
import IconGrid from '../components/icons/IconGrid.vue'
import IconList from '../components/icons/IconList.vue'
import IconSparkle from '../components/icons/IconSparkle.vue'

const route = useRoute()
const router = useRouter()
const tab = useRouteQueryTab(route, router, 'characters')

const bannerUrl = useGameImage('library.banner')

const viewOptions: { value: 'grid' | 'list'; label: string; icon: Component }[] = [
  { value: 'grid', label: 'Grid view', icon: IconGrid },
  { value: 'list', label: 'List view', icon: IconList }
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

function retryPresets(): void {
  presetAbort?.abort()
  presetAbort = new AbortController()
  void presets.load(presetAbort.signal)
}

const tabs = computed(() => [
  { key: 'worlds', label: 'Worlds', count: presets.worlds.value.length },
  { key: 'characters', label: 'Characters', count: presets.characters.value.length },
  { key: 'style-packs', label: 'Style Packs', count: catalog.stylePacks.length },
  { key: 'templates', label: 'Templates', count: catalog.templates.length }
])

interface TabConfig {
  search: string
  chips: { value: string; label: string }[]
  rail: { title: string; copy: string; quote: string }
}

const configs: Record<string, TabConfig> = {
  characters: {
    search: 'Search your library…',
    chips: [
      { value: 'all', label: 'All' },
      { value: 'player', label: 'Player-ready' },
      { value: 'npc', label: 'NPC' }
    ],
    rail: {
      title: 'From character to story',
      copy: 'Select characters here, then add them to a cast when creating a new story.',
      quote: '“Familiar faces.\nBrighter worlds.”'
    }
  },
  worlds: {
    search: 'Search worlds…',
    chips: [
      { value: 'all', label: 'All' },
      { value: 'ready', label: 'Ready to use' },
      { value: 'draft', label: 'Drafts' }
    ],
    rail: {
      title: 'From world to story',
      copy: 'Choose a world, gather your cast, and begin a new story.',
      quote: '“Familiar places.\nBrighter worlds.”'
    }
  },
  'style-packs': {
    search: 'Search style packs…',
    chips: [],
    rail: {
      title: 'From style to story',
      copy: 'Every tale wears a voice. Craft a house style, then lend it to any world.',
      quote: '“New voices.\nOld fires.”'
    }
  },
  templates: {
    search: 'Search templates…',
    chips: [],
    rail: {
      title: 'From spark to story',
      copy: 'Start from a template, or roll your own. The page stays blank until you begin.',
      quote: '“First lines.\nLasting worlds.”'
    }
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

function setTab(key: string): void {
  resetLibraryFilters()
  tab.value = key
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
      <div class="lib__banner-body">
        <div class="lib__heading">
          <span class="ev-eyebrow"><IconSparkle :size="13" /> Your creative archive</span>
          <h1 class="lib__title">Library</h1>
          <p class="lib__sub">
            Build the places, people, and storytelling styles you can reuse across adventures.
          </p>
        </div>
        <div class="lib__side">
          <div class="lib__create">
            <button type="button" class="lib__create-main" @click="openCharacter('new')">
              <IconPlus :size="15" /> Create
            </button>
            <button type="button" class="lib__create-caret" aria-label="More create options">
              <IconChevronDown :size="15" />
            </button>
          </div>
          <p class="ev-quote lib__motto">“Same people.<br />New paths.”</p>
        </div>
      </div>
    </section>

    <!-- tabs ------------------------------------------------------------------ -->
    <LibTabBar :tabs="tabs" :model-value="tab" @update="setTab" />

    <!-- content ----------------------------------------------------------------- -->
    <div class="lib__grid" :class="{ 'lib--list': libraryUi.view === 'list' }">
      <section class="lib__panel ev-card" :aria-label="`Library — ${tab}`">
        <div class="lib__toolbar">
          <SearchField
            v-model="libraryUi.search"
            :placeholder="config.search"
            class="lib__search" />
          <ChipGroup v-if="config.chips.length" v-model="libraryUi.chip" :options="config.chips" />
          <span class="lib__spacer"></span>
          <SortSelect
            v-model="libraryUi.sort"
            label="Sort:"
            :options="[
              { value: 'recent', label: 'Recently Updated' },
              { value: 'name', label: 'Name' }
            ]" />
          <ViewToggle v-model="libraryUi.view" label="View mode" :options="viewOptions" />
        </div>

        <!-- characters -->
        <div v-if="tab === 'characters'" class="lib__cards">
          <p v-if="presets.loading.value" class="lib__none" role="status">Reading the archive…</p>
          <p v-else-if="presets.error.value" class="lib__none" role="alert">
            The archive did not answer ({{ presets.error.value }}) —
            <button type="button" class="lib__link" @click="retryPresets()">retry</button>
          </p>
          <template v-else>
            <CharacterLibCard
              v-for="c in characters"
              :key="c.id"
              :character="c"
              @open="openCharacter(c.id)" />
            <p v-if="!characters.length" class="lib__none">
              Nothing in the archive matches — try another word.
            </p>
          </template>
          <CreateLibTile
            title="Create a character"
            copy="New companions.
New possibilities."
            @create="openCharacter('new')" />
        </div>

        <!-- worlds -->
        <div v-else-if="tab === 'worlds'" class="lib__cards lib__cards--worlds">
          <p v-if="presets.loading.value" class="lib__none" role="status">Reading the archive…</p>
          <p v-else-if="presets.error.value" class="lib__none" role="alert">
            The archive did not answer ({{ presets.error.value }}) —
            <button type="button" class="lib__link" @click="retryPresets()">retry</button>
          </p>
          <template v-else>
            <WorldLibCard v-for="w in worlds" :key="w.id" :world="w" @open="openWorld(w.id)" />
            <p v-if="!worlds.length" class="lib__none">No worlds match — the map is blank.</p>
          </template>
          <CreateLibTile
            title="Create a world"
            copy="Shape the setting of
your next story."
            cta="Create world"
            @create="openWorld('new')" />
        </div>

        <!-- style packs -->
        <div v-else-if="tab === 'style-packs'" class="lib__cards lib__cards--packs">
          <PackLibCard v-for="p in packs" :key="p.id" :pack="p" />
          <CreateLibTile
            title="Create a style pack"
            copy="Find the voice
of your tales."
            cta="Create pack" />
        </div>

        <!-- templates -->
        <div v-else class="lib__cards lib__cards--worlds">
          <PackLibCard v-for="p in templates" :key="p.id" :pack="p" />
          <CreateLibTile
            title="Create a template"
            copy="A first draft of
every future story."
            cta="Create template" />
        </div>
      </section>

      <InspireRail :title="config.rail.title" :copy="config.rail.copy" :quote="config.rail.quote" />
    </div>
  </main>
</template>

<style scoped>
.lib {
  max-width: 1440px;
  margin: 0 auto;
  padding: 14px 16px 40px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

/* banner ---------------------------------------------------------------------- */
.lib__banner {
  position: relative;
  overflow: hidden;
  min-height: 208px;
  padding: 0;
}
.lib__art {
  position: absolute;
  inset: 0 auto 0 30%;
  height: 100%;
  width: 70%;
  object-fit: cover;
  object-position: right center;
}
.lib__fade {
  position: absolute;
  inset: 0;
  background: linear-gradient(
    90deg,
    var(--surface-2) 22%,
    rgba(249, 242, 225, 0.55) 46%,
    transparent 68%
  );
  pointer-events: none;
}
.lib__banner-body {
  position: relative;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 26px;
  padding: 20px 24px 18px;
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
  font-size: 16.5px;
  color: var(--ink-2);
}
.lib__side {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 14px;
  flex: none;
}
.lib__create {
  display: flex;
  align-items: stretch;
  border-radius: 10px;
  overflow: hidden;
  border: 1px solid #0c3f46;
  box-shadow:
    inset 0 1px 0 rgba(255, 243, 214, 0.22),
    0 1px 2px rgba(16, 46, 46, 0.3),
    0 8px 16px -10px rgba(16, 46, 46, 0.5);
}
.lib__create-main,
.lib__create-caret {
  background: linear-gradient(180deg, #256e67, #14535a);
  color: var(--cream-on-teal);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: 46px;
  transition: filter 0.14s ease;
}
.lib__create-main {
  gap: 9px;
  padding: 0 22px;
  font-size: 19px;
  font-weight: 500;
}
.lib__create-caret {
  padding: 0 13px;
  border-left: 1px solid rgba(10, 46, 50, 0.6);
  box-shadow: inset 1px 0 0 rgba(255, 243, 214, 0.15);
}
.lib__create:hover {
  filter: brightness(1.07);
}
.lib__motto {
  text-align: center;
  font-size: 15.5px;
  line-height: 1.45;
  white-space: pre-line;
  padding-right: 4px;
}

/* content grid ------------------------------------------------------------------ */
.lib__grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 318px;
  gap: 14px;
  align-items: stretch;
}
.lib__panel {
  padding: 16px 18px 18px;
  min-width: 0;
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
  margin-top: 16px;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 14px;
}
.lib__cards--worlds {
  grid-template-columns: repeat(auto-fill, minmax(292px, 1fr));
}
.lib__cards--packs {
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
}
.lib--list .lib__cards,
.lib--list .lib__cards--worlds,
.lib--list .lib__cards--packs {
  grid-template-columns: 1fr;
}
.lib__none {
  grid-column: 1 / -1;
  text-align: center;
  font-style: italic;
  color: var(--muted);
  padding: 18px 0 6px;
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

@media (max-width: 1180px) {
  .lib__grid {
    grid-template-columns: 1fr;
  }
}
@media (max-width: 860px) {
  .lib__banner-body {
    flex-direction: column;
  }
  .lib__side {
    align-items: flex-start;
  }
}
</style>
