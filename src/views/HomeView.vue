<script setup lang="ts">
import { onActivated, onMounted, ref } from 'vue'
import HeroCard from '../components/HeroCard.vue'
import BeginTaleCard from '../components/BeginTaleCard.vue'
import LibraryCard from '../components/LibraryCard.vue'
import RecentStories from '../components/RecentStories.vue'
import SetupDialog from '../components/story/SetupDialog.vue'
import type { StorySetupView } from '../../content/clients/worldsim'
import {
  assetUrl,
  getChronicle,
  getPresentation,
  getRole,
  getSetup,
  getStory,
  listPresets,
  listStories
} from '../api/worldsim'
import { firstSentence } from '../game/adventure'
import type { CurrentStory } from '../game/model'
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

/**
 * For a story you play: your character, their renown, the last thing that
 * happened and where you stand, so Home invites you straight back in.
 * Best effort: the hero keeps its plain form if any read fails.
 */
async function addPlaying(worldId: string): Promise<void> {
  try {
    const grant = await getRole(worldId)
    const me = grant?.role === 'player' ? grant.character_id : null
    if (!me) return
    const opts = { role: 'player' as const, characterId: me }
    const view = await getPresentation(worldId, opts)
    const head = await getChronicle(worldId, 0, opts, 1)
    const tail = await getChronicle(worldId, Math.max(0, head.watermark - 6), opts)
    const told = [...(tail.entries ?? [])].reverse().find((e) => e.text)
    const self = (view.cast ?? []).find((c) => c.character_id === me)
    const art = (view.place_art ?? []).find((a) => a.location_id === self?.location_id)
    const current = menuState.current as CurrentStory | null
    if (!current || current.id !== worldId || !self) return
    menuState.current = {
      ...current,
      playing: {
        name: self.name,
        portraitUrl: self.portrait_asset_id ? assetUrl(worldId, self.portrait_asset_id) : null,
        title: view.journey?.title ?? null,
        lastLine: told?.text ? firstSentence(told.text) : null,
        sceneUrl: art ? assetUrl(worldId, art.asset_id) : null
      }
    }
  } catch {
    // Keep the plain hero.
  }
}

/** Read the shelf; a quiet read keeps what is on screen until it is done. */
async function refresh(quiet = false): Promise<void> {
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
    // Continue features an eligible unarchived story: archived tales stay
    // available through the shelf's explicit archived filter, never as hero.
    // sortStoriesNewest already puts never-opened (null last_played_at)
    // stories after played ones, matching the "Last played" label.
    const ordered = sortStoriesNewest(stories.items ?? [])
    const eligible = ordered.filter((s) => !s.archived)
    if (!eligible.length) {
      menuState.current = null
      menuState.recent = []
      return
    }
    const details = await Promise.all(eligible.map((s) => getStory(s.world_id)))
    const first = details.find((d) => d.world_id === eligible[0].world_id)
    if (first) {
      menuState.current = toMenuCurrent(first, worldOf(eligible[0].world_name))
      if (first.mode === 'player') void addPlaying(first.world_id)
    } else {
      menuState.current = null
    }
    menuState.recent = eligible
      .slice(1, 4)
      .map((s) => {
        const detail = details.find((d) => d.world_id === s.world_id)
        return detail ? toMenuRecent(detail, worldOf(s.world_name)) : null
      })
      .filter((r): r is NonNullable<typeof r> => r !== null)
    error.value = null
  } catch (err) {
    if (!quiet) error.value = err instanceof Error ? err.message : 'could not load stories'
  } finally {
    loading.value = false
  }
}

// Kept alive between visits: the first opening reads with a loading line,
// coming back refreshes behind what is already shown.
let opened = false
onMounted(() => void refresh())
onActivated(() => {
  if (opened) void refresh(true)
  opened = true
})
</script>

<template>
  <main class="page">
    <p v-if="error" class="page__state" role="alert">
      The library is unreachable ({{ error }}) — showing nothing rather than old tales.
    </p>
    <p v-else-if="loading" class="page__state" role="status">Opening the library…</p>
    <template v-else>
      <div class="page__grid ev-rise">
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
