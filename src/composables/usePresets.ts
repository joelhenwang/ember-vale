/**
 * Persisted Library presets for the journey (C2).
 *
 * Server presets replace the demo catalog in the wizard. Presentation
 * mapping only: starter Wren/Ash resolve to their real portraits by name;
 * anything without curated art gets an explicitly neutral scene fallback
 * (never another character's face) until the image pipeline lands.
 */

import { computed, ref } from 'vue'
import type { CharacterDef, ImageSlot, WorldDef } from '../game/model'
import { getPreset, listPresets } from '../api/worldsim'

export interface PresetCharacter {
  id: string
  revision: number
  name: string
  role: string
  blurb: string
  tags: string[]
  startKey: string | null
  playerReady: boolean
  imageSlot: ImageSlot
}

export interface PresetWorld {
  id: string
  revision: number
  name: string
  description: string
  places: { key: string; name: string }[]
}

const PORTRAIT_BY_NAME: Record<string, ImageSlot> = {
  Wren: 'character.wren',
  Ash: 'character.ash'
}

function roleFromTags(tags: string[]): string {
  const skip = new Set(['Human', 'Player-ready', 'NPC'])
  return tags.find((t) => !skip.has(t)) ?? 'Wanderer'
}

const WORLD_IMAGE_BY_NAME: Record<string, ImageSlot> = {
  'Ember Vale': 'world.emberVale'
}

/**
 * Present a server character preset as a Library card record. Pure
 * presentation mapping: usage is unknown until story shelves report
 * it, and the contract offers no update timestamp, so recency sorting
 * stays unavailable for these records — the revision rides along as
 * explicit metadata instead. Anything without curated art gets the
 * neutral fallback, never another face.
 */
export function toLibraryCharacter(p: PresetCharacter): CharacterDef {
  return {
    id: p.id,
    name: p.name,
    role: p.role,
    blurb: p.blurb,
    bio: p.blurb,
    tags: p.tags.map((label) =>
      label === 'Player-ready' ? { label, tone: 'green' as const } : { label }
    ),
    imageSlot: p.imageSlot,
    categories: p.playerReady ? ['companions'] : ['locals'],
    playerReady: p.playerReady,
    usedInStories: null,
    revision: p.revision,
    updatedAt: 0
  }
}

/** Present a server world preset as a Library card record (same policy). */
export function toLibraryWorld(p: PresetWorld): WorldDef {
  return {
    id: p.id,
    name: p.name,
    blurb: p.description,
    tags: [],
    imageSlot: WORLD_IMAGE_BY_NAME[p.name] ?? 'world.map',
    places: p.places.length,
    usedInStories: null,
    status: 'ready',
    revision: p.revision,
    updatedAt: 0
  }
}

export function usePresets() {
  const worlds = ref<PresetWorld[]>([])
  const characters = ref<PresetCharacter[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  const ready = computed(() => !loading.value && error.value === null)

  async function load(signal?: AbortSignal): Promise<void> {
    loading.value = true
    error.value = null
    try {
      const [worldSummaries, charSummaries] = await Promise.all([
        listPresets('world', { signal }),
        listPresets('character', { signal })
      ])
      const worldDetails = await Promise.all(
        worldSummaries.map((w) => getPreset(w.id, w.current_revision, { signal }))
      )
      const charDetails = await Promise.all(
        charSummaries.map((c) => getPreset(c.id, c.current_revision, { signal }))
      )
      worlds.value = worldDetails
        .map((d) => {
          const rev = (d.revision ?? {}) as Record<string, unknown>
          const places = (rev['locations'] as { key: string; name: string }[] | undefined) ?? []
          return {
            id: d.id,
            revision: d.current_revision,
            name: d.name,
            description: (rev['description'] as string | undefined) ?? '',
            places: places.map((p) => ({ key: p.key, name: p.name }))
          }
        })
        .sort((a, b) => a.name.localeCompare(b.name))
      characters.value = charDetails
        .map((d) => {
          const rev = (d.revision ?? {}) as Record<string, unknown>
          const tags = ((rev['tags'] as string[] | undefined) ?? []).map(String)
          const name = d.name
          return {
            id: d.id,
            revision: d.current_revision,
            name,
            role: roleFromTags(tags),
            blurb: (rev['appearance'] as string | undefined) ?? '',
            tags,
            startKey: (rev['starting_location_key'] as string | undefined) ?? null,
            playerReady: tags.includes('Player-ready'),
            imageSlot: PORTRAIT_BY_NAME[name] ?? 'story.lantern'
          }
        })
        .sort((a, b) => a.name.localeCompare(b.name))
    } catch (err) {
      if (err instanceof Error && err.name === 'ApiError') {
        const cancelled = (err as { cancelled?: boolean }).cancelled
        if (cancelled) return
      }
      error.value = err instanceof Error ? err.message : 'could not load presets'
    } finally {
      loading.value = false
    }
  }

  return { worlds, characters, loading, error, ready, load }
}
