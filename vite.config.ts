import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig(({ mode }) => {
  // Local-loopback dev access: the compose API requires a Bearer key for
  // non-health routes. The dev proxy injects it server-side from the root
  // .env (WORLDSIM_SECURITY__API_KEY, never committed, never bundled) so the
  // browser holds no credential. Production same-origin deployments
  // authenticate at the backend directly; see docs/evidence/stage-a-b.md.
  const env = loadEnv(mode, process.cwd(), '')
  const apiKey = env.EMBER_VALE_API_KEY || env.WORLDSIM_SECURITY__API_KEY || ''
  // Loopback by default: the proxy injects an operator credential, so a
  // wildcard bind would grant anyone who can reach the dev server
  // authenticated /api access. LAN development needs an explicit
  // EMBER_VALE_DEV_HOST plus its own access control (a hostname allowlist
  // alone is not authentication).
  const devHost = env.EMBER_VALE_DEV_HOST || process.env.EMBER_VALE_DEV_HOST || '127.0.0.1'
  const proxy = {
    '/api': {
      // Scratch stacks override the backend without touching this file.
      target: env.EMBER_VALE_API_TARGET || 'http://localhost:8101',
      changeOrigin: true,
      headers: apiKey ? { Authorization: `Bearer ${apiKey}` } : undefined
    }
  }
  return {
    plugins: [vue()],
    build: {
      rollupOptions: {
        output: {
          // Vue and the router change far less often than the app: their own
          // chunk stays cached across releases.
          manualChunks: (id: string) =>
            /node_modules[\/](@vue|vue|vue-router)[\/]/.test(id) ? 'vendor' : undefined
        }
      }
    },
    server: {
      host: devHost,
      port: 5173,
      strictPort: true,
      proxy,
      // Only the app's own sources are watched: evidence, the backend and
      // generated art change while the dev server runs (a bench writing a
      // JSON file once crashed the watcher), and watching them is wasted work.
      watch: {
        ignored: [
          '**/docs/**',
          '**/backend/**',
          '**/evidence/**',
          '**/local-models/**',
          '**/launcher/**',
          '**/content/assets/**',
          '**/.claude/**'
        ]
      }
    },
    // `vite preview` serves the production build the same way, so the
    // built app can be measured (scripts/page-bench.mjs) against the API.
    preview: {
      host: devHost,
      port: 4173,
      strictPort: true,
      proxy
    }
  }
})
