/**
 * New Story wizard words and small readings: each step's heading, the tone
 * starting points, the storyteller's plain name, and world search. The
 * wizard's state and its draft live in NewStoryView and useStoryDraft.
 */

export interface StepHead {
  title: string
  sub: string
}

export const NEW_STORY_HEADS: readonly StepHead[] = [
  {
    title: 'Choose a world',
    sub: "Pick the setting for your new story. You'll choose characters next."
  },
  { title: 'Choose your cast', sub: "Add up to 6 characters. You'll choose who you play next." },
  { title: 'How do you want to play?', sub: 'Choose your role, then whose actions are yours.' },
  {
    title: 'Name your story and set its mood',
    sub: 'The title names your story. The tone shapes how it is told.'
  },
  {
    title: 'Choose your storyteller',
    sub: "Use the app's storyteller, or tie this story to a provider profile."
  },
  { title: 'Ready to begin?', sub: 'Check your choices. You can change any step before starting.' }
]

export interface TonePreset {
  value: string
  title: string
  line: string
}

/** Starting points for the tone; the player may write any mood instead. */
export const TONE_PRESETS: readonly TonePreset[] = [
  {
    value: 'hopeful mystery',
    title: 'Hopeful mystery',
    line: 'Wonder, secrets, and signs of a brighter future.'
  },
  {
    value: 'cozy adventure',
    title: 'Cozy adventure',
    line: 'Warm, character-focused and light on danger.'
  },
  {
    value: 'dark intrigue',
    title: 'Dark intrigue',
    line: 'High stakes, hidden agendas and uneasy alliances.'
  }
]

/** "Hopeful mystery" from "hopeful mystery"; empty stays empty. */
export function toneLabel(tone: string): string {
  const clean = tone.trim()
  return clean ? clean.charAt(0).toUpperCase() + clean.slice(1) : ''
}

/**
 * The storyteller the app uses by default, by name: "active:venice" ->
 * "Venice". A deterministic stand-in says so; unknown says so.
 */
export function storytellerName(modelProfile: string | null): string {
  if (!modelProfile) return 'Not known yet'
  const id = modelProfile.replace(/^active:/, '').split(/[:/]/)[0] ?? ''
  if (!id) return 'Not known yet'
  if (id === 'fake') return 'Practice storyteller (no live model)'
  const known: Record<string, string> = { openrouter: 'OpenRouter', venice: 'Venice' }
  return known[id] ?? id.charAt(0).toUpperCase() + id.slice(1)
}

/** Worlds whose name, description or places mention every word searched. */
export function searchWorlds<
  T extends { name: string; description: string; places: { name: string }[] }
>(worlds: readonly T[], search: string): T[] {
  const words = search.toLowerCase().split(/\s+/).filter(Boolean)
  if (!words.length) return [...worlds]
  return worlds.filter((w) => {
    const text = [w.name, w.description, ...w.places.map((p) => p.name)].join(' ').toLowerCase()
    return words.every((word) => text.includes(word))
  })
}

/** "16 places · Mirewake · Oarfall Harbor · Lowbell Tower" (the first few). */
export function placesLine(places: readonly { name: string }[], shown = 3): string {
  const count = `${places.length} ${places.length === 1 ? 'place' : 'places'}`
  const names = places.slice(0, shown).map((p) => p.name)
  return [count, ...names].join(' · ')
}

/** A watched adventure's party: the first four of the cast (`MAX_PARTY_SIZE` on the server). */
export const WATCHED_PARTY_SIZE = 4

/** Who forms a watched adventure's party, and who stays out of it. */
export function watchedParty(names: readonly string[]): { party: string[]; left: string[] } {
  return { party: names.slice(0, WATCHED_PARTY_SIZE), left: names.slice(WATCHED_PARTY_SIZE) }
}

/** "Wren, Ash and Lyra". */
export function namesLine(names: readonly string[]): string {
  if (names.length < 2) return names[0] ?? ''
  return `${names.slice(0, -1).join(', ')} and ${names[names.length - 1]}`
}
