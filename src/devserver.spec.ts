import { describe, expect, it } from 'vitest'
import configFn from '../vite.config'

describe('credential-injecting dev server boundary', () => {
  it('binds loopback with no wildcard hosts by default', () => {
    const cfg = configFn({ mode: 'development', command: 'serve' })
    expect(cfg.server?.host).toBe('127.0.0.1')
    expect(cfg.server?.allowedHosts).toBeUndefined()
    expect(cfg.preview?.host).toBe('127.0.0.1')
    expect(cfg.preview?.allowedHosts).toBeUndefined()
  })

  it('requires an explicit opt-in for a wider bind', () => {
    process.env.EMBER_VALE_DEV_HOST = '0.0.0.0'
    try {
      const cfg = configFn({ mode: 'development', command: 'serve' })
      expect(cfg.server?.host).toBe('0.0.0.0')
    } finally {
      delete process.env.EMBER_VALE_DEV_HOST
    }
  })
})
