import { computed, reactive } from 'vue'
import type { CastCategory, SortMode } from './filters'
import type { CharacterDef, PackDef, WorldDef } from './model'

/**
 * Creative archive — the same data the Library page browses and the
 * New Story wizard picks from. Mock for now; production swaps the seed
 * arrays for engine-backed lists without touching components.
 */
export const catalog = reactive({
  characters: [
    {
      id: 'wren',
      name: 'Wren',
      role: 'Traveler',
      blurb: 'Quick eyes, a quicker smile, and a habit of asking “what if?”',
      bio: 'Quick-eyed, curious, and always ready to follow the road others overlook.',
      tags: [{ label: 'Human' }, { label: 'Explorer' }, { label: 'Player-ready', tone: 'green' }],
      imageSlot: 'character.wren',
      categories: ['travelers', 'companions'],
      playerReady: true,
      usedInStories: 2,
      revision: null,
      updatedAt: 6
    },
    {
      id: 'ash',
      name: 'Ash',
      role: 'Wanderer',
      blurb: 'A steady presence, shaped by long roads and hard winters.',
      bio: 'A steady presence shaped by long roads, cold nights, and careful promises.',
      tags: [{ label: 'Human' }, { label: 'Guardian' }, { label: 'Player-ready', tone: 'green' }],
      imageSlot: 'character.ash',
      categories: ['travelers', 'companions'],
      playerReady: true,
      usedInStories: 1,
      revision: null,
      updatedAt: 5
    },
    {
      id: 'lyria',
      name: 'Lyria',
      role: 'Wayfinder',
      blurb: 'Sees deeper, asks kinder questions, and believes in people.',
      bio: 'Sees connections where others see borders.',
      tags: [{ label: 'Human' }, { label: 'Guide' }, { label: 'Player-ready', tone: 'green' }],
      imageSlot: 'character.lyria',
      categories: ['companions', 'scholars'],
      playerReady: true,
      usedInStories: 3,
      revision: null,
      updatedAt: 4
    },
    {
      id: 'miri',
      name: 'Miri',
      role: 'Scholar',
      blurb: 'Finds wonder in the ordinary and stories in everything.',
      bio: 'Questions uncover brighter tomorrows.',
      tags: [{ label: 'Human' }, { label: 'Scholar' }, { label: 'Player-ready', tone: 'green' }],
      imageSlot: 'character.miri',
      categories: ['scholars', 'companions'],
      playerReady: true,
      usedInStories: 1,
      revision: null,
      updatedAt: 3
    },
    {
      id: 'thomas',
      name: 'Thomas',
      role: 'Blacksmith',
      blurb: 'Strong hands. Kinder people.',
      bio: 'Strong hands. Kinder people.',
      tags: [
        { label: 'Human' },
        { label: 'Craftsman', tone: 'rose' },
        { label: 'Player-ready', tone: 'green' }
      ],
      imageSlot: 'character.thomas',
      categories: ['locals'],
      playerReady: true,
      usedInStories: 1,
      revision: null,
      updatedAt: 2
    },
    {
      id: 'nessa',
      name: 'Nessa',
      role: 'Ferrywoman',
      blurb: 'Knows every shortcut the river allows.',
      bio: 'Knows every shortcut the river allows — and half the stories they carry.',
      tags: [{ label: 'Human' }, { label: 'Local' }, { label: 'NPC' }],
      imageSlot: 'character.nessa',
      categories: ['locals'],
      playerReady: false,
      usedInStories: 1,
      revision: null,
      updatedAt: 1
    }
  ] satisfies CharacterDef[],

  worlds: [
    {
      id: 'ember-vale',
      name: 'Ember Vale',
      blurb: 'A welcoming valley with old secrets.',
      tags: [
        { label: 'Cozy fantasy', tone: 'tan' },
        { label: 'Low magic', tone: 'green' }
      ],
      imageSlot: 'world.emberVale',
      places: 2,
      usedInStories: 2,
      status: 'ready',
      revision: null,
      updatedAt: 7
    },
    {
      id: 'silverleaf-coast',
      name: 'Silverleaf Coast',
      blurb: 'Harbor towns, sea winds, and forgotten ruins.',
      tags: [
        { label: 'Adventure', tone: 'blue' },
        { label: 'High magic', tone: 'purple' }
      ],
      imageSlot: 'world.silverleaf',
      places: 5,
      usedInStories: 1,
      status: 'ready',
      revision: null,
      updatedAt: 6
    }
  ] satisfies WorldDef[],

  stylePacks: [
    {
      id: 'house-style',
      name: 'Ember Vale House Style',
      blurb: 'Warm, wry, wonder-forward narration with gentle stakes.',
      tags: [
        { label: 'Tone', tone: 'tan' },
        { label: 'Default', tone: 'green' }
      ],
      usedInStories: 4,
      updatedAt: 9
    }
  ] satisfies PackDef[],

  templates: [
    {
      id: 'fable',
      name: 'Fable Starter',
      blurb: 'A short moral-shaped tale for a single evening.',
      tags: [{ label: 'Starter' }],
      usedInStories: 1,
      updatedAt: 3
    },
    {
      id: 'slowburn',
      name: 'Slow-Burn Mystery',
      blurb: 'Clues, debts, and a town that talks in whispers.',
      tags: [{ label: 'Serialized' }],
      usedInStories: 1,
      updatedAt: 2
    }
  ] satisfies PackDef[]
})

/* ------------------------------------------------------------------ *
 * New Story wizard (step 2: cast selection)
 * ------------------------------------------------------------------ */

export type WizardCategory = CastCategory

export const wizard = reactive({
  /** 1 World · 2 Characters · 3 Play Mode · 4 Story · 5 AI · 6 Review */
  step: 2,
  selected: ['wren', 'ash'] as string[],
  search: '',
  category: 'all' as WizardCategory,
  sort: 'name' as SortMode
})

export const selectedCharacters = computed<CharacterDef[]>(() =>
  wizard.selected.map((id) => catalog.characters.find((c) => c.id === id)!).filter(Boolean)
)

export function toggleCharacter(id: string): void {
  const i = wizard.selected.indexOf(id)
  if (i >= 0) wizard.selected.splice(i, 1)
  else wizard.selected.push(id)
}

/* ------------------------------------------------------------------ *
 * Library page UI state
 * ------------------------------------------------------------------ */

export const libraryUi = reactive({
  search: '',
  chip: 'all',
  sort: 'recent' as SortMode,
  view: 'grid' as 'grid' | 'list'
})

export function resetLibraryFilters(): void {
  libraryUi.search = ''
  libraryUi.chip = 'all'
}
