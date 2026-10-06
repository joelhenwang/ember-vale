import { describe, expect, it } from 'vitest'
import type { BeatView, ChronicleEntry, SuggestionView } from '../../content/clients/worldsim'
import {
  NIL_SNAPSHOT,
  buildLog,
  cardDrives,
  isFresh,
  leadChips,
  inSentence,
  doIntent,
  doPrompt,
  firstSentence,
  prologue,
  quickChips,
  sayIntent,
  sceneFocus,
  scenesToLoad,
  suggestionIntent,
  trimPlaceLead,
  turnChanges,
  levelProgress,
  type Glimpse
} from './adventure'

const ME = 'me'
const HERE = 'hearth'

function entry(over: Partial<ChronicleEntry> & { sequence: number }): ChronicleEntry {
  return {
    absolute_index: 1,
    event_id: `e${over.sequence}`,
    event_type: 'action_resolved',
    title: 't',
    ...over
  }
}

function beat(id: string, kind: string, text: string, speaker: string | null = null): BeatView {
  return { id, kind, text, speaker_id: speaker, source_event_id: 'x' }
}

describe('adventure log', () => {
  it('tells scenes you saw in full, spoken lines under their speaker', () => {
    const log = buildLog({
      entries: [entry({ sequence: 1, scene_id: 's1', participant_ids: [ME, 'ash'] })],
      beats: {
        s1: [
          beat('b1', 'narration', 'The fire cracks.'),
          beat('b2', 'dialogue', '"Morning," says Ash.', 'ash'),
          beat('b3', 'dialogue', '"Hello."', ME),
          beat('b4', 'system', 'internal')
        ]
      },
      me: ME,
      hereId: HERE
    })
    expect(log.map((l) => [l.kind, l.text, l.mine ?? false])).toEqual([
      ['time', 'Day 1 · Sunrise', false],
      ['narration', 'The fire cracks.', false],
      ['dialogue', '"Morning," says Ash.', false],
      ['dialogue', '"Hello."', true]
    ])
  })

  it('shows elsewhere as one sentence and drops idle moments elsewhere', () => {
    const log = buildLog({
      entries: [
        entry({
          sequence: 1,
          location_id: 'market',
          participant_ids: ['ash'],
          text: 'Ash haggles over apples. The seller relents.'
        }),
        entry({ sequence: 2, location_id: 'market', participant_ids: ['bo'], idle: true }),
        entry({ sequence: 3, event_type: 'world_ticked' })
      ],
      beats: {},
      me: ME,
      hereId: HERE
    })
    expect(log.map((l) => [l.kind, l.text])).toEqual([
      ['time', 'Day 1 · Sunrise'],
      ['elsewhere', 'Ash haggles over apples.']
    ])
  })

  it('says a scene is still being written until narration exists', () => {
    const input = {
      entries: [entry({ sequence: 1, scene_id: 's1', location_id: HERE, participant_ids: [ME] })],
      beats: {},
      me: ME,
      hereId: HERE
    }
    expect(buildLog(input).at(-1)?.kind).toBe('pending')
    expect(scenesToLoad(input)).toEqual(['s1'])
    expect(scenesToLoad({ ...input, beats: { s1: [beat('b', 'narration', 'x')] } })).toEqual([])
    // A scene nearby that the player was not in: its prose comes from the chronicle.
    const nearby = {
      ...input,
      entries: [entry({ sequence: 2, scene_id: 's2', location_id: HERE })]
    }
    expect(scenesToLoad(nearby)).toEqual([])
  })

  it('cuts to the first sentence', () => {
    expect(firstSentence('One. Two.')).toBe('One.')
    expect(firstSentence('No stop')).toBe('No stop')
  })
})

describe('adventure actions', () => {
  it('builds say and do intents the server accepts', () => {
    expect(sayIntent(ME, 'ash', '“Good morning”')).toEqual({
      character_id: ME,
      snapshot_id: NIL_SNAPSHOT,
      family: 'communicate',
      target_character_id: 'ash',
      topic: '"Good morning"'
    })
    expect(doIntent(ME, ' search the stall ')).toMatchObject({
      family: 'interact',
      attempt: 'search the stall'
    })
    expect(doIntent(ME, 'shake hands', 'ash')).toMatchObject({ target_character_id: 'ash' })
  })

  const s = (over: Partial<SuggestionView>): SuggestionView => ({
    id: over.family ?? 'x',
    family: 'rest',
    title: 'T',
    ...over
  })

  it('turns chips into intents, asking for words only when needed', () => {
    expect(
      suggestionIntent(ME, s({ family: 'move', destination_location_id: 'mkt' }))
    ).toMatchObject({ family: 'move', destination_location_id: 'mkt' })
    expect(suggestionIntent(ME, s({ family: 'take', item_instance_id: 'i1' }))).toMatchObject({
      family: 'take',
      item_instance_id: 'i1'
    })
    expect(
      suggestionIntent(
        ME,
        s({ family: 'transfer', item_instance_id: 'i1', target_character_id: 'ash' })
      )
    ).toMatchObject({ family: 'transfer', item_instance_id: 'i1', target_character_id: 'ash' })
    expect(suggestionIntent(ME, s({ family: 'communicate', target_character_id: 'ash' }))).toBe(
      null
    )
    expect(
      suggestionIntent(ME, s({ family: 'communicate', target_character_id: 'ash' }), 'hi')
    ).toMatchObject({ topic: '"hi"' })
  })

  it('orders quick chips: pick up, go, look, spar, rest', () => {
    const chips = quickChips([
      s({ family: 'rest' }),
      s({ family: 'appeal' }),
      s({ family: 'move' }),
      s({ family: 'take' }),
      s({ family: 'communicate' })
    ])
    expect(chips.map((c) => c.family)).toEqual(['take', 'move', 'rest'])
  })
})

describe('reading aids', () => {
  it('drops a place lead the label already says', () => {
    expect(trimPlaceLead('At the Market, Ash looks around.', 'Market')).toBe('Ash looks around.')
    expect(trimPlaceLead('Ash looks around.', 'Market')).toBe('Ash looks around.')
    expect(trimPlaceLead('At the Market, x', null)).toBe('At the Market, x')
  })

  it('opens with who you are and who is out there', () => {
    expect(
      prologue({
        name: 'Wren',
        place: 'Hearth',
        appearance: 'Quick eyes and a traveler’s coat.',
        others: [
          { name: 'Ash', place: 'Market' },
          { name: 'Tam', place: 'Hearth' }
        ]
      })
    ).toEqual([
      'You are Wren, at the Hearth.',
      'Quick eyes and a traveler’s coat.',
      'Tam is here with you.',
      'Ash is at the Market.'
    ])
  })
})

describe('scene framing', () => {
  it('centres the map close-up on the place', () => {
    expect(sceneFocus({ x: 0.25, y: 0.5 })).toEqual({
      backgroundPosition: '25% 50%',
      backgroundSize: '260%'
    })
    expect(sceneFocus(null).backgroundSize).toBe('cover')
  })
})

describe('sheet aids', () => {
  it('reads drive lines from a card', () => {
    expect(cardDrives('A wanderer.\nWants: find her brother.\nAvoids: promises.\nWants:')).toEqual([
      'Wants: find her brother.',
      'Avoids: promises.'
    ])
    expect(cardDrives(undefined)).toEqual([])
  })

  it('marks rumours fresh for two beats', () => {
    expect(isFresh(5, 7)).toBe(true)
    expect(isFresh(5, 8)).toBe(false)
    expect(isFresh(undefined, 1)).toBe(false)
  })
})

describe('turn feedback', () => {
  const at = (over: Partial<Glimpse>): Glimpse => ({
    place: 'Market',
    stamina: 80,
    mana: 50,
    items: [],
    present: ['Ash'],
    rumours: [],
    ...over
  })

  it('names what you gained, lost, met and heard', () => {
    const changes = turnChanges(
      at({ items: ['Tea cup', 'Tea cup'] }),
      at({
        items: ['Tea cup', 'Silver locket'],
        stamina: 70,
        present: ['Ash', 'Nessa'],
        rumours: ['A Market-stall Puzzle']
      })
    )
    expect(changes.map((c) => [c.text, c.tone])).toEqual([
      ['+ Silver locket', 'gain'],
      ['− Tea cup', 'loss'],
      ['Stamina −10', 'loss'],
      ['Nessa arrives', 'news'],
      ['New rumour: A Market-stall Puzzle', 'news']
    ])
  })

  it('says where you are now instead of who came and went', () => {
    const changes = turnChanges(at({}), at({ place: 'Hearth', present: [] }))
    expect(changes.map((c) => c.text)).toEqual(['Now at Hearth'])
  })

  it('celebrates a settled rumour', () => {
    const changes = turnChanges(
      at({ rumours: ['A Market-stall Puzzle'], settled: [] }),
      at({ rumours: [], settled: ['A Market-stall Puzzle'] })
    )
    expect(changes).toEqual([{ text: 'Settled: A Market-stall Puzzle', tone: 'gain' }])
  })

  it('marks renown gained and a new level', () => {
    const changes = turnChanges(
      at({ renown: 8, level: 1, title: 'Newcomer' }),
      at({ renown: 11, level: 2, title: 'Familiar face' })
    )
    expect(changes).toEqual([
      { text: '+3 renown', tone: 'gain' },
      { text: 'Now known as: Familiar face', tone: 'level' }
    ])
    expect(levelProgress(11, 10, 30)).toBeCloseTo(0.05)
  })

  it('is quiet when nothing changed', () => {
    expect(turnChanges(at({}), at({}))).toEqual([])
  })
})

describe('composer prompt', () => {
  it('points at a lead, then at someone near, then at the world', () => {
    expect(doPrompt('The Old Mill', ['Ash'])).toContain('“The Old Mill”')
    expect(doPrompt(null, ['Ash'])).toContain('help Ash')
    expect(doPrompt(null, [])).toContain('search the stalls')
  })
})

describe('lead chips', () => {
  it('asks someone here about the newest rumour and looks into it', () => {
    const chips = leadChips(ME, [{ title: 'The Old Mill' }], [{ character_id: 'ash', name: 'Ash' }])
    expect(chips.map((c) => c.label)).toEqual([
      'Ask Ash about “The Old Mill”',
      'Look into “The Old Mill”'
    ])
    expect(chips[0].intent).toMatchObject({ family: 'communicate', target_character_id: 'ash' })
    expect(chips[1].intent).toMatchObject({ family: 'interact', attempt: 'look into the Old Mill' })
    expect(leadChips(ME, [], [])).toEqual([])
    const article = leadChips(ME, [{ title: 'A stray dog' }], [])
    expect(article[0].intent).toMatchObject({ attempt: 'look into a stray dog' })
    expect(inSentence('The Old Mill')).toBe('the Old Mill')
    expect(inSentence('Old Mill')).toBe('Old Mill')
  })
})
