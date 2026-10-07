import { describe, expect, it } from 'vitest'
import {
  compassRows,
  conceptRows,
  emptyCount,
  gist,
  identityLine,
  portraitPrompt,
  sayings,
  stepSummaries,
  voiceFields,
  writingFields
} from './characterForm'
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

describe('step panels', () => {
  const mara = {
    ...ensureCharDraft('form-spec-panels'),
    overview: 'Ferry-clan girl, 17, apprenticed to the bell-keepers. Curious.',
    age: '17',
    race: 'Human',
    sex: 'Female',
    hair: 'dark brown braid',
    eyes: 'sea-gray',
    history: 'Raised among the ferry clans of the Saltreach. Later a bell-keeper.',
    traits: 'curious, stubborn',
    want: 'To learn why the city sank.',
    secretFear: 'That the bells are silent for good.',
    carries: "her grandmother's brass bell, a coil of line",
    tone: 'Bright and practical, with dry humor.',
    exampleLine: '"That wasn\'t the wind."\n\n“Hold the rope.”'
  }

  it('reads the concept from the draft, first sentences only', () => {
    expect(conceptRows(mara).map((r) => r.text)).toEqual([
      'Raised among the ferry clans of the Saltreach.',
      'To learn why the city sank.',
      "her grandmother's brass bell"
    ])
  })

  it('cuts long text at a word', () => {
    expect(gist('one two three four five six', 12)).toBe('one two…')
  })

  it('shows the compass, empty where unwritten', () => {
    const rows = compassRows(mara)
    expect(rows.map((r) => r.label)).toEqual([
      'Wants',
      'Fears',
      'Will not cross',
      'Inner tension',
      'Under pressure'
    ])
    expect(rows[2].text).toBe('')
  })

  it('lists sayings without quote marks', () => {
    expect(sayings(mara)).toEqual(["That wasn't the wind.", 'Hold the rope.'])
  })

  it('gives the sample writer only their voice', () => {
    const keys = voiceFields(mara).map((f) => f.key)
    expect(keys).toEqual(['traits', 'tone', 'exampleLine', 'strangers'])
  })

  it('summarises each step for the review', () => {
    const lines = stepSummaries(mara)
    expect(lines[1].text).toBe('17 years · Human · Female · dark brown braid · sea-gray eyes')
    expect(lines[2].text).toBe('curious, stubborn · To learn why the city sank.')
  })
})
