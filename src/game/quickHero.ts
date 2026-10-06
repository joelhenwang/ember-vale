/**
 * Play as a new hero: one name, one line about who you are, and you are in
 * Ember Vale with Wren and Ash nearby. Pure builders; the composable does
 * the requests.
 */

import type { StoryDraftCreateRequest } from '../../content/clients/worldsim'

export interface HeroInput {
  name: string
  /** Who they are and how they look, in the player's words. */
  about: string
  pronouns: string
}

export interface PresetRef {
  id: string
  revision: number
}

export interface HeroCast {
  world: PresetRef
  hero: PresetRef
  /** Companions by name (Wren, Ash), when the library has them. */
  companions: { name: string; ref: PresetRef; at: string }[]
}

/** Trimmed input, or why it cannot start a story yet. */
export function checkHero(input: HeroInput): { hero: HeroInput } | { problem: string } {
  const name = input.name.trim()
  const about = input.about.trim()
  if (!name) return { problem: 'Give your hero a name.' }
  if (name.length > 64) return { problem: 'Names are 64 letters at most.' }
  if (about.length > 600) return { problem: 'Keep who they are to a few sentences.' }
  return { hero: { name, about, pronouns: input.pronouns.trim().slice(0, 40) } }
}

/** The character preset payload: the description becomes their appearance. */
export function heroPreset(hero: HeroInput): Record<string, unknown> {
  return {
    kind: 'character',
    name: hero.name,
    appearance: hero.about || null,
    pronouns: hero.pronouns || null,
    starting_location_key: 'hearth'
  }
}

/** A story where you play the hero, at the Hearth, with the companions about. */
export function heroDraft(hero: HeroInput, cast: HeroCast): StoryDraftCreateRequest['payload'] {
  return {
    world: { preset_id: cast.world.id, preset_revision: cast.world.revision },
    cast: [
      {
        instance_key: 'hero',
        preset_id: cast.hero.id,
        preset_revision: cast.hero.revision,
        name: hero.name,
        location_key: 'hearth'
      },
      ...cast.companions
        .filter((c) => c.name.toLowerCase() !== hero.name.toLowerCase())
        .map((c) => ({
          instance_key: c.name.toLowerCase(),
          preset_id: c.ref.id,
          preset_revision: c.ref.revision,
          name: c.name,
          location_key: c.at
        }))
    ],
    mode: { role: 'player', controlled_cast_key: 'hero' },
    story: { title: `${hero.name}'s Tale` },
    ai: { art_source: 'curated' }
  } as StoryDraftCreateRequest['payload']
}
