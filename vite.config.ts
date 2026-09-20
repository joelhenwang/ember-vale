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
  return {
    plugins: [vue()],
    server: {
      host: '0.0.0.0',
      port: 5173,
      strictPort: true,
      allowedHosts: true,
      proxy: {
        '/api': {
          target: 'http://localhost:8101',
          changeOrigin: true,
          headers: apiKey ? { Authorization: `Bearer ${apiKey}` } : undefined
        }
      }
    },
    preview: {
      host: '0.0.0.0',
      port: 4173,
      strictPort: true,
      allowedHosts: true
    }
  }
})
