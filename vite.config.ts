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
  return {
    plugins: [vue()],
    server: {
      host: devHost,
      port: 5173,
      strictPort: true,
      proxy: {
        '/api': {
          target: 'http://localhost:8101',
          changeOrigin: true,
          headers: apiKey ? { Authorization: `Bearer ${apiKey}` } : undefined
        }
      }
    },
    preview: {
      host: devHost,
      port: 4173,
      strictPort: true
    }
  }
})
