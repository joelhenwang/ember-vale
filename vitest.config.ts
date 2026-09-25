/**
 * Vitest config — kept separate from vite.config.ts so the dev server stays
 * untouched. Tests cover the pure game-logic layer only (no DOM needed).
 */
import { defineConfig } from 'vitest/config'

export default defineConfig({
  test: {
    include: ['src/**/*.spec.ts', 'scripts/**/*.spec.mjs'],
    environment: 'node'
  }
})
