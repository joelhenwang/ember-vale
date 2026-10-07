/**
 * Key moments: the story's painted pictures, as Home and the moment view
 * show them. A picture painted before moments had headlines gets one from
 * what kind of moment it was.
 */

import type { BeatView, SceneArtView } from '../../content/clients/worldsim'
import { beatTimeLabel } from './observatory'

const KIND_TITLES: Record<string, string> = {
  turning: 'A turning point',
  arrival: 'A new arrival',
  meeting: 'A first meeting',
  settled: 'A rumour laid to rest',
  manual: 'A moment remembered'
}

/** The pictures ready to show, oldest first. */
export function readyMoments(art: readonly SceneArtView[] | null | undefined): SceneArtView[] {
  return (art ?? []).filter((a) => a.status === 'ready' && a.asset_id)
}

/** The newest painted moment, if any. */
export function latestMoment(art: readonly SceneArtView[] | null | undefined): SceneArtView | null {
  const ready = readyMoments(art)
  return ready.length ? ready[ready.length - 1] : null
}

/** Its headline: the writer's, or one from the kind of moment. */
export function momentTitle(moment: Pick<SceneArtView, 'title' | 'moment'>): string {
  return moment.title?.trim() || KIND_TITLES[moment.moment] || 'A moment remembered'
}

/** "Oarfall Harbor · Day 1, Night" (the place only when known). */
export function momentWhen(
  moment: Pick<SceneArtView, 'phase_index'>,
  place?: string | null
): string {
  const when = beatTimeLabel(moment.phase_index ?? 0).replace(' · ', ', ')
  return place ? `${place} · ${when}` : when
}

export interface Speaker {
  name: string
  portraitUrl: string | null
}

/** One line of a moment's scene: told by the narrator or said by someone. */
export type MomentLine =
  { kind: 'told'; text: string } | { kind: 'said'; text: string; speaker: Speaker }

/**
 * A scene's narration as the moment view reads it: spoken beats beside
 * their speaker's face, the rest as prose. Speakers the viewer has not
 * met yet still show by name ("Someone" when even that is unknown).
 */
export function momentLines(
  beats: readonly BeatView[],
  speakers: ReadonlyMap<string, Speaker>
): MomentLine[] {
  const lines: MomentLine[] = []
  for (const beat of beats) {
    const text = beat.text.trim()
    if (!text || beat.kind === 'system') continue
    if (beat.speaker_id && beat.kind === 'dialogue') {
      lines.push({
        kind: 'said',
        text,
        speaker: speakers.get(beat.speaker_id) ?? { name: 'Someone', portraitUrl: null }
      })
    } else {
      lines.push({ kind: 'told', text })
    }
  }
  return lines
}
