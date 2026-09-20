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
import { computed, onMounted, ref } from 'vue'
import type { Component } from 'vue'
import { useRouter } from 'vue-router'
import type { StorySetupView } from '../../content/clients/worldsim'
import { filterStories } from '../game/filters'
import { setStoryArchived, storiesUi, storyShelf, type StoryRecord } from '../game/stories'
import { sortStoriesNewest, toStoryRecord, type ResolvedWorld } from '../game/records'
import {
  archiveStory,
  getSetup,
  getStory,
  listStories,
  unarchiveStory
} from '../api/worldsim'
import { usePresets } from '../composables/usePresets'
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

const viewOptions: { value: 'grid' | 'list'; label: string; icon: Component }[] = [
  { value: 'grid', label: 'Grid view', icon: IconGrid },
  { value: 'list', label: 'List view', icon: IconList }
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
  router.push({ name: 'story-play', params: { storyId: story.id } })
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
  } catch (err) {
    actionError.value = err instanceof Error ? err.message : 'could not update the story'
  }
}

onMounted(async () => {
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
    storyShelf.splice(
      0,
      storyShelf.length,
      ...records.filter((r): r is StoryRecord => r !== null)
    )
  } catch (err) {
    loadError.value = err instanceof Error ? err.message : 'could not load stories'
  } finally {
    loading.value = false
  }
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

      <p v-if="loading" class="stories__none" role="status">Opening the shelf…</p>
      <p v-else-if="loadError" class="stories__none" role="alert">
        The library is unreachable ({{ loadError }}) — showing nothing rather than old tales.
      </p>
      <template v-else>
        <p v-if="actionError" class="stories__none" role="alert">{{ actionError }}</p>
        <div class="stories__grid" :class="{ 'stories__grid--list': storiesUi.view === 'list' }">
          <StoryCard
            v-for="s in list"
            :key="s.id"
            :story="s"
            :layout="storiesUi.view"
            @continue="openStory(s)"
            @configure="openSetup(s)"
            @saves="openStory(s)"
            @archive="toggleArchive(s, $event)" />
        </div>

        <p v-if="!list.length" class="stories__none">
          {{ storyShelf.length ? 'No stories in this drawer — try another word.' : 'No stories yet — begin a tale to fill this shelf.' }}
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
  position: absolute;
  right: 0;
  bottom: 0;
  width: 46%;
  height: 100%;
  color: #c9b58c;
  opacity: 0.5;
  pointer-events: none;
}
.stories__new {
  height: 46px;
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
  margin-top: 16px;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(380px, 1fr));
  gap: 18px;
}
.stories__grid--list {
  grid-template-columns: 1fr;
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
