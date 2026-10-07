import { describe, expect, it } from 'vitest'
import {
  ensureCharDraft,
  ensureWorldDraft,
  isCharDirty,
  saveCharDraft,
  suggestCharacter,
  suggestWorld
} from './studio'

describe('character drafts', () => {
  it('seeds known characters and returns the same object for the same id', () => {
    const wren = ensureCharDraft('wren')
    expect(wren.want).not.toBe('')
    expect(ensureCharDraft('wren')).toBe(wren)
  })
  it('gives unknown ids (including "new") a blank draft', () => {
    const fresh = ensureCharDraft('someone-new')
    expect(fresh.want).toBe('')
    expect(fresh.appearanceSaved).toBe(false)
  })
  it('tracks the save/dirty cycle with snapshots', () => {
    const d = ensureCharDraft('dirty-cycle-test')
    expect(isCharDirty('dirty-cycle-test')).toBe(false)
    d.want = 'A want.'
    expect(isCharDirty('dirty-cycle-test')).toBe(true)
    saveCharDraft('dirty-cycle-test')
    expect(isCharDirty('dirty-cycle-test')).toBe(false)
    d.avoid = 'An avoid.'
    expect(isCharDirty('dirty-cycle-test')).toBe(true)
  })
  it('suggest only fills empty fields, never overwrites', () => {
    const d = ensureCharDraft('suggest-test')
    d.want = 'Mine, already.'
    d.avoid = ''
    suggestCharacter(d)
    expect(d.want).toBe('Mine, already.')
    expect(d.avoid).not.toBe('')
    expect(d.styleTags.length).toBeGreaterThan(0)
  })
})

describe('world drafts', () => {
  it('suggest fills every look field at once', () => {
    const d = ensureWorldDraft('suggest-world-test')
    suggestWorld(d)
    expect(d.architecture).not.toBe('')
    expect(d.details).not.toBe('')
    expect(d.exclusions).not.toBe('')
    expect(d.terrain.length).toBeGreaterThan(0)
  })
})
