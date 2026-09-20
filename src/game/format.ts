/**
 * Pure display mapping for real backend records (C5).
 *
 * Real timestamps and phases in, honest labels out. Nothing here invents
 * history: missing data renders as explicitly unknown, never as prose.
 */

import type { StoryTimeOfDay } from './stories'

/** Relative label for an ISO last-played timestamp, or an honest fallback. */
export function lastPlayedLabel(iso: string | null | undefined, nowMs?: number): string {
  if (!iso) return 'Not yet opened'
  const then = Date.parse(iso)
  if (Number.isNaN(then)) return 'Played before'
  const now = nowMs ?? Date.now()
  const minutes = Math.max(0, Math.round((now - then) / 60000))
  if (minutes < 1) return 'Played just now'
  if (minutes < 60) return `Played ${minutes} minute${minutes === 1 ? '' : 's'} ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `Played ${hours} hour${hours === 1 ? '' : 's'} ago`
  const days = Math.floor(hours / 24)
  if (days === 1) return 'Played yesterday'
  if (days < 30) return `Played ${days} days ago`
  return `Played on ${new Date(then).toLocaleDateString()}`
}

/** Bucket a backend phase string into the shelf's day-part display. */
export function phaseToTimeOfDay(phase: string): StoryTimeOfDay {
  const p = phase.toLowerCase()
  if (p.includes('morn') || p.includes('dawn') || p.includes('sunrise')) return 'Morning'
  if (p.includes('dusk') || p.includes('evening') || p.includes('sunset')) return 'Evening'
  if (p.includes('night') || p.includes('midnight')) return 'Night'
  return 'Afternoon'
}

/** Title-case a phase for display ("sunrise" -> "Sunrise"). */
export function phaseLabel(phase: string): string {
  if (!phase) return 'Unknown'
  return phase.charAt(0).toUpperCase() + phase.slice(1)
}
