import { reactive } from 'vue'
import type { GameMenuState } from './model'

/**
 * The menu's display model. Home populates `current`/`recent` from the
 * backend story list on every visit — nothing here is seed content. An
 * empty backend renders the honest empty hero, never a fabricated tale.
 */
export const menuState = reactive<GameMenuState>({
  player: { name: 'Lyria', avatarSlot: 'player.avatar' },
  current: null,
  recent: [],
  quickStartWorld: 'Ember Vale',
  motto: 'Curiosity is a kind of courage.'
})
