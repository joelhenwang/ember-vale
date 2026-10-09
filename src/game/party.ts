/**
 * Combat stories (opt-in per story): the hero's choices in the New Story
 * wizard, and how the party panel and the story log say a fight's rolls.
 * Pure and Vue-free; the dice themselves are rolled on the server.
 */

import type { CombatRollView, FoeView, PartyMemberView } from '../../content/clients/worldsim'

export interface HeroChoice {
  key: string
  name: string
  blurb: string
}

/** The peoples a hero can be (the server's 5e tables, in plain words). */
export const HERO_RACES: HeroChoice[] = [
  { key: 'human', name: 'Human', blurb: 'Adaptable, a little good at everything.' },
  { key: 'elf', name: 'Elf', blurb: 'Quick and keen-eyed; sees in the dark.' },
  { key: 'dwarf', name: 'Dwarf', blurb: 'Stout and hard to fell.' },
  { key: 'halfling', name: 'Halfling', blurb: 'Small, nimble and lucky.' },
  { key: 'gnome', name: 'Gnome', blurb: 'Clever and curious.' },
  { key: 'half-elf', name: 'Half-elf', blurb: 'Charming, at home in two worlds.' },
  { key: 'half-orc', name: 'Half-orc', blurb: 'Strong, and slow to go down.' },
  { key: 'dragonborn', name: 'Dragonborn', blurb: 'Proud, with a breath of fire.' },
  { key: 'tiefling', name: 'Tiefling', blurb: 'Touched by old magic; quick-witted.' }
]

/** The callings a hero can follow; every hero starts at level 1. */
export const HERO_CLASSES: HeroChoice[] = [
  { key: 'fighter', name: 'Fighter', blurb: 'Sword and shield; steady in any fight.' },
  { key: 'rogue', name: 'Rogue', blurb: 'Quick and quiet; strikes where it hurts.' },
  { key: 'ranger', name: 'Ranger', blurb: 'Bow and blade; a tracker of the wilds.' },
  { key: 'cleric', name: 'Cleric', blurb: 'Heals the party and wears heavy mail.' },
  { key: 'wizard', name: 'Wizard', blurb: 'Book-learned spells; fragile but potent.' },
  { key: 'paladin', name: 'Paladin', blurb: 'A holy warrior bound by an oath.' },
  { key: 'barbarian', name: 'Barbarian', blurb: 'Fights in a rage; hits hard.' },
  { key: 'bard', name: 'Bard', blurb: 'Music, wit and a little magic.' },
  { key: 'druid', name: 'Druid', blurb: "Nature's magic; heals and calls the wild." },
  { key: 'monk', name: 'Monk', blurb: 'Fast hands and focus; no armour needed.' },
  { key: 'sorcerer', name: 'Sorcerer', blurb: 'Magic in the blood; fire at the fingertips.' },
  { key: 'warlock', name: 'Warlock', blurb: 'A pact for power; few but strong spells.' }
]

export const DEFAULT_HERO = { race: 'human', characterClass: 'fighter' }

export function choiceName(list: HeroChoice[], key: string | null | undefined): string {
  return (
    list.find((c) => c.key === key)?.name ?? (key ? key.charAt(0).toUpperCase() + key.slice(1) : '')
  )
}

/** "Human fighter, level 1". */
export function heroLine(race: string | null | undefined, cls: string, level = 1): string {
  const people = race ? choiceName(HERO_RACES, race) : ''
  const calling = choiceName(HERO_CLASSES, cls).toLowerCase()
  return `${people ? `${people} ${calling}` : choiceName(HERO_CLASSES, cls)}, level ${level}`
}

/** 0…1 for a hit-point bar; an unknown maximum reads as full. */
export function hpFraction(
  current: number | null | undefined,
  max: number | null | undefined
): number {
  if (!max || max <= 0) return 1
  return Math.min(1, Math.max(0, (current ?? max) / max))
}

/** How hurt someone looks: drives the bar's colour. */
export function hpTone(current: number | null | undefined, max: number | null | undefined) {
  const f = hpFraction(current, max)
  if ((current ?? 1) <= 0) return 'down'
  if (f <= 0.34) return 'low'
  if (f <= 0.67) return 'hurt'
  return 'well'
}

/** "2 first-level, 1 second-level" — slots a caster has each day. */
export function slotLine(slots: number[] | undefined): string {
  const names = [
    'first',
    'second',
    'third',
    'fourth',
    'fifth',
    'sixth',
    'seventh',
    'eighth',
    'ninth'
  ]
  return (slots ?? [])
    .map((n, i) => (n > 0 ? `${n} ${names[i] ?? `${i + 1}th`}-level` : ''))
    .filter(Boolean)
    .join(', ')
}

/** The hero first, then companions in the order they joined. */
export function partyOrder(members: PartyMemberView[], me: string | null): PartyMemberView[] {
  const hero = members.filter((m) => m.character_id && m.character_id === me)
  return [...hero, ...members.filter((m) => !hero.includes(m))]
}

export function foesStanding(foes: FoeView[] | undefined): number {
  return (foes ?? []).filter((f) => f.hp_current > 0).length
}

export type RollTone = 'hit' | 'crit' | 'miss' | 'heal' | 'save' | 'info' | 'hurt' | 'level'

export interface RollSay {
  /** "Wren attacks the Goblin" */
  lead: string
  /** "with a Longsword" */
  using: string | null
  /** "17 vs AC 15" (the d20 with its bonus against the defence). */
  check: string | null
  /** The die as it fell, for the d20 badge (a natural 20 or 1 is special). */
  natural: number | null
  /** "Hit · 6 slashing" */
  outcome: string | null
  /** "Goblin 7 → 1" */
  hp: string | null
  tone: RollTone
}

const OUTCOMES: Record<string, string> = {
  hit: 'Hit',
  crit: 'Critical hit',
  miss: 'Miss',
  saved: 'Shrugs it off',
  half: 'Half damage',
  failed: 'Fails the save',
  healed: 'Healed'
}

/** One roll in plain words for the story log. */
export function sayRoll(r: CombatRollView): RollSay {
  const actor = r.actor ?? ''
  const target = r.target ?? ''
  const kind = r.kind
  if (kind === 'encounter') {
    return {
      lead: `A fight begins: ${target || 'foes'}`,
      using: null,
      check: null,
      natural: null,
      outcome: r.result ? `${r.result.charAt(0).toUpperCase()}${r.result.slice(1)} fight` : null,
      hp: null,
      tone: 'info'
    }
  }
  if (kind === 'condition') {
    return {
      lead: `${target || 'Someone'} is ${String(r.using ?? 'affected').toLowerCase()}`,
      using: null,
      check: null,
      natural: null,
      outcome: null,
      hp: null,
      tone: 'info'
    }
  }
  if (kind === 'xp') {
    return {
      lead: `${target || 'The foe'} ${target.includes(',') ? 'are' : 'is'} defeated`,
      using: null,
      check: null,
      natural: null,
      outcome: `${r.amount ?? 0} XP${r.share != null && r.share !== r.amount ? ` · ${r.share} each` : ''}`,
      hp: null,
      tone: 'info'
    }
  }
  if (kind === 'level') {
    return {
      lead: `Level up! ${actor} reaches level ${r.level ?? '?'}`,
      using: null,
      check: null,
      natural: null,
      outcome: r.amount ? `+${r.amount} hit points` : null,
      hp: null,
      tone: 'level'
    }
  }
  if (r.result === 'no-slot') {
    return {
      lead: `${actor} tries ${r.using ?? 'a spell'}`,
      using: null,
      check: null,
      natural: null,
      outcome: 'No spell slot left · it fails',
      hp: null,
      tone: 'miss'
    }
  }
  if (kind === 'recruit') {
    return {
      lead: `${actor} joins the party`,
      using: null,
      check: null,
      natural: null,
      outcome: null,
      hp: null,
      tone: 'heal'
    }
  }
  if (kind === 'note' || (!actor && !target)) {
    return {
      lead: r.text,
      using: null,
      check: null,
      natural: null,
      outcome: null,
      hp: null,
      tone: 'info'
    }
  }
  const healing = r.result === 'healed'
  const spell = r.using ?? 'a spell'
  const lead = healing
    ? `${actor} heals ${target || 'no one'}`
    : kind === 'cast'
      ? `${actor} casts ${spell}${target ? ` at ${target}` : ''}`
      : `${actor} ${kind === 'spar' ? 'spars with' : 'attacks'} ${target}`
  const check =
    r.roll != null && r.ac != null
      ? `${r.roll} vs AC ${r.ac}`
      : r.roll != null && r.dc != null
        ? `${target} rolls ${r.roll} vs DC ${r.dc}`
        : null
  const said = r.result ? (OUTCOMES[r.result] ?? r.result) : null
  const harm =
    r.amount != null && r.amount > 0
      ? `${r.amount}${r.damage_type ? ` ${r.damage_type}` : ''}`
      : null
  const outcome = healing
    ? `Healed ${r.amount ?? 0}`
    : [said, harm].filter(Boolean).join(' · ') || null
  const hp =
    r.hp_before == null || r.hp_after == null || !target
      ? null
      : r.hp_before !== r.hp_after
        ? `${target} ${r.hp_before} → ${r.hp_after}`
        : r.hp_after === 0 && !healing
          ? `${target} was already down`
          : healing
            ? `${target} was already at full health`
            : null
  const tone: RollTone = healing
    ? 'heal'
    : r.result === 'miss' || r.result === 'saved'
      ? 'miss'
      : r.result === 'crit'
        ? 'crit'
        : r.actor_foe && (r.result === 'hit' || r.result === 'half' || r.result === 'failed')
          ? 'hurt'
          : r.result
            ? 'hit'
            : 'info'
  return {
    lead,
    using: kind === 'cast' && !healing ? null : r.using ? `with ${r.using}` : null,
    check,
    natural: r.natural ?? null,
    outcome,
    hp,
    tone
  }
}

/** Names of party members who reached a new level in these rolls. */
export function levelledUp(rolls: CombatRollView[] | undefined): string[] {
  return (rolls ?? []).filter((r) => r.kind === 'level' && r.actor).map((r) => r.actor as string)
}

/** Experience toward the next level, 0…1, and the words for it. */
export function xpProgress(m: PartyMemberView): { fraction: number; label: string } {
  const xp = m.xp ?? 0
  const start = m.xp_level_start ?? 0
  const next = m.xp_next_level
  if (next == null) return { fraction: 1, label: `${xp} XP · highest level` }
  const span = Math.max(1, next - start)
  return {
    fraction: Math.min(1, Math.max(0, (xp - start) / span)),
    label: `${xp} / ${next} XP`
  }
}

/** "1 of 3 first-level" — the slots still free today. */
export function slotsLeftLine(m: PartyMemberView): string {
  const names = [
    'first',
    'second',
    'third',
    'fourth',
    'fifth',
    'sixth',
    'seventh',
    'eighth',
    'ninth'
  ]
  const per = m.spell_slots ?? []
  const left = m.spell_slots_left ?? per
  return per
    .map((n, i) => (n > 0 ? `${left[i] ?? n} of ${n} ${names[i] ?? `${i + 1}th`}-level` : ''))
    .filter(Boolean)
    .join(', ')
}

/** A hit that hurt someone in the party (the view shakes their card). */
export function partyHurt(rolls: CombatRollView[], name: string): boolean {
  return rolls.some(
    (r) => r.target === name && !r.target_foe && (r.amount ?? 0) > 0 && r.result !== 'healed'
  )
}
