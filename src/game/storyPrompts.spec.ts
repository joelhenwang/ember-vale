import { describe, expect, it } from 'vitest'
import { IMAGE_LIMIT, storyWordsFrom, storyWordsRequest, validateStoryWords } from './storyPrompts'

const VIEW = {
  world_id: 'w',
  llm_prefix: 'Keep it grim.',
  image_suffix: 'muted colours',
  version: 3,
  characters: [
    { character_id: 'a', name: 'Ash', prefix: '', suffix: '' },
    {
      character_id: 'w',
      name: 'Wren',
      prefix: 'tall,',
      suffix: 'red scarf',
      portrait_asset_id: 'p'
    }
  ]
}

describe('story words', () => {
  it('reads the server view into a form', () => {
    const form = storyWordsFrom(VIEW)
    expect(form.llmPrefix).toBe('Keep it grim.')
    expect(form.llmSuffix).toBe('')
    expect(form.characters.map((c) => [c.name, c.suffix, c.portraitAssetId])).toEqual([
      ['Ash', '', null],
      ['Wren', 'red scarf', 'p']
    ])
  })

  it('sends trimmed words and only the characters that changed', () => {
    const baseline = storyWordsFrom(VIEW)
    const form = storyWordsFrom(VIEW)
    form.imagePrefix = '  storybook,  '
    form.characters[0].suffix = 'grey cloak '
    const request = storyWordsRequest(form, baseline, 3)
    expect(request.image_prefix).toBe('storybook,')
    expect(request.expected_version).toBe(3)
    expect(request.characters).toEqual([{ character_id: 'a', prefix: '', suffix: 'grey cloak' }])
  })

  it('keeps words within what the AI and the painter read', () => {
    const form = storyWordsFrom(VIEW)
    expect(validateStoryWords(form)).toEqual({})
    form.imageSuffix = 'x'.repeat(IMAGE_LIMIT + 1)
    form.characters[1].prefix = 'y'.repeat(IMAGE_LIMIT + 1)
    expect(Object.keys(validateStoryWords(form)).sort()).toEqual([
      'character:w:prefix',
      'imageSuffix'
    ])
  })
})
