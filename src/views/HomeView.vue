<script setup lang="ts">
import { onActivated, onMounted, ref } from 'vue'
import HeroCard from '../components/HeroCard.vue'
import RecentStories from '../components/RecentStories.vue'
import {
  assetUrl,
  getChronicle,
  getMap,
  getPresentation,
  getRole,
  getStory,
  listStories
} from '../api/worldsim'
import { firstSentence } from '../game/adventure'
import { readyMoments, type Speaker } from '../game/moments'
import type { CurrentStory } from '../game/model'
import { usePresets } from '../composables/usePresets'
import { sortStoriesNewest, toMenuCurrent, toMenuRecent, type ResolvedWorld } from '../game/records'
import { menuState } from '../game/state'

const loading = ref(true)
const error = ref<string | null>(null)
const presets = usePresets()

function worldOf(name: string): ResolvedWorld {
  const found = presets.worlds.value.find((w) => w.name === name)
  if (found) return { name: found.name, description: found.description }
  return { name: name || 'Unknown world', description: '' }
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
    const [tail, map] = await Promise.all([
      getChronicle(worldId, Math.max(0, head.watermark - 6), opts),
      getMap(worldId, opts).catch(() => null)
    ])
    const told = [...(tail.entries ?? [])].reverse().find((e) => e.text)
    const self = (view.cast ?? []).find((c) => c.character_id === me)
    const art = (view.place_art ?? []).find((a) => a.location_id === self?.location_id)
    const current = menuState.current as CurrentStory | null
    if (!current || current.id !== worldId || !self) return
    const speakers: Record<string, Speaker> = {}
    for (const c of view.cast ?? []) {
      speakers[c.character_id] = {
        name: c.name,
        portraitUrl: c.portrait_asset_id ? assetUrl(worldId, c.portrait_asset_id) : null
      }
    }
    const places: Record<string, string> = {}
    for (const p of map?.places ?? []) places[p.id] = p.name
    menuState.current = {
      ...current,
      playing: {
        characterId: me,
        name: self.name,
        portraitUrl: self.portrait_asset_id ? assetUrl(worldId, self.portrait_asset_id) : null,
        title: view.journey?.title ?? null,
        lastLine: told?.text ? firstSentence(told.text) : null,
        sceneUrl: art ? assetUrl(worldId, art.asset_id) : null,
        moments: readyMoments(view.scene_art),
        speakers,
        places
      }
    }
  } catch {
    // Keep the plain hero.
  }
}

/** Read the shelf; a quiet read keeps what is on screen until it is done. */
async function refresh(quiet = false): Promise<void> {
  try {
    const [stories] = await Promise.all([listStories('all'), presets.load()])
    if (presets.error.value) throw new Error(presets.error.value)
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
      .slice(1, 3)
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
      <HeroCard class="ev-rise" />
      <RecentStories />
    </template>
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
</style>
