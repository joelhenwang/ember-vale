import { describe, expect, it } from 'vitest'
import { ref } from 'vue'
import type { CallOptions } from '../api/worldsim'
import type {
  ChronicleEntry,
  PresentationResponse,
  RoleGrantView
} from '../../content/clients/worldsim'
import { useAdventure, type AdventureApi } from './useAdventure'

const WORLD = 'w1'
const ME = 'wren'
const HEARTH = 'hearth'

function presentation(index: number): PresentationResponse {
  return {
    world_id: WORLD,
    day: 1,
    phase: 'dawn',
    absolute_index: index,
    revision: index,
    capabilities: { role: 'player', character_id: ME, capabilities: ['advance'] },
    manifest: { id: 'm', version: 1, schematic: true, anchors: [] },
    cast: [
      { character_id: ME, name: 'Wren', life_status: 'alive', location_id: HEARTH },
      { character_id: 'ash', name: 'Ash', life_status: 'alive', location_id: HEARTH }
    ]
  } as unknown as PresentationResponse
}

function entry(sequence: number, text: string): ChronicleEntry {
  return {
    sequence,
    event_id: `e${sequence}`,
    event_type: 'action_resolved',
    title: text,
    text,
    absolute_index: sequence,
    location_id: HEARTH,
    participant_ids: [ME]
  }
}

function fakeApi(over: Partial<AdventureApi> = {}) {
  const calls: { advance: [number, Record<string, unknown>, CallOptions][] } = { advance: [] }
  let index = 0
  let told: ChronicleEntry[] = []
  const api: AdventureApi = {
    getRole: async () => ({ role: 'player', character_id: ME }) as unknown as RoleGrantView,
    getStory: async () => ({ title: 'T' }) as never,
    openStory: async () => ({ title: 'A Morning' }) as never,
    getMap: async () => ({ world_id: WORLD, places: [{ id: HEARTH, name: 'Hearth' }] }) as never,
    getPresentation: async () => presentation(index),
    getChronicle: async () =>
      ({
        entries: told,
        has_more: false,
        next_after: told.length,
        watermark: told.length
      }) as never,
    getSceneNarration: async () => [],
    getCharacter: async () => ({ id: ME, name: 'Wren', state: { stamina: 80, mana: 40 } }) as never,
    getSuggestions: async () => [],
    listItems: async () => ({ world_id: WORLD, owner_id: ME, members: [] }) as never,
    advance: async (_w, i, intents, opts) => {
      calls.advance.push([i, intents, opts])
      index = i
      told = [...told, entry(told.length + 1, 'Wren looks around the Hearth.')]
      return {} as never
    },
    ...over
  }
  return { api, calls }
}

const never = (): (() => void) => () => undefined

describe('useAdventure', () => {
  it('opens as the player, at their place, with who is there', async () => {
    const { api } = fakeApi()
    const adv = useAdventure(ref(WORLD), { api, schedule: never })
    await adv.load()
    expect(adv.me.value).toBe(ME)
    expect(adv.title.value).toBe('A Morning')
    expect(adv.here.value?.name).toBe('Hearth')
    expect(adv.present.value.map((c) => c.name)).toEqual(['Ash'])
  })

  it('sends one action as the next beat and tells what happened', async () => {
    const { api, calls } = fakeApi()
    const adv = useAdventure(ref(WORLD), { api, schedule: never })
    await adv.load()
    const ok = await adv.act({ family: 'observe', character_id: ME })
    expect(ok).toBe(true)
    const [index, intents, opts] = calls.advance[0]
    expect(index).toBe(1)
    expect(Object.keys(intents)).toEqual([ME])
    expect(opts).toMatchObject({ role: 'player', characterId: ME })
    expect(adv.log.value.map((l) => l.text)).toContain('Wren looks around the Hearth.')
    expect(adv.acting.value).toBe(false)
  })

  it('says a slow turn is still going rather than failing', async () => {
    const { api } = fakeApi({
      advance: async () => {
        throw new Error('request timed out')
      }
    })
    const adv = useAdventure(ref(WORLD), { api, schedule: never })
    await adv.load()
    expect(await adv.wait()).toBe(false)
    expect(adv.actionError.value).toMatch(/slow to answer/)
  })
})
