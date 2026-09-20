/**
 * Pure draft-payload construction for the New Story wizard (C2).
 *
 * Kept Vue-free and unit-tested: the view collects selections, this module
 * builds the exact `StoryDraftPayload` JSON the backend validates. Revision
 * pins are exact — drafts never silently upgrade.
 */

export interface DraftCastSelection {
  key: string
  presetId: string
  presetRevision: number
  name: string
  locationKey?: string
}

export interface DraftWorldSelection {
  presetId: string
  presetRevision: number
  name?: string
}

export interface DraftModeSelection {
  role: 'watcher' | 'player' | 'director' | 'deity'
  controlledKey?: string
}

export interface NewStorySelections {
  world: DraftWorldSelection
  cast: DraftCastSelection[]
  mode: DraftModeSelection
  title: string
  tone?: string
  artSource?: string
}

export type DraftPayloadJson = Record<string, unknown>

/** Build the payload JSON for create/patch draft requests. */
export function buildDraftPayload(selections: NewStorySelections): DraftPayloadJson {
  return {
    world: {
      preset_id: selections.world.presetId,
      preset_revision: selections.world.presetRevision,
      ...(selections.world.name ? { name: selections.world.name } : {})
    },
    cast: selections.cast.map((member) => ({
      instance_key: member.key,
      preset_id: member.presetId,
      preset_revision: member.presetRevision,
      name: member.name,
      ...(member.locationKey ? { location_key: member.locationKey } : {})
    })),
    mode: {
      role: selections.mode.role,
      ...(selections.mode.controlledKey
        ? { controlled_cast_key: selections.mode.controlledKey }
        : {})
    },
    story: {
      title: selections.title,
      ...(selections.tone ? { tone: selections.tone } : {})
    },
    ai: { art_source: selections.artSource ?? 'curated' }
  }
}

/** Structural issues the wizard can check before asking the server. */
export function localDraftIssues(selections: NewStorySelections): string[] {
  const issues: string[] = []
  const keys = selections.cast.map((c) => c.key)
  if (new Set(keys).size !== keys.length) issues.push('cast keys must be unique')
  if (!selections.cast.length) issues.push('select at least one character')
  if (!selections.title.trim()) issues.push('give the story a title')
  if (selections.mode.role === 'player') {
    if (!selections.mode.controlledKey) issues.push('player mode needs a controlled character')
    else if (!keys.includes(selections.mode.controlledKey)) {
      issues.push('controlled character is not in the cast')
    }
  }
  return issues
}

/** Drop a removed cast member's controlled selection (caller must re-ask). */
export function controlledAfterCastChange(
  castKeys: string[],
  controlledKey: string | undefined
): string | undefined {
  if (controlledKey === undefined) return undefined
  return castKeys.includes(controlledKey) ? controlledKey : undefined
}
