import { describe, expect, it } from 'vitest'
import { branchTitle, canBranch, originLine, turnLabel } from './branches'

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
})
