/**
 * What is for sale where the hero stands, as chips that fill the composer
 * with a plain Do attempt ("Buy a potion of healing for 6 gold coins").
 * A good the purse cannot pay for shows, but cannot be chosen (shops-001).
 */
import type { ShopResponse } from '../../content/clients/worldsim'

export interface BuyChip {
  key: string
  /** "Potion of healing · 6" */
  label: string
  /** What the composer is filled with. */
  attempt: string
  price: number
  affordable: boolean
  /** Why it cannot be chosen, when it cannot. */
  short: string | null
}

function coins(n: number): string {
  return n === 1 ? '1 gold coin' : `${n} gold coins`
}

function withArticle(name: string): string {
  return /^[aeiou]/i.test(name) ? `an ${name}` : `a ${name}`
}

export interface SellChip {
  key: string
  /** "Sell scimitar · 3" */
  label: string
  attempt: string
  price: number
}

/** What the hero could sell here, as chips (shops-002); none elsewhere. */
export function sellChips(shop: ShopResponse | null): SellChip[] {
  if (!shop?.buys?.length) return []
  return shop.buys.map((b) => ({
    key: b.item_id,
    label: `Sell ${b.name} · ${b.price} gold`,
    attempt: `Sell the ${b.name} for ${coins(b.price)}`,
    price: b.price
  }))
}

/** The buy chips for a shop; none when nothing is sold here. */
export function buyChips(shop: ShopResponse | null): BuyChip[] {
  if (!shop?.goods?.length) return []
  const purse = shop.purse ?? 0
  return shop.goods.map((g) => {
    const affordable = purse >= g.price
    return {
      key: g.key,
      label: `${g.name.charAt(0).toUpperCase()}${g.name.slice(1)} · ${g.price} gold`,
      attempt: `Buy ${withArticle(g.name)} for ${coins(g.price)}`,
      price: g.price,
      affordable,
      short: affordable ? null : `You carry ${coins(purse)}`
    }
  })
}
