/**
 * Deliberate adoption of a published preset revision (E3 nested return).
 *
 * The studio never switches the wizard automatically: publishing — or a
 * first-preset creation returning to its calling draft — returns with an
 * adoption offer, and the wizard applies it only on explicit accept.
 * Adoption pins the offered revision exactly — never the Library head —
 * and touches nothing else, so the original story's other pins stay
 * unchanged. A character offer for a preset outside the cast adds it
 * (the wizard caps the cast at six); it never edits anything implicitly.
 *
 * Every offer carries its originating story draft (`draftId`). An offer
 * applies only to that draft: a delayed return that lands while another
 * draft is mounted must switch to (or ignore for) the originating draft,
 * never modify the other one. The wizard also keeps the offer until the
 * new pins persist successfully — a failed save retains the offer — and
 * restores the previous pins when a failed accept is dismissed.
 */

import type { NewStorySelections } from './drafting'

export interface AdoptionOffer {
  kind: 'world' | 'character'
  presetId: string
  revision: number
  /** Originating story draft: the only draft this offer may modify. */
  draftId: string
  /** True when the offer returns a first-preset creation, not a publish. */
  created: boolean
}

export function parseAdoptionOffer(query: Record<string, unknown>): AdoptionOffer | null {
  const kind = query['adopt_kind']
  const preset = query['adopt_preset']
  const raw = query['adopt_revision']
  const draft = query['adopt_draft']
  const revision = typeof raw === 'string' ? Number(raw) : typeof raw === 'number' ? raw : NaN
  if (
    (kind === 'world' || kind === 'character') &&
    typeof preset === 'string' &&
    preset.length > 0 &&
    Number.isInteger(revision) &&
    revision >= 1 &&
    typeof draft === 'string' &&
    draft.length > 0
  ) {
    return {
      kind,
      presetId: preset,
      revision,
      draftId: draft,
      created: query['adopt_created'] === '1'
    }
  }
  return null
}

/** True only when the offer belongs to the currently mounted draft. */
export function offerTargetsDraft(offer: AdoptionOffer, draftId: string | null): boolean {
  return draftId !== null && offer.draftId === draftId
}

export type AdoptionPlan =
  | { kind: 'apply-world' }
  | { kind: 'apply-character' }
  | { kind: 'apply-character-add' }
  | { kind: 'cast-full' }
  | { kind: 'stale-draft' }
  | { kind: 'unknown-target' }

/** The wizard caps the cast at six members. */
export const MAX_CAST = 6

/**
 * Decide what an offer means for the mounted draft without touching
 * anything. `worldKnown` names whether the offered world preset is on
 * the shelf; `charKnown` names the same for a character preset.
 * Character offers re-pin a matching member, or add a known preset
 * outside a non-full cast on explicit accept.
 */
export function planAdoption(
  offer: AdoptionOffer,
  selections: NewStorySelections,
  draftId: string | null,
  worldKnown: boolean,
  charKnown = false
): AdoptionPlan {
  if (!offerTargetsDraft(offer, draftId)) return { kind: 'stale-draft' }
  if (offer.kind === 'world') {
    return worldKnown ? { kind: 'apply-world' } : { kind: 'unknown-target' }
  }
  const member = selections.cast.find((m) => m.presetId === offer.presetId)
  if (member) return { kind: 'apply-character' }
  if (!charKnown) return { kind: 'unknown-target' }
  return selections.cast.length >= MAX_CAST
    ? { kind: 'cast-full' }
    : { kind: 'apply-character-add' }
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

/**
 * The pins an adoption accept may change, for rollback on dismiss:
 * world pins, cast revision pins, and cast starting locations (which
 * reconciliation may reset). Keyed by cast member key.
 */
export interface PinSnapshot {
  worldId: string
  worldRev: number
  castRevs: Record<string, number>
  castLocs: Record<string, string>
}

export function snapshotPins(selections: NewStorySelections): PinSnapshot {
  const castRevs: Record<string, number> = {}
  const castLocs: Record<string, string> = {}
  for (const m of selections.cast) {
    castRevs[m.key] = m.presetRevision
    castLocs[m.key] = m.locationKey ?? ''
  }
  return {
    worldId: selections.world.presetId,
    worldRev: selections.world.presetRevision,
    castRevs,
    castLocs
  }
}

/** True when the live selections still carry exactly the snapshotted pins. */
export function pinsEqual(snapshot: PinSnapshot, selections: NewStorySelections): boolean {
  if (
    snapshot.worldId !== selections.world.presetId ||
    snapshot.worldRev !== selections.world.presetRevision
  ) {
    return false
  }
  const live = snapshotPins(selections)
  const aKeys = Object.keys(snapshot.castRevs).sort()
  const bKeys = Object.keys(live.castRevs).sort()
  return (
    aKeys.length === bKeys.length &&
    aKeys.every(
      (k, i) =>
        k === bKeys[i] &&
        snapshot.castRevs[k] === live.castRevs[k] &&
        snapshot.castLocs[k] === live.castLocs[k]
    )
  )
}

/**
 * The mutable pin surface an adoption accept or dismiss drives: the
 * wizard form shape (`location`, not the payload's `locationKey`).
 */
export interface RestorablePins {
  worldId: string
  worldRev: number
  cast: { key: string; presetRevision: number; location: string }[]
}

/** Write a snapshot back onto live pins (dismissal after a failed accept). */
export function restoreSnapshot(target: RestorablePins, snapshot: PinSnapshot): void {
  target.worldId = snapshot.worldId
  target.worldRev = snapshot.worldRev
  for (const member of target.cast) {
    const rev = snapshot.castRevs[member.key]
    if (rev !== undefined) member.presetRevision = rev
    if (member.key in snapshot.castLocs) {
      member.location = snapshot.castLocs[member.key] ?? member.location
    }
  }
}
