/**
 * The character studio's steps and fields, described once: which step a
 * field sits on, what it asks, and how long an answer may be. The writing
 * helper (fill the empty fields from the overview) and the portrait
 * painter read the same descriptions, so neither drifts from the form.
 */

import type { CharacterDraft } from './studio'

export const CHARACTER_STEPS = [
  { title: 'Overview', sub: 'Who are they, in your own words? A few key points are enough.' },
  { title: 'Appearance', sub: 'How they look, and their picture.' },
  { title: 'Background & personality', sub: 'Where they come from and what moves them.' },
  { title: 'Voice', sub: 'How they sound, and a few things they would say.' },
  { title: 'Review', sub: 'What they carry and how they are, then make it real.' }
] as const

/** The text fields the writing helper may fill (styleTags and selects stay the player's). */
export type WritableKey =
  | 'age'
  | 'race'
  | 'sex'
  | 'hair'
  | 'eyes'
  | 'height'
  | 'body'
  | 'marks'
  | 'history'
  | 'traits'
  | 'habits'
  | 'want'
  | 'avoid'
  | 'pressure'
  | 'contradiction'
  | 'boundaries'
  | 'secretFear'
  | 'tone'
  | 'whenTheyCare'
  | 'exampleLine'
  | 'wears'
  | 'carries'
  | 'condition'

export interface FieldSpec {
  key: WritableKey
  /** 1-based step it sits on. */
  step: number
  label: string
  /** What a good answer looks like (also shown as the placeholder). */
  hint: string
  max: number
}

export const CHARACTER_FIELDS: FieldSpec[] = [
  { key: 'age', step: 2, label: 'Age', hint: 'a number, e.g. 25', max: 20 },
  { key: 'race', step: 2, label: 'Race', hint: 'e.g. Human, Elf, Dwarf', max: 40 },
  { key: 'sex', step: 2, label: 'Sex', hint: 'Male, Female or Other', max: 20 },
  { key: 'hair', step: 2, label: 'Hair', hint: 'e.g. short and messy black hair', max: 120 },
  { key: 'eyes', step: 2, label: 'Eyes', hint: 'e.g. black', max: 60 },
  { key: 'height', step: 2, label: 'Height', hint: 'tall, average or short', max: 20 },
  {
    key: 'body',
    step: 2,
    label: 'Body',
    hint: 'e.g. wide muscular chest, long arms and legs',
    max: 300
  },
  {
    key: 'marks',
    step: 2,
    label: 'Extra',
    hint: 'e.g. a scar over the right eye, a tattoo, anything that marks them out',
    max: 300
  },
  {
    key: 'history',
    step: 3,
    label: 'Background',
    hint: 'where they grew up, what happened to them, what brought them here',
    max: 1200
  },
  {
    key: 'traits',
    step: 3,
    label: 'Personality',
    hint: 'a few traits, e.g. patient, stubborn, quick to laugh',
    max: 300
  },
  {
    key: 'habits',
    step: 3,
    label: 'Habits & behaviours',
    hint: 'what they do without thinking, e.g. hums while working',
    max: 300
  },
  { key: 'want', step: 3, label: 'What they want', hint: 'the want under the want', max: 300 },
  {
    key: 'avoid',
    step: 3,
    label: 'What they avoid',
    hint: 'the thing they never say out loud',
    max: 300
  },
  { key: 'pressure', step: 3, label: 'Under pressure', hint: 'how the mask slips', max: 300 },
  {
    key: 'contradiction',
    step: 3,
    label: 'A contradiction',
    hint: 'two truths about them that do not fit',
    max: 300
  },
  {
    key: 'boundaries',
    step: 3,
    label: 'Will not cross',
    hint: 'a line they keep, even for someone they love',
    max: 300
  },
  {
    key: 'secretFear',
    step: 3,
    label: 'Secret fear',
    hint: 'the fear that gets quieter, not louder',
    max: 300
  },
  {
    key: 'tone',
    step: 4,
    label: 'Tone',
    hint: 'how they come across when they speak, e.g. dry and warm, curt, florid',
    max: 200
  },
  {
    key: 'whenTheyCare',
    step: 4,
    label: 'When they care',
    hint: 'what care looks like from them',
    max: 300
  },
  {
    key: 'exampleLine',
    step: 4,
    label: 'Things they would say',
    hint: 'two or three lines in their own voice, one per line',
    max: 600
  },
  {
    key: 'wears',
    step: 5,
    label: 'Equipped',
    hint: 'what they wear and wield, e.g. oilskin coat, short sword',
    max: 300
  },
  {
    key: 'carries',
    step: 5,
    label: 'Carried',
    hint: 'what is in their pack and pockets',
    max: 300
  },
  {
    key: 'condition',
    step: 5,
    label: 'Physical state',
    hint: 'how they are right now, e.g. rested, a bandaged forearm',
    max: 200
  }
]

export function fieldsOnStep(step: number): FieldSpec[] {
  return CHARACTER_FIELDS.filter((f) => f.step === step)
}

/** The fields as the writing helper sees them: filled ones are context. */
export function writingFields(draft: CharacterDraft, only?: (f: FieldSpec) => boolean) {
  return CHARACTER_FIELDS.filter((f) => !only || only(f)).map((f) => ({
    key: f.key,
    label: f.label,
    hint: f.hint,
    value: draft[f.key],
    max_length: f.max
  }))
}

/** Everything else the player decided, given as context to the writing helper. */
export function writingContext(draft: CharacterDraft) {
  const extra = [
    { key: 'pronouns', label: 'Pronouns', value: draft.pronouns },
    { key: 'styles', label: 'Speaking style', value: draft.styleTags.join(', ') },
    { key: 'strangers', label: 'With strangers', value: draft.withStrangers }
  ]
  return extra
    .filter((e) => e.value.trim())
    .map((e) => ({ key: e.key, label: e.label, hint: '', value: e.value, max_length: 200 }))
}

/** How many of the writable fields are still empty. */
export function emptyCount(draft: CharacterDraft, step?: number): number {
  return CHARACTER_FIELDS.filter((f) => (step ? f.step === step : true)).filter(
    (f) => !draft[f.key].trim()
  ).length
}

/**
 * Words for painting them, from how they look: who (age, sex, race),
 * then hair, eyes, build, marks and what they wear. Empty when the
 * appearance says nothing yet.
 */
export function portraitPrompt(draft: CharacterDraft): string {
  const age = draft.age.trim()
  const who = [
    age ? (/^\d+$/.test(age) ? `${age}-year-old` : age) : '',
    draft.sex.trim().toLowerCase(),
    draft.race.trim()
  ]
    .filter(Boolean)
    .join(' ')
  // Fragments read as one description: "auburn hair", "wearing a coat".
  const soft = (text: string) => text.trim().replace(/^[A-Z](?=[a-z ])/, (c) => c.toLowerCase())
  const parts = [
    who,
    draft.height.trim() && draft.height.trim().toLowerCase() !== 'average'
      ? `${draft.height.trim().toLowerCase()}`
      : '',
    draft.hair.trim() && `${soft(draft.hair)}${/hair/i.test(draft.hair) ? '' : ' hair'}`,
    draft.eyes.trim() && `${soft(draft.eyes)}${/eye/i.test(draft.eyes) ? '' : ' eyes'}`,
    soft(draft.body),
    soft(draft.marks),
    draft.wears.trim() && `wearing ${soft(draft.wears)}`
  ].filter(Boolean)
  if (!parts.length) return ''
  if (!who && draft.appearanceExtra.trim()) parts.push(draft.appearanceExtra.trim())
  return parts.join(', ').slice(0, 1200)
}

/** One line under their name: age, race, sex, height. */
export function identityLine(draft: CharacterDraft): string {
  const age = draft.age.trim()
  const cap = (t: string) => t.charAt(0).toUpperCase() + t.slice(1)
  return [
    age ? (/^\d+$/.test(age) ? `${age} years` : age) : '',
    cap(draft.race.trim()),
    cap(draft.sex.trim()),
    cap(draft.height.trim())
  ]
    .filter(Boolean)
    .join(' · ')
}
