<script setup lang="ts">
import { onMounted, ref } from 'vue'
import HeroCard from '../components/HeroCard.vue'
import BeginTaleCard from '../components/BeginTaleCard.vue'
import LibraryCard from '../components/LibraryCard.vue'
import RecentStories from '../components/RecentStories.vue'
import SetupDialog from '../components/story/SetupDialog.vue'
import type { StorySetupView } from '../../content/clients/worldsim'
import { getSetup, getStory, listPresets, listStories } from '../api/worldsim'
import { usePresets } from '../composables/usePresets'
import { sortStoriesNewest, toMenuCurrent, toMenuRecent, type ResolvedWorld } from '../game/records'
import { menuState } from '../game/state'

const loading = ref(true)
const error = ref<string | null>(null)
const setup = ref<StorySetupView | null>(null)
const showSetup = ref(false)
const counts = ref({ worlds: 0, characters: 0, packs: 0 })
const presets = usePresets()

function worldOf(name: string): ResolvedWorld {
  const found = presets.worlds.value.find((w) => w.name === name)
  if (found) return { name: found.name, description: found.description }
  return { name: name || 'Unknown world', description: '' }
}

async function openSetup(): Promise<void> {
  const current = menuState.current
  if (!current) return
  try {
    setup.value = await getSetup(current.id)
  } catch {
    setup.value = null
  } finally {
    showSetup.value = true
  }
}

onMounted(async () => {
  try {
    const [stories, packSummaries] = await Promise.all([
      listStories('all'),
      listPresets('style_pack').catch(() => []),
      presets.load()
    ])
    if (presets.error.value) throw new Error(presets.error.value)
    counts.value = {
      worlds: presets.worlds.value.length,
      characters: presets.characters.value.length,
      packs: packSummaries.length
    }
    const ordered = sortStoriesNewest(stories.items ?? [])
    if (!ordered.length) {
      menuState.current = null
      menuState.recent = []
      return
    }
    const details = await Promise.all(ordered.map((s) => getStory(s.world_id)))
    const first = details.find((d) => d.world_id === ordered[0].world_id)
    if (first) {
      menuState.current = toMenuCurrent(first, worldOf(ordered[0].world_name))
    }
    menuState.recent = ordered.slice(1, 4).map((s) => {
      const detail = details.find((d) => d.world_id === s.world_id)
      return detail ? toMenuRecent(detail, worldOf(s.world_name)) : null
    }).filter((r): r is NonNullable<typeof r> => r !== null)
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'could not load stories'
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <main class="page">
    <p v-if="error" class="page__state" role="alert">
      The library is unreachable ({{ error }}) — showing nothing rather than old tales.
    </p>
    <p v-else-if="loading" class="page__state" role="status">Opening the library…</p>
    <template v-else>
      <div class="page__grid">
        <HeroCard @details="openSetup" />
        <aside class="page__side">
          <BeginTaleCard />
          <LibraryCard
            :worlds="counts.worlds"
            :characters="counts.characters"
            :packs="counts.packs" />
        </aside>
      </div>
      <RecentStories />
    </template>
    <SetupDialog :setup="setup" :open="showSetup" @close="showSetup = false" />
  </main>
</template>

<style scoped>
.page {
  max-width: 1440px;
  margin: 0 auto;
  padding: 14px 16px 40px;
}
.page__state {
  padding: 18px;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: #fbf6e9;
}
.page__grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 474px;
  gap: 14px;
  align-items: stretch;
}
.page__side {
  display: grid;
  grid-template-rows: minmax(0, 1fr) auto;
  gap: 16px;
  min-width: 0;
}

@media (max-width: 1180px) {
  .page__grid {
    grid-template-columns: minmax(0, 1fr);
  }
  .page__side {
    grid-template-rows: auto;
    grid-template-columns: 1fr 1fr;
  }
}
@media (max-width: 900px) {
  .page__side {
    grid-template-columns: 1fr;
  }
}
</style>
