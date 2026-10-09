/**
 * Branching a story from one of its turns: the wording shared by the
 * Adventure log, the Watch feed, the confirmation and the Stories list.
 * The title mirrors the server's (`branch_title` in domain/branches.py).
 */

import { PHASES } from './observatory'

/** "Day 2, evening", as the server writes it in titles. */
export function turnLabel(index: number): string {
  const day = Math.floor(index / PHASES.length) + 1
  const phase = PHASES[((index % PHASES.length) + PHASES.length) % PHASES.length]
  return `Day ${day}, ${phase}`
}

const FROM_SUFFIX = /\s+—\s+(from Day \d+, \w+|the path not taken \(Day \d+, \w+\))$/

function titled(source: string, suffix: string): string {
  const base = source.trim().replace(FROM_SUFFIX, '') || 'Story'
  return base.slice(0, 128 - suffix.length).trimEnd() + suffix
}

/** "The Saltreach — from Day 2, evening"; a branch of a branch keeps one suffix. */
export function branchTitle(source: string, index: number): string {
  return titled(source, ` — from ${turnLabel(index)}`)
}

/**
 * The story that keeps the turns "Go back to this turn" removes, named after
 * the turn that path ends at: "The Saltreach — the path not taken (Day 3, dusk)".
 */
export function pathNotTakenTitle(source: string, latest: number): string {
  return titled(source, ` — the path not taken (${turnLabel(latest)})`)
}

export interface OriginLike {
  title: string
  time_label: string
}

/** The Stories list line: "Branched from The Ledger at Day 1, morning". */
export function originLine(origin: OriginLike | null | undefined): string | null {
  if (!origin) return null
  return `Branched from ${origin.title} at ${origin.time_label}`
}

/** Whether a turn heading offers "Branch from here" (its end state was kept). */
export function canBranch(kept: ReadonlySet<number>, index: number | null | undefined): boolean {
  return typeof index === 'number' && index >= 1 && kept.has(index)
}

/**
 * Whether a turn heading offers "Go back to this turn": a kept turn before the
 * newest one, and the newest turn kept too (it is saved as its own story first).
 */
export function canRewind(
  kept: ReadonlySet<number>,
  latest: number | null | undefined,
  index: number | null | undefined
): boolean {
  return (
    canBranch(kept, index) &&
    typeof latest === 'number' &&
    kept.has(latest) &&
    (index as number) < latest
  )
}

/** One key per confirmation: a retry gets the same new story, never a second. */
export function newBranchKey(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) return crypto.randomUUID()
  return `branch-${Date.now()}-${Math.random().toString(16).slice(2)}`
}
