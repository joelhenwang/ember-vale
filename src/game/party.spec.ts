import { describe, expect, it } from 'vitest'
import type { PartyMemberView } from '../../content/clients/worldsim'
import {
  abilityMod,
  addAbilityPoint,
  choiceWaiting,
  heroLine,
  joinedAs,
  improvementReady,
  hpTone,
  levelledUp,
  onlyExperience,
  partyHurt,
  partyOrder,
  sayRoll,
  slotLine,
  slotsLeftLine,
  xpProgress
} from './party'

function member(id: string, character: string | null): PartyMemberView {
  return {
    id,
    world_id: 'w',
    name: id,
    level: 1,
    character_class: 'fighter',
    version: 0,
    character_id: character
  }
}

describe('party', () => {
  it('names the hero in plain words', () => {
    expect(heroLine('half-elf', 'wizard')).toBe('Half-elf wizard, level 1')
    expect(heroLine(null, 'rogue', 3)).toBe('Rogue, level 3')
  })

  it('says what a companion joined as', () => {
    expect(joinedAs('Ash', 'human', 'ranger')).toBe('Ash joined as a human ranger')
    expect(joinedAs('Lyra', 'elf', 'cleric')).toBe('Lyra joined as an elf cleric')
    expect(joinedAs('Bo', null, 'fighter')).toBe('Bo joined as a fighter')
  })

  it('puts the hero first, companions after', () => {
    const order = partyOrder([member('lyra', null), member('wren', 'me')], 'me')
    expect(order.map((m) => m.id)).toEqual(['wren', 'lyra'])
  })

  it('reads hurt from the share of health left', () => {
    expect(hpTone(12, 12)).toBe('well')
    expect(hpTone(6, 12)).toBe('hurt')
    expect(hpTone(3, 12)).toBe('low')
    expect(hpTone(0, 12)).toBe('down')
  })

  it('lists spell slots a day by level', () => {
    expect(slotLine([2, 1])).toBe('2 first-level, 1 second-level')
    expect(slotLine([])).toBe('')
  })

  it('says a roll: who, with what, the die against the defence, what it did', () => {
    const said = sayRoll({
      kind: 'attack',
      text: 'Wren hits Goblin for 6 slashing. (7->1 HP)',
      actor: 'Wren',
      target: 'Goblin',
      using: 'Longsword',
      roll: 17,
      natural: 12,
      ac: 15,
      result: 'hit',
      amount: 6,
      damage_type: 'slashing',
      hp_before: 7,
      hp_after: 1,
      target_foe: true
    })
    expect(said).toEqual({
      lead: 'Wren attacks Goblin',
      using: 'with Longsword',
      check: '17 vs AC 15',
      natural: 12,
      outcome: 'Hit · 6 slashing',
      hp: 'Goblin 7 → 1',
      tone: 'hit'
    })
  })

  it('says a healing potion drunk', () => {
    const said = sayRoll({
      kind: 'potion',
      text: 'Wren drinks a potion of healing: 7 hit points (3->10 HP).',
      actor: 'Wren',
      target: 'Wren',
      using: 'potion of healing',
      result: 'healed',
      amount: 7,
      hp_before: 3,
      hp_after: 10
    })
    expect([said.lead, said.outcome, said.hp, said.tone]).toEqual([
      'Wren drinks a potion of healing',
      'Healed 7',
      'Wren 3 → 10',
      'heal'
    ])
  })

  it('says a night in a room and a sale plainly', () => {
    const slept = sayRoll({
      kind: 'rest',
      text: 'Wren sleeps in a room for the night: 4->12 HP.',
      actor: 'Wren',
      using: 'room for the night',
      amount: 8,
      hp_before: 4,
      hp_after: 12,
      result: 'healed'
    })
    expect([slept.lead, slept.outcome, slept.hp, slept.tone]).toEqual([
      'Wren sleeps in a room for the night',
      'Rested · healed 8',
      'Wren 4 → 12',
      'heal'
    ])
    const sold = sayRoll({ kind: 'sell', text: '', actor: 'Wren', using: 'scimitar', amount: 3 })
    expect([sold.lead, sold.outcome]).toEqual(['Wren sells the scimitar', '+3 gold'])
  })

  it('says an ability check: who tried what, against how hard, how it went', () => {
    const said = sayRoll({
      kind: 'check',
      text: "Wren's Athletics check: 9 against DC 12, partial.",
      actor: 'Wren',
      using: 'Athletics',
      roll: 9,
      natural: 6,
      dc: 12,
      result: 'partial'
    })
    expect(said).toEqual({
      lead: 'Wren tries Athletics',
      using: null,
      check: '9 vs DC 12',
      natural: 6,
      outcome: 'Partly',
      hp: null,
      tone: 'save'
    })
    expect(sayRoll({ kind: 'check', text: '', actor: 'Ash', result: 'failure' }).tone).toBe('miss')
  })

  it('says a blow on a foe already down plainly', () => {
    const late = sayRoll({
      kind: 'attack',
      text: '',
      actor: 'Wren',
      target: 'Goblin',
      result: 'hit',
      amount: 5,
      hp_before: 0,
      hp_after: 0
    })
    expect(late.hp).toBe('Goblin was already down')
    const shrug = sayRoll({
      kind: 'cast',
      text: '',
      actor: 'Ash',
      target: 'Goblin',
      hp_before: 6,
      hp_after: 6
    })
    expect(shrug.hp).toBeNull()
    const topped = sayRoll({
      kind: 'cast',
      text: '',
      actor: 'Ash',
      target: 'Wren',
      result: 'healed',
      amount: 3,
      hp_before: 12,
      hp_after: 12
    })
    expect(topped.hp).toBe('Wren was already at full health')
  })

  it('says saves, heals, foes that land and recruits', () => {
    const save = sayRoll({
      kind: 'cast',
      text: '',
      actor: 'Ash',
      target: 'Goblin',
      using: 'Fireball',
      roll: 9,
      natural: 7,
      dc: 13,
      result: 'failed',
      amount: 8,
      damage_type: 'fire'
    })
    expect([save.lead, save.using]).toEqual(['Ash casts Fireball at Goblin', null])
    expect(save.check).toBe('Goblin rolls 9 vs DC 13')
    expect(save.outcome).toBe('Fails the save · 8 fire')
    const heal = sayRoll({
      kind: 'cast',
      text: '',
      actor: 'Ash',
      target: 'Wren',
      using: 'Cure Wounds',
      result: 'healed',
      amount: 5
    })
    expect([heal.lead, heal.outcome, heal.tone]).toEqual(['Ash heals Wren', 'Healed 5', 'heal'])
    const foe = {
      kind: 'attack',
      text: '',
      actor: 'Goblin',
      target: 'Wren',
      using: 'Scimitar',
      result: 'hit',
      amount: 4,
      actor_foe: true
    }
    expect(sayRoll(foe).tone).toBe('hurt')
    expect(partyHurt([foe], 'Wren')).toBe(true)
    expect(sayRoll({ kind: 'recruit', text: '', actor: 'Lyra' }).lead).toBe('Lyra joins the party')
  })
})

describe('combat depth', () => {
  const wren = {
    id: 'w',
    world_id: 'x',
    name: 'Wren',
    level: 2,
    character_class: 'cleric',
    version: 1,
    xp: 340,
    xp_level_start: 300,
    xp_next_level: 900,
    spell_slots: [3],
    spell_slots_left: [1]
  }

  it('says XP, a level gained and a spell with no slot left', () => {
    const xp = sayRoll({ kind: 'xp', text: '', target: 'Goblin 2', amount: 50, share: 25 })
    expect([xp.lead, xp.outcome]).toEqual(['Goblin 2 is defeated', '50 XP · 25 each'])
    const up = sayRoll({ kind: 'level', text: '', actor: 'Wren', level: 2, amount: 8 })
    expect([up.lead, up.outcome, up.tone]).toEqual([
      'Level up! Wren reaches level 2',
      '+8 hit points',
      'level'
    ])
    const dry = sayRoll({
      kind: 'cast',
      text: '',
      actor: 'Wren',
      using: 'Cure Wounds',
      result: 'no-slot'
    })
    expect([dry.lead, dry.outcome, dry.tone]).toEqual([
      'Wren tries Cure Wounds',
      'No spell slot left · it fails',
      'miss'
    ])
    expect(levelledUp([{ kind: 'level', text: '', actor: 'Wren', level: 2 }])).toEqual(['Wren'])
    expect(levelledUp(undefined)).toEqual([])
  })

  it('measures XP toward the next level and the slots left today', () => {
    expect(xpProgress(wren)).toEqual({ fraction: 0.4 / 6, label: '340 / 900 XP' })
    expect(xpProgress({ ...wren, xp_next_level: null }).fraction).toBe(1)
    expect(slotsLeftLine(wren)).toBe('1 of 3 first-level')
  })
})

describe('a settled rumour', () => {
  it('says the matter is settled and what each gained', () => {
    const all = sayRoll({
      kind: 'xp',
      result: 'settled',
      text: '',
      target: 'The missing flour',
      amount: 100,
      share: 50
    })
    expect([all.lead, all.outcome, all.tone]).toEqual([
      'The missing flour is settled',
      '50 XP each',
      'info'
    ])
    const some = sayRoll({
      kind: 'xp',
      result: 'settled',
      text: '',
      target: 'The cart',
      actor: 'Elara',
      share: 150
    })
    expect(some.outcome).toBe('Elara: 150 XP each')
  })

  it('knows experience with no dice', () => {
    const earned = { kind: 'xp', result: 'settled', text: '', share: 50 }
    const up = { kind: 'level', text: '', actor: 'Wren', level: 2 }
    expect(onlyExperience([earned, up])).toBe(true)
    expect(onlyExperience([earned, { kind: 'attack', text: '' }])).toBe(false)
    expect(onlyExperience([])).toBe(false)
  })
})

describe('level-up choices', () => {
  const scores = { str: 16, dex: 12, con: 19, int: 8, wis: 10, cha: 10 }

  it('builds +2 to one or +1 to two, within the cap', () => {
    let picks = addAbilityPoint({}, 'str', scores)
    expect(improvementReady(picks)).toBe(false)
    picks = addAbilityPoint(picks, 'str', scores)
    expect(picks).toEqual({ str: 2 })
    expect(improvementReady(picks)).toBe(true)
    // a third press on the same ability clears it
    expect(addAbilityPoint(picks, 'str', scores)).toEqual({})
    // +1 and +1
    picks = addAbilityPoint(addAbilityPoint({}, 'str', scores), 'dex', scores)
    expect(picks).toEqual({ str: 1, dex: 1 })
    expect(improvementReady(picks)).toBe(true)
    // con 19 takes one point, not two
    expect(addAbilityPoint({ con: 1 }, 'con', scores)).toEqual({ con: 1 })
    // full already: a new ability starts over
    expect(addAbilityPoint({ str: 2 }, 'wis', scores)).toEqual({ wis: 1 })
  })

  it('says the modifier and what waits', () => {
    expect(abilityMod(16)).toBe('+3')
    expect(abilityMod(8)).toBe('-1')
    expect(choiceWaiting('ability,spells')).toBe(
      'choose a better ability and new spells in Character details'
    )
    expect(choiceWaiting(null)).toBe('')
    const said = sayRoll({
      kind: 'level',
      text: 'x',
      actor: 'Wren',
      level: 4,
      amount: 7,
      choose: 'ability'
    })
    expect(said.outcome).toBe('+7 hit points · choose a better ability in Character details')
  })
})

describe('getting back up', () => {
  it('says the fallen hero is up again', () => {
    const said = sayRoll({ kind: 'recover', text: 'x', actor: 'Wren', hp_before: 0, hp_after: 1 })
    expect(said.lead).toBe('Wren gets back up')
    expect(said.hp).toBe('Wren 0 → 1')
    expect(said.tone).toBe('heal')
  })
})

describe('spoils', () => {
  it('says what a fallen foe left', () => {
    expect(sayRoll({ kind: 'loot', text: 'x', actor: 'Goblin 2', using: 'scimitar' }).lead).toBe(
      'Goblin 2 left a scimitar'
    )
    expect(sayRoll({ kind: 'loot', text: 'x', actor: 'Zombie', using: '5 gold coins' }).lead).toBe(
      'Zombie left 5 gold coins'
    )
    expect(sayRoll({ kind: 'loot', text: 'x', actor: 'Goblin', using: 'a few coins' }).lead).toBe(
      'Goblin left a few coins'
    )
  })
})
