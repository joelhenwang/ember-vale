import { describe, expect, it } from 'vitest'
import {
  branchTitle,
  canBranch,
  canRewind,
  originLine,
  pathNotTakenTitle,
  turnLabel
} from './branches'

describe('branches', () => {
  it('labels turns as the server does', () => {
    expect(turnLabel(2)).toBe('Day 1, morning')
    expect(turnLabel(9)).toBe('Day 1, midnight')
    expect(turnLabel(17)).toBe('Day 2, evening')
  })

  it('names a branch after its source and turn, once', () => {
    expect(branchTitle('The Ledger', 2)).toBe('The Ledger — from Day 1, morning')
    expect(branchTitle('The Ledger — from Day 1, morning', 17)).toBe(
      'The Ledger — from Day 2, evening'
    )
    expect(branchTitle('x'.repeat(200), 2).length).toBe(128)
  })

  it('offers the action only on kept turns', () => {
    const kept = new Set([1, 2, 5])
    expect(canBranch(kept, 2)).toBe(true)
    expect(canBranch(kept, 3)).toBe(false)
    expect(canBranch(kept, 0)).toBe(false)
    expect(canBranch(kept, null)).toBe(false)
  })

  it('says where a story came from', () => {
    expect(originLine({ title: 'The Ledger', time_label: 'Day 1, morning' })).toBe(
      'Branched from The Ledger at Day 1, morning'
    )
    expect(originLine(null)).toBeNull()
  })

  it('names the path not taken after the turn it ends at, once', () => {
    expect(pathNotTakenTitle('The Ledger', 5)).toBe(
      'The Ledger — the path not taken (Day 1, sunset)'
    )
    expect(pathNotTakenTitle('The Ledger — the path not taken (Day 1, sunset)', 17)).toBe(
      'The Ledger — the path not taken (Day 2, evening)'
    )
    expect(branchTitle('The Ledger — the path not taken (Day 1, sunset)', 2)).toBe(
      'The Ledger — from Day 1, morning'
    )
  })

  it('offers going back only to kept turns before a kept newest turn', () => {
    const kept = new Set([1, 2, 5])
    expect(canRewind(kept, 5, 2)).toBe(true)
    expect(canRewind(kept, 5, 5)).toBe(false)
    expect(canRewind(kept, 5, 3)).toBe(false)
    expect(canRewind(kept, 6, 2)).toBe(false)
    expect(canRewind(kept, null, 2)).toBe(false)
  })
})
