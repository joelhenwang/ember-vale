import { describe, expect, it } from 'vitest'
import { emptyCount, identityLine, portraitPrompt, writingFields } from './characterForm'
import { ensureCharDraft } from './studio'

describe('character form', () => {
  it('paints from how they look, as one description', () => {
    const draft = { ...ensureCharDraft('form-spec-a') }
    expect(portraitPrompt(draft)).toBe('')
    Object.assign(draft, {
      age: '24',
      sex: 'Female',
      race: 'Half-elf',
      height: 'Average',
      hair: 'Dark auburn, braided',
      eyes: 'Hazel-green',
      body: 'Lean and wiry',
      marks: 'A pale scar on her chin',
      wears: 'A river coat'
    })
    expect(portraitPrompt(draft)).toBe(
      '24-year-old female Half-elf, dark auburn, braided hair, hazel-green eyes, lean and wiry, a pale scar on her chin, wearing a river coat'
    )
    expect(identityLine(draft)).toBe('24 years · Half-elf · Female · Average')
  })

  it('tells the writing helper which fields are empty, and counts them per step', () => {
    const draft = { ...ensureCharDraft('form-spec-b'), hair: 'Black' }
    const fields = writingFields(draft, (f) => f.step === 2)
    expect(fields.find((f) => f.key === 'hair')).toMatchObject({ value: 'Black', label: 'Hair' })
    expect(
      fields.every((f) =>
        ['age', 'race', 'sex', 'hair', 'eyes', 'height', 'body', 'marks'].includes(f.key)
      )
    ).toBe(true)
    expect(emptyCount(draft, 2)).toBe(7)
    expect(emptyCount(draft)).toBe(22)
  })
})
