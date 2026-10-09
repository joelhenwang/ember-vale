import { describe, expect, it } from 'vitest'
import type { PartyMemberView } from '../../content/clients/worldsim'
import { heroLine, hpTone, partyHurt, partyOrder, sayRoll, slotLine } from './party'

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
