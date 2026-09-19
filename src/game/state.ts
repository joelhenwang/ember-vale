import { reactive } from 'vue'
import type { GameMenuState } from './model'

/**
 * The menu's single source of truth. Mock for now — the real build hydrates
 * this from the story engine on boot and after each beat resolves.
 */
export const menuState = reactive<GameMenuState>({
  player: { name: 'Lyria', avatarSlot: 'player.avatar' },
  current: {
    id: 'sealed-gate',
    title: 'The Sealed Gate',
    beat: { day: 3, timeOfDay: 'Morning', location: 'The Market Forge' },
    logline:
      "A cryptic marking at the forge points toward the old archive. With new questions in hand, you prepare to follow the trail into the city's forgotten past.",
    imageSlot: 'hero.currentStory',
    mark: 'spark',
    pov: 'Player',
    epigraph: 'Small people. Large stories.'
  },
  recent: [
    {
      id: 'ashes-snow',
      title: 'Ashes Beneath the Snow',
      beat: { day: 8, timeOfDay: 'Dusk', location: 'Hollowridge Pass' },
      logline:
        'In the north, old debts wake beneath the ice. The mountain keeps its secrets, for now.',
      imageSlot: 'story.ashes',
      mark: 'spark',
      pov: 'Watcher'
    },
    {
      id: 'lantern-road',
      title: 'The Lantern Road',
      beat: { day: 2, timeOfDay: 'Night', location: 'Ferry Ward' },
      logline: "Strangers, lanterns, and a road that shouldn't exist. The journey continues.",
      imageSlot: 'story.lantern',
      mark: 'leaf',
      pov: 'Player'
    }
  ],
  quickStartWorld: 'Ember Vale',
  motto: 'Curiosity is a kind of courage.'
})
