/**
 * Deliberate adoption of a published preset revision (E3 nested return).
 *
 * The studio never switches the wizard automatically: publishing returns
 * to the owning story draft with an adoption offer, and the wizard applies
 * it only on explicit accept. Adoption pins `published_revision` exactly —
 * never the Library head — and touches nothing else, so the original
 * story's other pins stay unchanged. Pure functions, tested in
 * adoption.spec.ts (including the journey proof: a new story uses the
 * adopted revision while the original selections stay unchanged).
 */

import type { NewStorySelections } from './drafting'

export interface AdoptionOffer {
  kind: 'world' | 'character'
  presetId: string
  revision: number
}

export function parseAdoptionOffer(query: Record<string, unknown>): AdoptionOffer | null {
  const kind = query['adopt_kind']
  const preset = query['adopt_preset']
  const raw = query['adopt_revision']
  const revision = typeof raw === 'string' ? Number(raw) : typeof raw === 'number' ? raw : NaN
  if (
    (kind === 'world' || kind === 'character') &&
    typeof preset === 'string' &&
    preset.length > 0 &&
    Number.isInteger(revision) &&
    revision >= 1
  ) {
    return { kind, presetId: preset, revision }
  }
  return null
}

/**
 * Apply an accepted offer to a copy of the selections. The input is never
 * mutated: callers can prove the original story is unchanged by comparing
 * against it. A character offer with no matching cast member is a no-op
 * (never an implicit add); a world offer re-pins world id and revision.
 */
export function applyAdoption(
  selections: NewStorySelections,
  offer: AdoptionOffer
): NewStorySelections {
  if (offer.kind === 'world') {
    return {
      ...selections,
      world: { presetId: offer.presetId, presetRevision: offer.revision }
    }
  }
  return {
    ...selections,
    cast: selections.cast.map((m) =>
      m.presetId === offer.presetId ? { ...m, presetRevision: offer.revision } : m
    )
  }
}
