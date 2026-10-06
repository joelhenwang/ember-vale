/**
 * Story settings: the player's own words around this story's prompts.
 * Vue-free: the form, its limits and the save request.
 *
 * Storyteller words wrap every AI prompt of the story's turns (characters,
 * narrator, director, summaries). Picture words wrap every image prompt;
 * a character's picture words wrap what is drawn of them (their portrait,
 * and scene pictures they are in).
 */
import type { StoryPromptsUpdate, StoryPromptsView } from '../../content/clients/worldsim'

export const LLM_LIMIT = 2000
export const IMAGE_LIMIT = 400

export interface CharacterWords {
  characterId: string
  name: string
  portraitAssetId: string | null
  prefix: string
  suffix: string
}

export interface StoryWordsForm {
  llmPrefix: string
  llmSuffix: string
  imagePrefix: string
  imageSuffix: string
  characters: CharacterWords[]
}

export function emptyStoryWords(): StoryWordsForm {
  return { llmPrefix: '', llmSuffix: '', imagePrefix: '', imageSuffix: '', characters: [] }
}

export function storyWordsFrom(view: StoryPromptsView): StoryWordsForm {
  return {
    llmPrefix: view.llm_prefix ?? '',
    llmSuffix: view.llm_suffix ?? '',
    imagePrefix: view.image_prefix ?? '',
    imageSuffix: view.image_suffix ?? '',
    characters: (view.characters ?? []).map((c) => ({
      characterId: c.character_id,
      name: c.name,
      portraitAssetId: c.portrait_asset_id ?? null,
      prefix: c.prefix ?? '',
      suffix: c.suffix ?? ''
    }))
  }
}

/** Field errors keyed like the form ("llmPrefix", "character:<id>:prefix"). */
export function validateStoryWords(form: StoryWordsForm): Record<string, string> {
  const errors: Record<string, string> = {}
  const check = (key: string, value: string, limit: number) => {
    if (value.length > limit) errors[key] = `At most ${limit} characters (${value.length} now).`
  }
  check('llmPrefix', form.llmPrefix, LLM_LIMIT)
  check('llmSuffix', form.llmSuffix, LLM_LIMIT)
  check('imagePrefix', form.imagePrefix, IMAGE_LIMIT)
  check('imageSuffix', form.imageSuffix, IMAGE_LIMIT)
  for (const c of form.characters) {
    check(`character:${c.characterId}:prefix`, c.prefix, IMAGE_LIMIT)
    check(`character:${c.characterId}:suffix`, c.suffix, IMAGE_LIMIT)
  }
  return errors
}

/** The save request; only characters whose words changed are sent. */
export function storyWordsRequest(
  form: StoryWordsForm,
  baseline: StoryWordsForm,
  version: number
): StoryPromptsUpdate {
  const before = new Map(baseline.characters.map((c) => [c.characterId, c]))
  return {
    llm_prefix: form.llmPrefix.trim(),
    llm_suffix: form.llmSuffix.trim(),
    image_prefix: form.imagePrefix.trim(),
    image_suffix: form.imageSuffix.trim(),
    characters: form.characters
      .filter((c) => {
        const old = before.get(c.characterId)
        return !old || old.prefix !== c.prefix || old.suffix !== c.suffix
      })
      .map((c) => ({
        character_id: c.characterId,
        prefix: c.prefix.trim(),
        suffix: c.suffix.trim()
      })),
    expected_version: version
  }
}

/** Examples the page offers to fill an empty field with one click. */
export const EXAMPLES = {
  llmPrefix: 'Tone: cosy and gently funny; keep danger low and kindness high.',
  llmSuffix: 'Use simple words a twelve-year-old would know.',
  imagePrefix: 'storybook watercolour,',
  imageSuffix: 'soft autumn light, muted colours',
  characterSuffix: 'always wears a red wool scarf'
} as const
