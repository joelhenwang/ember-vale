import { describe, expect, it } from 'vitest'
import {
  applyMotion,
  isAmbient,
  motionAllowed,
  parseMotion,
  readMotion,
  writeMotion
} from './motion'

function memory(): Storage {
  const m = new Map<string, string>()
  return {
    getItem: (k: string) => m.get(k) ?? null,
    setItem: (k: string, v: string) => void m.set(k, v),
    removeItem: (k: string) => void m.delete(k),
    clear: () => m.clear(),
    key: () => null,
    get length() {
      return m.size
    }
  }
}

describe('motion preference', () => {
  it('reads only the choices it knows', () => {
    expect(parseMotion('full')).toBe('full')
    expect(parseMotion('reduced')).toBe('reduced')
    expect(parseMotion('wild')).toBe('system')
    expect(parseMotion(null)).toBe('system')
  })

  it('remembers a choice and forgets "system"', () => {
    const s = memory()
    writeMotion(s, 'full')
    expect(readMotion(s)).toBe('full')
    writeMotion(s, 'system')
    expect(s.length).toBe(0)
    expect(readMotion(s)).toBe('system')
  })

  it('survives storage that throws', () => {
    const broken = {
      getItem: () => {
        throw new Error('blocked')
      }
    }
    expect(readMotion(broken)).toBe('system')
  })

  it('marks the page so CSS can follow', () => {
    const root = { dataset: {} as DOMStringMap } as HTMLElement
    applyMotion(root, 'reduced')
    expect(root.dataset.motion).toBe('reduced')
    applyMotion(root, 'system')
    expect(root.dataset.motion).toBeUndefined()
  })

  it('lets the choice beat the system', () => {
    expect(motionAllowed('full', true)).toBe(true)
    expect(motionAllowed('reduced', false)).toBe(false)
    expect(motionAllowed('system', true)).toBe(false)
    expect(motionAllowed('system', false)).toBe(true)
  })

  it('rests decorative loops, never progress indicators', () => {
    expect(isAmbient('ev-drift')).toBe(true)
    expect(isAmbient('ev-ember-rise')).toBe(true)
    expect(isAmbient('brand-glow-acde892b')).toBe(true)
    expect(isAmbient('wm-idle-c3e8fcd4')).toBe(true)
    expect(isAmbient('ev-shimmer')).toBe(false)
    expect(isAmbient('ev-dots')).toBe(false)
    expect(isAmbient('paint-turn')).toBe(false)
    expect(isAmbient('obs-spin-1234abcd')).toBe(false)
  })
})
