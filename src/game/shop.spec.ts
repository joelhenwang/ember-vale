import { describe, expect, it } from 'vitest'
import { buyChips } from './shop'

const shop = {
  world_id: 'w',
  place: 'Market',
  purse: 3,
  goods: [
    { key: 'rope', name: 'rope', price: 1, description: '', keep: true },
    { key: 'ale', name: 'mug of ale', price: 1, description: '', keep: false },
    { key: 'healers-kit', name: "healer's kit", price: 3, description: '', keep: true },
    { key: 'potion-of-healing', name: 'potion of healing', price: 6, description: '', keep: true }
  ]
}

describe('buy chips', () => {
  it('fills the composer with a plain buy at the price', () => {
    const chips = buyChips(shop)
    expect(chips.map((c) => c.attempt)).toEqual([
      'Buy a rope for 1 gold coin',
      'Buy a mug of ale for 1 gold coin',
      "Buy a healer's kit for 3 gold coins",
      'Buy a potion of healing for 6 gold coins'
    ])
    expect(chips[3]!.label).toBe('Potion of healing · 6 gold')
  })

  it('shows what the purse cannot pay for, but not as a choice', () => {
    const chips = buyChips(shop)
    expect(chips.map((c) => c.affordable)).toEqual([true, true, true, false])
    expect(chips[3]!.short).toBe('You carry 3 gold coins')
  })

  it('offers nothing where nothing is sold', () => {
    expect(buyChips(null)).toEqual([])
    expect(buyChips({ world_id: 'w', place: null, goods: [], purse: 9 })).toEqual([])
  })
})
