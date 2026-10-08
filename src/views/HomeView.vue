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
    <Transition name="ev-fade" mode="out-in">
      <p v-if="error" class="page__state" role="alert">
        The library is unreachable ({{ error }}) — showing nothing rather than old tales.
      </p>
      <!-- loading: the shape of the page, shimmering, until the shelf is read -->
      <div v-else-if="loading" class="page__loading" role="status">
        <span class="ev-sr">Opening the library…</span>
        <div class="ghost-hero ev-card" aria-hidden="true">
          <span class="ghost-hero__banner ev-skeleton"></span>
          <span class="ghost-hero__row">
            <span class="ghost-hero__face ev-skeleton"></span>
            <span class="ghost-hero__lines">
              <span class="ev-skeleton"></span>
              <span class="ev-skeleton"></span>
              <span class="ev-skeleton"></span>
            </span>
          </span>
        </div>
        <div class="ghost-recent" aria-hidden="true">
          <span v-for="n in 3" :key="n" class="ghost-recent__card ev-card">
            <span class="ev-skeleton"></span>
          </span>
        </div>
      </div>
      <div v-else>
        <HeroCard class="ev-rise" />
        <RecentStories />
      </div>
    </Transition>
  </main>
</template>

<style scoped>
.page {
  max-width: 1440px;
  margin: 0 auto;
  padding: 14px 16px 40px;
}
.ev-sr {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
}
.ghost-hero {
  display: flex;
  flex-direction: column;
  gap: 18px;
  padding: 10px;
}
.ghost-hero__banner {
  height: clamp(200px, 24vw, 350px);
  border-radius: 9px;
}
.ghost-hero__row {
  display: flex;
  gap: 26px;
  padding: 0 16px 14px;
}
.ghost-hero__face {
  width: 172px;
  height: 120px;
  border-radius: 10px;
}
.ghost-hero__lines {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.ghost-hero__lines span {
  height: 16px;
}
.ghost-hero__lines span:first-child {
  width: 40%;
  height: 34px;
}
.ghost-hero__lines span:last-child {
  width: 70%;
}
.ghost-recent {
  margin-top: 26px;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 18px;
}
.ghost-recent__card {
  display: flex;
  padding: 8px;
  height: 126px;
}
.ghost-recent__card span {
  width: 42%;
  border-radius: 8px;
}
@media (max-width: 760px) {
  .ghost-recent {
    grid-template-columns: 1fr;
  }
  .ghost-hero__face {
    display: none;
  }
}
.page__state {
  padding: 18px;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: #fbf6e9;
}
</style>
