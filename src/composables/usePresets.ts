/**
 * Persisted Library presets for the journey (C2).
 *
 * Server presets replace the demo catalog in the wizard. Presentation
 * mapping only: starter Wren/Ash resolve to their real portraits by name;
 * anything without curated art gets an explicitly neutral scene fallback
 * (never another character's face) until the image pipeline lands.
 */

import { computed, ref } from 'vue'
import type { CharacterDef, FramedCover, FramedPortrait, ImageSlot, WorldDef } from '../game/model'
import type { Frame } from '../game/framing'
import { getPreset, libraryAssetUrl, listPresets } from '../api/worldsim'
import type { PresetDetail } from '../../content/clients/worldsim'
import { characterBlurb } from '../game/studioFields'

export interface PresetCharacter {
  id: string
  revision: number
  /** The preset's metadata version, for archiving. */
  version: number
  /** Shipped with the app: it can be copied but not put away. */
  builtin: boolean
  name: string
  role: string
  blurb: string
  tags: string[]
  startKey: string | null
  playerReady: boolean
  imageSlot: ImageSlot
  portrait: FramedPortrait | null
}

export interface PresetWorld {
  id: string
  revision: number
  version: number
  builtin: boolean
  name: string
  description: string
  places: { key: string; name: string }[]
  cover: FramedCover | null
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
/** A world revision's own picture with its banner frame. */
export function worldCover(rev: Record<string, unknown>): FramedCover | null {
  const cover = rev['cover'] as { asset_id?: unknown; frame?: Frame } | null | undefined
  if (!cover || typeof cover.asset_id !== 'string' || !cover.frame) return null
  return { src: libraryAssetUrl(cover.asset_id), frame: cover.frame }
}

/** A preset revision's imported picture with its frames, when it has both. */
export function framedPortrait(rev: Record<string, unknown>): FramedPortrait | null {
  const id = rev['portrait_asset_id']
  const frames = rev['portrait_frames'] as { portrait?: Frame; face?: Frame } | null | undefined
  if (typeof id !== 'string' || !frames?.portrait || !frames.face) return null
  return { src: libraryAssetUrl(id), portrait: frames.portrait, face: frames.face }
}

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
    portrait: p.portrait,
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
    cover: p.cover,
    places: p.places.length,
    usedInStories: null,
    status: 'ready',
    revision: p.revision,
    updatedAt: 0
  }
}

/*
 * The last shelf read, shared by every page: a page opening again shows it
 * at once and refreshes quietly. A revision never changes once written, so
 * its details are read only once.
 */
let shelf: { worlds: PresetWorld[]; characters: PresetCharacter[] } | null = null
const revisions = new Map<string, PresetDetail>()

/** Forget the shared shelf (tests, and after a change made elsewhere). */
export function forgetPresetShelf(): void {
  shelf = null
  revisions.clear()
}

async function revisionOf(
  id: string,
  revision: number,
  signal?: AbortSignal
): Promise<PresetDetail> {
  const key = `${id}:${revision}`
  const known = revisions.get(key)
  if (known) return known
  const detail = await getPreset(id, revision, { signal })
  revisions.set(key, detail)
  return detail
}

export function usePresets() {
  const worlds = ref<PresetWorld[]>(shelf?.worlds ?? [])
  const characters = ref<PresetCharacter[]>(shelf?.characters ?? [])
  const loading = ref(false)
  const error = ref<string | null>(null)

  const ready = computed(() => !loading.value && error.value === null)

  async function load(signal?: AbortSignal): Promise<void> {
    // Only an empty shelf shows a loading state; a known one refreshes quietly.
    loading.value = shelf === null
    error.value = null
    try {
      const [worldSummaries, charSummaries] = await Promise.all([
        listPresets('world', { signal }),
        listPresets('character', { signal })
      ])
      const versions = new Map(
        [...worldSummaries, ...charSummaries].map((p) => [p.id, p.version] as const)
      )
      const worldDetails = await Promise.all(
        worldSummaries.map((w) => revisionOf(w.id, w.current_revision, signal))
      )
      const charDetails = await Promise.all(
        charSummaries.map((c) => revisionOf(c.id, c.current_revision, signal))
      )
      worlds.value = worldDetails
        .map((d) => {
          const rev = (d.revision ?? {}) as Record<string, unknown>
          const places = (rev['locations'] as { key: string; name: string }[] | undefined) ?? []
          return {
            id: d.id,
            revision: d.current_revision,
            version: versions.get(d.id) ?? d.version,
            builtin: d.builtin,
            name: d.name,
            description: (rev['description'] as string | undefined) ?? '',
            places: places.map((p) => ({ key: p.key, name: p.name })),
            cover: worldCover(rev)
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
            version: versions.get(d.id) ?? d.version,
            builtin: d.builtin,
            name,
            role: roleFromTags(tags),
            blurb: characterBlurb(rev),
            tags,
            startKey: (rev['starting_location_key'] as string | undefined) ?? null,
            playerReady: tags.includes('Player-ready'),
            imageSlot: PORTRAIT_BY_NAME[name] ?? 'story.lantern',
            portrait: framedPortrait(rev)
          }
        })
        .sort((a, b) => a.name.localeCompare(b.name))
      shelf = { worlds: worlds.value, characters: characters.value }
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
