/**
 * Failure-path cleanup for the recovery harness: when the run fails
 * after API startup (via the `--fail-at proxy` self-test hook), the
 * owned scratch API process is stopped and the failure report is
 * retained. Skipped without the local scratch-stack prerequisites
 * (venv python, .env live URL, reachable scratch database, free
 * scratch ports); never touches the live stack.
 */
import { describe, expect, it } from 'vitest'
import { spawn } from 'node:child_process'
import { randomBytes } from 'node:crypto'
import fs from 'node:fs'
import net from 'node:net'
import os from 'node:os'
import path from 'node:path'

const ROOT = process.cwd()
const SCRATCH_PORT = 8102
const SCRATCH_VITE_PORT = 5174

function loadDotEnv() {
  const env = {}
  try {
    const text = fs.readFileSync(path.join(ROOT, '.env'), 'utf8')
    for (const line of text.split('\n')) {
      if (/^\s*#/.test(line)) continue
      const m = line.match(/^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$/)
      if (m) env[m[1]] = m[2]
    }
  } catch {
    /* prerequisites absent: the test skips below */
  }
  return env
}

function portOpen(port) {
  return new Promise((resolve) => {
    const socket = net.connect(port, '127.0.0.1')
    socket.on('connect', () => {
      socket.end()
      resolve(true)
    })
    socket.on('error', () => resolve(false))
  })
}

async function waitForPort(port, wantOpen, timeoutMs) {
  const until = Date.now() + timeoutMs
  for (;;) {
    if ((await portOpen(port)) === wantOpen) return true
    if (Date.now() > until) return false
    await new Promise((r) => setTimeout(r, 500))
  }
}

const dot = loadDotEnv()
const liveUrl = dot.WORLDSIM_DATABASE__URL || ''
const scratchUrl = liveUrl ? liveUrl.replace(/\/embervale$/, '/embervale_recovery') : ''
const scratchTarget = (() => {
  try {
    const u = new URL(scratchUrl.replace(/\+asyncpg$/, ''))
    return { host: u.hostname || 'localhost', port: Number(u.port) || 5432 }
  } catch {
    return null
  }
})()
const venvPython = path.join(ROOT, 'backend', '.venv', 'Scripts', 'python.exe')

// A real end-to-end self-test (it starts a scratch API and vite, ~16 s):
// opt in with EMBER_VALE_HARNESS_SELFTEST=1 when changing the harness.
const skipReason =
  process.env.EMBER_VALE_HARNESS_SELFTEST !== '1'
    ? 'harness self-test (set EMBER_VALE_HARNESS_SELFTEST=1 to run)'
    : !fs.existsSync(venvPython)
      ? 'no backend venv python'
      : !liveUrl
        ? 'no live database URL in .env'
        : !scratchTarget || scratchUrl === liveUrl
          ? 'no distinct scratch database URL'
          : null

async function runFailAtProxy(key) {
  const out = fs.mkdtempSync(path.join(os.tmpdir(), 'recovery-cleanup-'))
  const child = spawn(
    process.execPath,
    [
      path.join(ROOT, 'scripts', 'recovery-browser.mjs'),
      '--base',
      `http://127.0.0.1:${SCRATCH_VITE_PORT}`,
      '--api',
      `http://127.0.0.1:${SCRATCH_PORT}`,
      '--scratch-db-url',
      scratchUrl,
      '--out',
      out,
      '--fail-at',
      'proxy'
    ],
    {
      cwd: ROOT,
      env: {
        ...dot,
        ...process.env,
        RECOVERY_API_KEY: key,
        RECOVERY_SCRATCH_DB_URL: scratchUrl
      }
    }
  )
  let output = ''
  child.stdout.on('data', (d) => {
    output += d
  })
  child.stderr.on('data', (d) => {
    output += d
  })
  const exitCode = await new Promise((resolve) => {
    child.on('close', resolve)
    child.on('error', () => resolve(-1))
  })
  // The owned API demonstrably started (it served the seed and proxy
  // reads before the injected failure), so a free port afterwards
  // proves cleanup — not a stillborn start.
  expect(output).toContain('browser proxy reaches the same scratch instance')
  expect(exitCode, `harness output:\n${output.slice(-2000)}`).not.toBe(0)
  expect(await waitForPort(SCRATCH_PORT, false, 60000)).toBe(true)

  const resultsPath = path.join(out, 'results-recovery-browser.json')
  expect(fs.existsSync(resultsPath)).toBe(true)
  const report = JSON.parse(fs.readFileSync(resultsPath, 'utf8'))
  const failed = (report.results || []).filter((r) => !r.ok)
  expect(failed.length).toBeGreaterThan(0)
  expect(JSON.stringify(failed)).toContain('injected proxy-verification failure')
  fs.rmSync(out, { recursive: true, force: true })
}

describe('recovery harness failure-path cleanup', () => {
  it.skipIf(skipReason !== null)(
    skipReason ?? 'owned API is stopped and the failure report retained',
    { timeout: 300000 },
    async () => {
      if (await portOpen(SCRATCH_PORT)) {
        throw new Error(`scratch port ${SCRATCH_PORT} already occupied; refusing self-test`)
      }
      if (await portOpen(SCRATCH_VITE_PORT)) {
        throw new Error(
          `scratch vite port ${SCRATCH_VITE_PORT} already occupied; refusing self-test`
        )
      }
      if (!(await portOpen(scratchTarget.port))) {
        throw new Error(
          `scratch database ${scratchTarget.host}:${scratchTarget.port} unreachable; refusing self-test`
        )
      }
      // The proxy-verification failure needs the real topology: scratch
      // vite in front of the owned scratch API. The harness starts and
      // stops the API itself; only the static file server is provided
      // here, and it is always stopped afterwards. Vite overwrites the
      // proxied Authorization header with its own key, so it gets the
      // same random scratch key the harness gives its owned API.
      const key = `cleanup-selftest-${randomBytes(8).toString('hex')}`
      const vite = spawn(
        process.execPath,
        ['node_modules/vite/bin/vite.js', '--port', String(SCRATCH_VITE_PORT), '--strictPort'],
        {
          cwd: ROOT,
          stdio: 'ignore',
          env: {
            ...process.env,
            EMBER_VALE_API_TARGET: `http://127.0.0.1:${SCRATCH_PORT}`,
            WORLDSIM_SECURITY__API_KEY: key
          }
        }
      )
      try {
        if (!(await waitForPort(SCRATCH_VITE_PORT, true, 120000))) {
          throw new Error('scratch vite did not start; refusing self-test')
        }
        await runFailAtProxy(key)
      } finally {
        try {
          vite.kill()
        } catch {
          /* already gone */
        }
        await waitForPort(SCRATCH_VITE_PORT, false, 30000)
      }
    }
  )
})
