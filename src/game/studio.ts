import { reactive } from 'vue'
/* snapshots live in reactive maps so "dirty" indicators update after save */

/**
 * Editable drafts for the character & world studios. Both the New Story
 * wizard and the Library route into the same studios and share these
 * objects, so an edit started from one entry point is preserved when
 * returning from the other. "Save" takes a snapshot; dirty state drives
 * the ● Unsaved changes indicator.
 */

export interface PlaceDraft {
  /** Local tab identity: stable for this editing session only. */
  id: string
  /**
   * Stable server location key, independent of the display name.
   * Renaming a place never changes its key, so route references and
   * the starting-location pin survive renames.
   */
  key: string
  name: string
  type: string
  purpose: string
  appearance: string
  landmark: string
  /**
   * Display name of the linked place (prose mirror). The authoritative
   * link is `connectedKey`; this carries the human-readable name into
   * the description prose and the connection picker.
   */
  connectedTo: string
  /**
   * Stable destination key of the outgoing connection ('' = none).
   * Routes resolve through this, never through display names, so
   * duplicate names cannot redirect a route during an unrelated save.
   */
  connectedKey: string
  sounds: string
  /**
   * Server prose the section parser did not attribute to a known
   * field. Invisible in the form; packed back verbatim so unrelated
   * prose is never lost by editing a section.
   */
  detailExtra: string
  /**
   * Original server description bytes at unpack time. When the
   * description fields are unchanged (compared against
   * `detailBaseCanonical`), these exact bytes ship back — a no-op save
   * never rewrites plain or empty prose with generated sections.
   */
  detailBase: string
  /**
   * Canonical pack of the unpacked description (same combine step the
   * packer uses, including travel-hydrated connections). The editable
   * baseline: only a recompute that differs from this regenerates.
   */
  detailBaseCanonical: string
}

export interface CharacterDraft {
  want: string
  avoid: string
  pressure: string
  contradiction: string
  styleTags: string[]
  withStrangers: string
  whenTheyCare: string
  exampleLine: string
  boundaries: string
  secretFear: string
  appearanceSaved: boolean
  /**
   * Server prose the section parser did not attribute to a known
   * field (leading free text in personality / background). Invisible
   * in the form; packed back verbatim ahead of the regenerated
   * sections so unrelated prose survives section edits.
   */
  personalityExtra: string
  backgroundExtra: string
}

export interface WorldDraft {
  terrain: string[]
  climate: string
  architecture: string
  details: string
  exclusions: string
  places: PlaceDraft[]
  /** Local id of the tab being edited. Inspecting tabs never publishes. */
  activePlace: string
  /**
   * Local id of the place configured as the world's starting location.
   * This — never the inspected tab — is what publishes as
   * starting_location_key.
   */
  startPlace: string
  /**
   * Server prose the section parser did not attribute to a known lore
   * field. Invisible in the form; packed back verbatim.
   */
  loreExtra: string
  /**
   * Server travel legs the form cannot represent (anything beyond one
   * connection per place). Invisible in the form; packed back verbatim
   * so routes authored outside the connection fields survive saves.
   * Pruned explicitly when a place is removed.
   */
  travelExtra: string[][]
}

const blankCharacter = (): CharacterDraft => ({
  want: '',
  avoid: '',
  pressure: '',
  contradiction: '',
  styleTags: [],
  withStrangers: 'Friendly, but guarded',
  whenTheyCare: '',
  exampleLine: '',
  boundaries: '',
  secretFear: '',
  appearanceSaved: false,
  personalityExtra: '',
  backgroundExtra: ''
})

const blankPlace = (n: number): PlaceDraft => ({
  id: `place-${Date.now()}-${n}`,
  key: `place-${n}`,
  name: 'New place',
  type: 'Village square',
  purpose: '',
  appearance: '',
  landmark: '',
  connectedTo: '',
  connectedKey: '',
  sounds: '',
  detailExtra: '',
  detailBase: '',
  detailBaseCanonical: ''
})

export const charDrafts = reactive<Record<string, CharacterDraft>>({})
export const worldDrafts = reactive<Record<string, WorldDraft>>({})

const charSnap = reactive<Record<string, string>>({})
const worldSnap = reactive<Record<string, string>>({})

export function ensureCharDraft(id: string): CharacterDraft {
  if (!charDrafts[id]) {
    if (id === 'wren') {
      charDrafts[id] = {
        want: 'Find their missing brother and learn why he left.',
        avoid: 'Making promises they cannot keep.',
        pressure: 'Jokes first, then becomes unusually direct.',
        contradiction: 'Distrusts authority, but secretly wants its approval.',
        styleTags: ['Brief sentences', 'Dry humor'],
        withStrangers: 'Friendly, but guarded',
        whenTheyCare: 'Offers practical help instead of reassurance.',
        exampleLine: 'I said I knew the road. I never said it was a good one.',
        boundaries: '',
        secretFear: '',
        appearanceSaved: false,
        personalityExtra: '',
        backgroundExtra: ''
      }
    } else if (id === 'nessa') {
      charDrafts[id] = {
        ...blankCharacter(),
        want: 'Keep the crossing fair and the gossip kind.',
        avoid: 'Owning anyone a secret.',
        styleTags: ['Warm nags', 'River sayings']
      }
    } else {
      charDrafts[id] = blankCharacter()
    }
    charSnap[id] = JSON.stringify(charDrafts[id])
  }
  return charDrafts[id]
}

export function ensureWorldDraft(id: string): WorldDraft {
  if (!worldDrafts[id]) {
    if (id === 'ember-vale') {
      worldDrafts[id] = {
        terrain: ['River valley', 'Woodland'],
        climate: 'Temperate',
        architecture: 'Timber and pale stone, weathered copper roofs, modest village squares.',
        details: 'Mossy riverbanks, woven market awnings, quiet traces of old magic.',
        exclusions: 'Modern machinery, towering castles',
        places: [
          {
            id: 'hearth',
            key: 'hearth',
            name: 'Hearth',
            type: 'Village inn',
            purpose: 'Warm rest, shared meals, and rumor trading.',
            appearance: 'Low beams, a wide stone hearth, lantern light and the smell of bread.',
            landmark: 'The common-room fire',
            connectedTo: 'Market',
            connectedKey: 'market',
            sounds: 'Kettles, chairs scraping, someone tuning a bad lute.',
            detailExtra: '',
            detailBase: '',
            detailBaseCanonical: ''
          },
          {
            id: 'market',
            key: 'market',
            name: 'Market',
            type: 'Open-air market',
            purpose: 'Trade, news, and chance encounters.',
            appearance:
              'A small cobbled square with striped canvas stalls, low timber buildings and a stone well.',
            landmark: 'Old stone well',
            connectedTo: 'Hearth',
            connectedKey: 'hearth',
            sounds: 'Apples tumbling into crates, haggling, a bell at noon.',
            detailExtra: '',
            detailBase: '',
            detailBaseCanonical: ''
          }
        ],
        activePlace: 'market',
        startPlace: 'market',
        loreExtra: '',
        travelExtra: []
      }
    } else if (id === 'silverleaf-coast') {
      worldDrafts[id] = {
        terrain: ['Sea cliffs', 'Harbors'],
        climate: 'Mild coastal',
        architecture: 'Whitewashed stone, terracotta roofs, stair-streets down to the water.',
        details: 'Gull cries, salt on the wind, ruins that predate the town.',
        exclusions: 'Steam engines, standing armies',
        places: [
          {
            id: 'lighthouse',
            key: 'lighthouse',
            name: 'The Lantern Point',
            type: 'Lighthouse',
            purpose: 'Guides ships — and hides the keeper’s ledger.',
            appearance: 'A white tower on the headland, a lamp that never quite stays lit.',
            landmark: 'The broken stair',
            connectedTo: '',
            connectedKey: '',
            sounds: 'Foghorn, gulls, the sea rearranging itself.',
            detailExtra: '',
            detailBase: '',
            detailBaseCanonical: ''
          }
        ],
        activePlace: 'lighthouse',
        startPlace: 'lighthouse',
        loreExtra: '',
        travelExtra: []
      }
    } else {
      worldDrafts[id] = {
        terrain: [],
        climate: 'Temperate',
        architecture: '',
        details: '',
        exclusions: '',
        places: [blankPlace(0)],
        activePlace: 'boot',
        startPlace: 'boot',
        loreExtra: '',
        travelExtra: []
      }
      const p = worldDrafts[id].places[0]!
      worldDrafts[id].activePlace = p.id
      worldDrafts[id].startPlace = p.id
    }
    worldSnap[id] = JSON.stringify(worldDrafts[id])
  }
  return worldDrafts[id]
}

export function saveCharDraft(id: string): void {
  charSnap[id] = JSON.stringify(charDrafts[id] ?? {})
}
export function saveWorldDraft(id: string): void {
  worldSnap[id] = JSON.stringify(worldDrafts[id] ?? {})
}

export function isCharDirty(id: string): boolean {
  if (!charDrafts[id]) return false
  return JSON.stringify(charDrafts[id]) !== charSnap[id]
}
export function isWorldDirty(id: string): boolean {
  if (!worldDrafts[id]) return false
  return JSON.stringify(worldDrafts[id]) !== worldSnap[id]
}

/* ------------------------------------------------------------------ *
 * Studio canned content — production: these come from the narrator
 * ------------------------------------------------------------------ */

export const STRANGER_STANCES = [
  'Friendly, but guarded',
  'Warm and open',
  'Cool and formal',
  'Playfully evasive'
]

export const CLIMATES = ['Temperate', 'Mild coastal', 'Alpine', 'Arid', 'Grey and drizzly']

export const PLACE_TYPES = [
  'Open-air market',
  'Village square',
  'Village inn',
  'Shrine',
  'Harbor',
  'Ruin',
  'Woodland path',
  'Other'
]

export const TIMES = ['Morning', 'Midday', 'Dusk', 'Night']
export const WEATHERS = ['Clear', 'Light rain', 'Fog', 'First snow']

export const BEHAVIOR_TRAITS = [
  'Leads with humor',
  'Deflects compliments',
  'Acts before asking',
  'Keeps every promise made aloud'
]

/** Dialogue pools for the Voice tab preview (two variants per situation). */
export const VOICE_SITUATIONS: readonly string[] = [
  'A stranger asks for their last coins.',
  'A friend breaks a small promise.',
  'A guard demands a toll.',
  'The road forks at dusk.'
]

export const CHAR_TONES = ['Warmer', 'More guarded', 'Less formal'] as const

interface Beat {
  system: string
  line: string
  system2: string
  line2: string
}

const WREN_BEATS: Record<number, Beat[]> = {
  0: [
    {
      system: 'Wren turns the coin between their fingers, studying the stranger.',
      line: '“My last coin? You do aim high. Tell me what you need it for.”',
      system2: 'After a moment, they nod toward the bread stall.',
      line2: '“Come on. We can split a loaf. No promises about the conversation.”'
    },
    {
      system: 'Wren counts the coins once, twice — then pockets them.',
      line: '“Ask me again when I’m richer and dumber. Preferably the first one.”',
      system2: 'They tug the satchel tighter, but shift aside to make room on the bench.',
      line2: '“Sit. The story’s free. It’s the second coin that costs.”'
    }
  ],
  1: [
    {
      system: 'Wren listens without interrupting, which is how you know it landed.',
      line: '“You said Tuesday. I held Tuesday. Fine — I’m holding Thursday instead.”',
      system2: 'They toss a pebble into the ditch, missing nothing.',
      line2: '“Next time, promise less. Then keep all of it. Easy math.”'
    }
  ],
  2: [
    {
      system: 'Wren produces the toll, already sorted, before the guard finishes the sentence.',
      line: '“Three copper, one favor, no receipt. The usual, right?”',
      system2: 'The guard blinks; Wren tips an imaginary hat.',
      line2: '“Smile, ser. The coin’s good. The conversation, less so.”'
    }
  ],
  3: [
    {
      system: 'Wren squints at the fork in the road, then at the sky.',
      line: '“Left’s shorter. Right’s drier. Neither’s honest, but one of them’s fast.”',
      system2: 'They start walking left without waiting for a vote.',
      line2: '“Come on. If we’re wrong, we’ll be wrong early. That’s basically optimism.”'
    }
  ]
}

export function wrenBeats(situationIndex: number, variant: number): Beat {
  const pool = WREN_BEATS[situationIndex] ?? WREN_BEATS[0]!
  return pool[variant % pool.length]!
}

/** Generic two-beat exchange for characters without authored beats. */
export function genericBeat(name: string, variant: number): Beat {
  return variant % 2 === 0
    ? {
        system: `${name} weighs the moment in silence — the good kind.`,
        line: '“Say it plain. I’m slower with riddles than I look.”',
        system2: 'A short nod, then a hand already moving to help.',
        line2: '“There. That wasn’t so hard, was it?”'
      }
    : {
        system: `${name} tilts their head, considering.`,
        line: '“I’ll meet you halfway — but I’ll pick which half.”',
        system2: 'Almost a smile. Almost.',
        line2: '“Ask again in ten minutes. I’m good as new then.”'
      }
}

/* ------------------------------------------------------------------ *
 * "Suggest details" — canned assistant behaviour (DEMO)
 * In production this is one call: prompt(draft, character) → narrator
 * fills the blanks. Kept as pure functions so they're easy to swap and
 * to unit-test.
 * ------------------------------------------------------------------ */

const CHAR_SUGGESTIONS = {
  want: 'See the one promise they broke finally kept.',
  avoid: 'Being owed anything.',
  pressure: 'Goes very still, then very precise.',
  contradiction: 'Craves a home, distrusts locks.',
  whenTheyCare: 'Fixes the thing, not the mood.',
  exampleLine: '“I don’t take second chances. I take first ones, carefully.”',
  styleTags: ['Dry asides', 'Honest in writing']
} as const

export function suggestCharacter(draft: CharacterDraft): void {
  if (!draft.want) draft.want = CHAR_SUGGESTIONS.want
  if (!draft.avoid) draft.avoid = CHAR_SUGGESTIONS.avoid
  if (!draft.pressure) draft.pressure = CHAR_SUGGESTIONS.pressure
  if (!draft.contradiction) draft.contradiction = CHAR_SUGGESTIONS.contradiction
  if (!draft.whenTheyCare) draft.whenTheyCare = CHAR_SUGGESTIONS.whenTheyCare
  if (!draft.exampleLine) draft.exampleLine = CHAR_SUGGESTIONS.exampleLine
  if (!draft.styleTags.length) draft.styleTags = [...CHAR_SUGGESTIONS.styleTags]
}

const WORLD_SUGGESTIONS = {
  terrain: ['River valley', 'Woodland'],
  architecture: 'Timber and pale stone, weathered copper roofs, modest village squares.',
  details: 'Mossy riverbanks, woven market awnings, quiet traces of old magic.',
  exclusions: 'Modern machinery, towering castles'
} as const

export function suggestWorld(draft: WorldDraft): void {
  if (!draft.terrain.length) draft.terrain = [...WORLD_SUGGESTIONS.terrain]
  if (!draft.architecture) draft.architecture = WORLD_SUGGESTIONS.architecture
  if (!draft.details) draft.details = WORLD_SUGGESTIONS.details
  if (!draft.exclusions) draft.exclusions = WORLD_SUGGESTIONS.exclusions
}

/* ------------------------------------------------------------------ *
 * Scene samples for the world preview (DEMO copy — narrator-authored in
 * production, keyed here by time-of-day + weather).
 * ------------------------------------------------------------------ */

const WORLD_SAMPLES: Record<string, string> = {
  'Morning|Clear':
    'Sunlight catches the canvas awnings. Beside the old well, traders arrange apples and exchange the morning news.',
  'Morning|Light rain':
    'Rain taps a rhythm on the awnings. The well runs silver, and everyone shares the same narrow dry spots.',
  'Midday|Clear':
    'The square hums at full pitch — prices argued, dogs asleep in shade, a kite caught briefly in a weathervane.',
  'Dusk|Fog':
    'Lanterns bloom early in the fog. Voices arrive before their owners, and the well becomes a rumor of itself.',
  'Night|Clear':
    'The stalls are lidded in canvas now; the square belongs to cats, lovers, and one very deliberate set of footsteps.',
  'Night|First snow':
    'Snow muffles the cobblestones to velvet. Smoke and starlight trade places overhead; the well wears a white cap.'
}

export function worldSample(
  time: string,
  weather: string,
  placeName: string,
  details: string
): string {
  const canned = WORLD_SAMPLES[`${time}|${weather}`]
  if (canned) return canned
  const tail = details.toLowerCase() || 'light doing quiet, unhurried work.'
  return `The ${placeName.toLowerCase()} at ${time.toLowerCase()}, under ${weather.toLowerCase()} — ${tail}`
}

/** Initial behavior toggles for the Behavior tab (mock; all but one on). */
export function defaultTraits(): Record<string, boolean> {
  return Object.fromEntries(BEHAVIOR_TRAITS.map((t, i) => [t, i !== 1]))
}
