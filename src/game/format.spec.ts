import { describe, expect, it } from 'vitest'
import { lastPlayedLabel, phaseLabel, phaseToTimeOfDay } from './format'

describe('backend display mapping', () => {
  it('labels real timestamps relatively and missing ones honestly', () => {
    const now = Date.parse('2026-09-20T12:00:00Z')
    expect(lastPlayedLabel(null, now)).toBe('Not yet opened')
    expect(lastPlayedLabel(undefined, now)).toBe('Not yet opened')
    expect(lastPlayedLabel('2026-09-20T11:59:40Z', now)).toBe('Played just now')
    expect(lastPlayedLabel('2026-09-20T11:30:00Z', now)).toBe('Played 30 minutes ago')
    expect(lastPlayedLabel('2026-09-20T09:00:00Z', now)).toBe('Played 3 hours ago')
    expect(lastPlayedLabel('2026-09-19T12:00:00Z', now)).toBe('Played yesterday')
    expect(lastPlayedLabel('2026-09-10T12:00:00Z', now)).toBe('Played 10 days ago')
    expect(lastPlayedLabel('not-a-date', now)).toBe('Played before')
  })

  it('buckets backend phases into shelf day-parts', () => {
    expect(phaseToTimeOfDay('sunrise')).toBe('Morning')
    expect(phaseToTimeOfDay('morning')).toBe('Morning')
    expect(phaseToTimeOfDay('dusk')).toBe('Evening')
    expect(phaseToTimeOfDay('night')).toBe('Night')
    expect(phaseToTimeOfDay('afternoon')).toBe('Afternoon')
    expect(phaseToTimeOfDay('daybreak')).toBe('Afternoon')
  })

  it('title-cases phases and names the unknown', () => {
    expect(phaseLabel('sunrise')).toBe('Sunrise')
    expect(phaseLabel('')).toBe('Unknown')
  })
})
