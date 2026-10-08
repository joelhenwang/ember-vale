<!--
  StoriesView — the "Your stories" shelf (search, status chips, sort,
  grid/list density, one StoryCard per saved tale).

  Records come from the backend story list (storyShelf is repopulated on
  every visit); the search/chip/sort pipeline stays the pure filterStories
  in game/filters.ts. Continue opens the story room; the information action
  shows the immutable setup snapshot; archive/restore round-trips the API
  with the record's metadata version.
-->
<script setup lang="ts">
import { computed, onActivated, onMounted, ref } from 'vue'
import { storyLocation } from '../game/storyRoute'
import type { Component } from 'vue'
import { useRouter } from 'vue-router'
import type { StorySetupView } from '../../content/clients/worldsim'
import { filterStories } from '../game/filters'
import { setStoryArchived, storiesUi, storyShelf, type StoryRecord } from '../game/stories'
import { sortStoriesNewest, toStoryRecord, type ResolvedWorld } from '../game/records'
import { archiveStory, getSetup, getStory, listStories, unarchiveStory } from '../api/worldsim'
import { usePresets } from '../composables/usePresets'
import { burst, flash } from '../composables/useEffects'
import SetupDialog from '../components/story/SetupDialog.vue'
import PageIntro from '../components/ui/PageIntro.vue'
import SearchField from '../components/ui/SearchField.vue'
import ChipGroup from '../components/ui/ChipGroup.vue'
import SortSelect from '../components/ui/SortSelect.vue'
import ViewToggle from '../components/ui/ViewToggle.vue'
import StoryCard from '../components/stories/StoryCard.vue'
import MountainRidge from '../components/decor/MountainRidge.vue'
import IconArchive from '../components/icons/IconArchive.vue'
import IconGrid from '../components/icons/IconGrid.vue'
import IconList from '../components/icons/IconList.vue'
import IconPlus from '../components/icons/IconPlus.vue'
import IconRefresh from '../components/icons/IconRefresh.vue'
import IconSparkle from '../components/icons/IconSparkle.vue'

const router = useRouter()

const list = computed(() => filterStories(storyShelf, storiesUi))

const chipOptions: { value: 'all' | 'in-progress' | 'archived'; label: string; icon: Component }[] =
  [
    { value: 'all', label: 'All', icon: IconGrid },
    { value: 'in-progress', label: 'In progress', icon: IconRefresh },
    { value: 'archived', label: 'Archived', icon: IconArchive }
  ]

const sortOptions = [
  { value: 'recent', label: 'Last played' },
  { value: 'name', label: 'Title' }
]

const viewOptions: { value: 'grid' | 'list'; label: string; short: string; icon: Component }[] = [
  { value: 'grid', label: 'Cards view', short: 'Cards', icon: IconGrid },
  { value: 'list', label: 'List view', short: 'List', icon: IconList }
]

const presets = usePresets()
const loading = ref(true)
const loadError = ref<string | null>(null)
const actionError = ref<string | null>(null)
const setup = ref<StorySetupView | null>(null)
const showSetup = ref(false)

function worldOf(name: string): ResolvedWorld {
  const found = presets.worlds.value.find((w) => w.name === name)
  if (found) return { name: found.name, description: found.description }
  return { name: name || 'Unknown world', description: '' }
}

function openStory(story: StoryRecord): void {
  router.push(storyLocation(story.id, story.mode))
}

async function openSetup(story: StoryRecord): Promise<void> {
  actionError.value = null
  try {
    setup.value = await getSetup(story.id)
  } catch (err) {
    setup.value = null
    actionError.value = err instanceof Error ? err.message : 'could not load configuration'
  } finally {
    showSetup.value = true
  }
}

async function toggleArchive(story: StoryRecord, archived: boolean): Promise<void> {
  actionError.value = null
  try {
    const detail = await getStory(story.id)
    if (archived) await archiveStory(story.id, detail.metadata_version)
    else await unarchiveStory(story.id, detail.metadata_version)
    setStoryArchived(story.id, archived)
    // the card glows where it still shows; a restore throws a few sparks
    const card = document.querySelector(`[data-story="${story.id}"]`)
    flash(card)
    if (!archived) burst(card, { count: 10, spread: 60 })
  } catch (err) {
    actionError.value = err instanceof Error ? err.message : 'could not update the story'
  }
}

async function refresh(quiet = false): Promise<void> {
  try {
    const [stories] = await Promise.all([listStories('all'), presets.load()])
    if (presets.error.value) throw new Error(presets.error.value)
    const ordered = sortStoriesNewest(stories.items ?? [])
    const details = await Promise.all(ordered.map((s) => getStory(s.world_id)))
    const records = ordered.map((s) => {
      const detail = details.find((d) => d.world_id === s.world_id)
      if (!detail) return null
      return toStoryRecord(detail, worldOf(s.world_name))
    })
    storyShelf.splice(0, storyShelf.length, ...records.filter((r): r is StoryRecord => r !== null))
    loadError.value = null
  } catch (err) {
    if (!quiet) loadError.value = err instanceof Error ? err.message : 'could not load stories'
  } finally {
    loading.value = false
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

// Kept alive: coming back refreshes quietly behind the shelf already shown.
let opened = false
onMounted(() => void refresh())
onActivated(() => {
  if (opened) void refresh(true)
  opened = true
})
</script>

<template>
  <main class="stories">
    <section class="stories__band ev-card">
      <MountainRidge class="stories__ridge" />
      <PageIntro title="Your stories" sub="Return to an adventure, or begin another.">
        <template #actions>
          <button type="button" class="cta stories__new" @click="router.push('/new-story')">
            <IconPlus :size="15" /> New story
          </button>
        </template>
      </PageIntro>
    </section>

    <section class="stories__panel ev-card" aria-label="Saved stories">
      <div class="stories__toolbar">
        <SearchField
          v-model="storiesUi.search"
          placeholder="Search stories…"
          class="stories__search" />
        <ChipGroup v-model="storiesUi.chip" :options="chipOptions" />
        <span class="stories__spacer"></span>
        <SortSelect v-model="storiesUi.sort" label="Sort by" :options="sortOptions" />
        <ViewToggle v-model="storiesUi.view" label="View mode" :options="viewOptions" />
      </div>

      <div v-if="loading" class="stories__grid" role="status" aria-label="Opening the shelf…">
        <span v-for="n in 3" :key="n" class="stories__ghost ev-card" aria-hidden="true">
          <span class="stories__ghost-art ev-skeleton"></span>
          <span class="stories__ghost-line ev-skeleton"></span>
          <span class="stories__ghost-line ev-skeleton"></span>
        </span>
      </div>
      <p v-else-if="loadError" class="stories__none" role="alert">
        The library is unreachable ({{ loadError }}) — showing nothing rather than old tales.
      </p>
      <template v-else>
        <Transition name="ev-rise">
          <p v-if="actionError" class="stories__none" role="alert">{{ actionError }}</p>
        </Transition>
        <Transition name="ev-swap" mode="out-in">
          <TransitionGroup
            :key="storiesUi.view"
            tag="div"
            name="ev-list"
            appear
            class="stories__grid"
            :class="{ 'stories__grid--list': storiesUi.view === 'list' }"
            @before-leave="pinLeaving">
            <StoryCard
              v-for="(s, i) in list"
              :key="s.id"
              :data-story="s.id"
              :style="{ '--i': i }"
              :story="s"
              :layout="storiesUi.view"
              @continue="openStory(s)"
              @configure="openSetup(s)"
              @saves="openStory(s)"
              @settings="router.push({ name: 'story-settings', params: { storyId: s.id } })"
              @archive="toggleArchive(s, $event)" />
          </TransitionGroup>
        </Transition>

        <p v-if="!list.length" class="stories__none ev-empty">
          {{
            storyShelf.length
              ? 'No stories in this drawer — try another word.'
              : 'No stories yet — begin a tale to fill this shelf.'
          }}
        </p>
      </template>
      <SetupDialog :setup="setup" :open="showSetup" @close="showSetup = false" />
    </section>

    <div class="stories__foot">
      <span class="stories__footline" aria-hidden="true"></span>
      <IconSparkle :size="12" class="stories__footspark" />
      <em>Progress is saved within each story.</em>
      <span class="stories__footline" aria-hidden="true"></span>
    </div>
  </main>
</template>

<style scoped>
.stories {
  max-width: 1440px;
  margin: 0 auto;
  padding: 14px 16px 40px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

/* band ---------------------------------------------------------------------- */
.stories__band {
  position: relative;
  overflow: hidden;
  padding: 20px 26px;
}
.stories__ridge {
  animation: stories-ridge 1.4s var(--ease-settle) both;
  position: absolute;
  right: 0;
  bottom: 0;
  width: 46%;
  height: 100%;
  color: #c9b58c;
  opacity: 0.5;
  pointer-events: none;
}
@keyframes stories-ridge {
  from {
    opacity: 0;
    transform: translateY(24px);
  }
}
.stories__new {
  height: 46px;
}
.stories__new svg {
  transition: transform 0.45s var(--ease-settle);
}
.stories__new:hover svg {
  transform: rotate(90deg);
}

/* panel --------------------------------------------------------------------- */
.stories__panel {
  padding: 14px 16px 18px;
}
.stories__toolbar {
  display: flex;
  align-items: center;
  gap: 14px;
  flex-wrap: wrap;
}
.stories__search {
  flex: 1;
  min-width: 220px;
  max-width: 620px;
}
.stories__spacer {
  flex: 1;
}

.stories__grid {
  position: relative;
  margin-top: 16px;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(380px, 1fr));
  gap: 18px;
}
.stories__grid--list {
  grid-template-columns: 1fr;
}
/* cards arrive one after another (capped so the shelf reads as one beat) */
.stories__grid > .ev-list-enter-active {
  transition-delay: calc(min(var(--i, 0), 8) * 45ms);
}
.stories__grid > .ev-list-leave-active {
  position: absolute;
  margin: 0;
}
.stories__ghost {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 10px 10px 18px;
}
.stories__ghost-art {
  aspect-ratio: 16 / 9.4;
  border-radius: 11px;
}
.stories__ghost-line {
  height: 18px;
  width: 60%;
  margin: 0 6px;
}
.stories__ghost-line:last-child {
  width: 85%;
  height: 14px;
}
.ev-fade-in {
  animation: ev-fade 0.4s var(--ease-out) both;
}
.stories__none {
  margin-top: 20px;
  text-align: center;
  font-size: 15px;
  color: var(--muted);
}

/* footer quote -------------------------------------------------------------- */
.stories__foot {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 14px;
  margin-top: 8px;
}
.stories__footline {
  width: 130px;
  height: 1px;
  background: #e2d4b2;
}
.stories__footspark {
  color: var(--gold);
  animation: ev-float 4.5s var(--ease-sine) infinite;
}
.stories__foot em {
  font-family: var(--font-display);
  font-size: 15.5px;
  color: #8d7c5f;
}

@media (max-width: 860px) {
  .stories__grid {
    grid-template-columns: 1fr;
  }
}
</style>
