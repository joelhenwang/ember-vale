#!/usr/bin/env node
/**
 * Deterministic browser recovery scenario (recovery-storage closure).
 *
 * Drives the real Play room in headless Edge against a scratch stack
 * (frontend on --base, fake-profile API behind it — never the paid
 * live stack), with no model spend:
 *
 *   1. API-seed a Player-as-Wren story (Wren + Ash co-located).
 *   2. Ask Q1 in the room, then kill the scratch API mid-beat so the run
 *      strands open (retry loop: a beat that commits before the kill is
 *      harmless progress; the loop only exits on a stranded run).
 *   3. Restart the API, reload the page: the recovery banner names the
 *      stranded beat.
 *   4. Type Q2 (never sent), click Resume: the stranded beat replays Q1.
 *
 * Asserts: exactly one resume replay at the stranded index carrying Q1
 * verbatim, Q1 admitted exactly once, Q2 never posted and still in the
 * composer, and the Q1 filing retired with Q2 absent from storage.
 *
 * Usage (from repo root; RECOVERY_API_KEY must match the scratch API):
 *   node scripts/recovery-browser.mjs \
 *     --base http://127.0.0.1:5174 --api http://127.0.0.1:8102 \
 *     --scratch-db-url postgresql://user:pass@localhost:5433/embervale_recovery \
 *     --out docs/evidence/recovery
 *
 * The scenario supervises the scratch API itself: it kills the server
 * mid-beat and respawns the same fake-profile command (DB credentials
 * come from the gitignored .env at runtime, never from evidence).
 * Isolation is enforced, not assumed: --scratch-db-url is required and
 * must name a different database than the live stack, --api must be the
 * local scratch instance the harness itself starts (an occupied scratch
 * port is refused), the fake provider is proven before any mutation, the
 * browser proxy is proven to reach that same instance, only verified
 * scratch processes are terminated, and the whole owned-process
 * lifecycle — from `startApi()` through browser cleanup — runs under one
 * outer try/finally. Exit non-zero on any failed step; results are still
 * written.
 */

import { execSync, spawn } from 'node:child_process'
import { createHash } from 'node:crypto'
import fs from 'node:fs'
import path from 'node:path'
import { chromium } from 'playwright-core'

const args = process.argv.slice(2)
const opt = (name, fallback) => {
  const i = args.indexOf(name)
  return i >= 0 && args[i + 1] ? args[i + 1] : fallback
}

const BASE = opt('--base', 'http://127.0.0.1:5174')
const API = opt('--api', 'http://127.0.0.1:8102')
const OUT = opt('--out', 'docs/evidence/recovery')
// Self-test hook only: `--fail-at proxy` throws right after API startup
// (at proxy verification) to prove the owned-process lifecycle still
// stops the API and retains the failure report. Never used for real runs.
const FAIL_AT = opt('--fail-at', '')
const KEY = process.env.RECOVERY_API_KEY || ''
const ROOT = opt('--root', process.cwd())
const PYTHON = path.join(ROOT, 'backend', '.venv', 'Scripts', 'python.exe')
const API_URL = (() => {
  // Restarts always bind loopback:8102, so --api must name that same
  // local instance — never a remote hostname or a different port.
  const parsed = new URL(API)
  const loopback = ['127.0.0.1', 'localhost', '::1'].includes(parsed.hostname)
  if (!loopback || parsed.port !== '8102') {
    throw new Error(`--api must be the local scratch instance (loopback:8102); got ${API}`)
  }
  return parsed
})()
const API_PORT = API_URL.port
const SCRATCH_DB_URL = opt('--scratch-db-url', process.env.RECOVERY_SCRATCH_DB_URL || '')
let killPid = 0
const ownedApiPids = new Set()
const EDGE = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe'
const Q1 = 'What news from the mill, Ash?'
const Q2 = 'What news from the market, Ash?'
const COMMIT = execSync('git rev-parse --short HEAD', { stdio: 'pipe' }).toString().trim()
let DIRTY = false
let DIFF_SHA = null
try {
  DIRTY = execSync('git status --porcelain', { stdio: 'pipe' }).toString().trim().length > 0
  DIFF_SHA = createHash('sha256')
    .update(execSync('git diff HEAD', { stdio: 'pipe', maxBuffer: 64 * 1024 * 1024 }))
    .digest('hex')
} catch {
  /* not a git tree: provenance stays null, the run still records */
}

fs.mkdirSync(OUT, { recursive: true })

const results = []
function record(step, ok, detail = '') {
  results.push({ scenario: 'recovery', step, ok, detail: String(detail).slice(0, 300) })
  console.log(`${ok ? 'PASS' : 'FAIL'} [recovery] ${step}${detail ? ` — ${detail}` : ''}`)
  if (!ok) process.exitCode = 1
}

function writeResults(extra = {}) {
  fs.writeFileSync(
    path.join(OUT, 'results-recovery-browser.json'),
    JSON.stringify(
      {
        slice: 'browser recovery: Q1 interrupted, reload, Q2 typed, Q1 resumed exactly once',
        commit: COMMIT,
        dirty: DIRTY,
        diffSha256: DIFF_SHA,
        at: new Date().toISOString(),
        gateway: 'fake profile on scratch API (no model spend)',
        modelSpend: 'none',
        requestSummaries: advancePosts.map((b) => ({
          absolute_index: b.absolute_index,
          topics: Object.values(b.player_intents || {}).map((i) => i?.topic)
        })),
        responseSummaries: advanceResponses,
        results,
        ...extra
      },
      null,
      2
    ) + '\n'
  )
}

async function apiCall(method, urlPath, body) {
  const res = await fetch(`${API}/api/v1${urlPath}`, {
    method,
    headers: {
      'Content-Type': 'application/json',
      'X-Worldsim-Role': 'watcher',
      ...(KEY ? { Authorization: `Bearer ${KEY}` } : {})
    },
    body: body === undefined ? undefined : JSON.stringify(body)
  })
  if (!res.ok)
    throw new Error(`${method} ${urlPath} -> ${res.status}: ${(await res.text()).slice(0, 200)}`)
  return res.json()
}

async function waitHealthy() {
  const deadline = Date.now() + 90000
  for (;;) {
    try {
      const res = await fetch(`${API}/api/v1/health/ready`)
      if (res.ok) return
    } catch {
      /* still down */
    }
    if (Date.now() > deadline) throw new Error('scratch API did not come back')
    await new Promise((r) => setTimeout(r, 1000))
  }
}

function loadDotEnv() {
  // Runtime-only secrets (DB password lives here): parsed, never printed
  // or written to evidence.
  const env = {}
  const text = fs.readFileSync(path.join(ROOT, '.env'), 'utf8')
  for (const line of text.split('\n')) {
    if (/^\s*#/.test(line)) continue
    const m = line.match(/^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$/)
    if (m) env[m[1]] = m[2]
  }
  return env
}

function startApi() {
  // Supervised directly: start (or restart) the fake-profile server on
  // the validated scratch database. Migrations persist in the scratch
  // DB; no alembic rerun. Every instance is owned and stopped in `finally`.
  const dot = loadDotEnv()
  const scratchUrl = requireScratchDbUrl(dot.WORLDSIM_DATABASE__URL)
  const child = spawn(
    PYTHON,
    ['-m', 'worldsim.interfaces.cli', 'serve', '--host', '127.0.0.1', '--port', API_PORT],
    {
      cwd: ROOT,
      detached: true,
      stdio: 'ignore',
      env: {
        ...process.env,
        WORLDSIM_DATABASE__URL: scratchUrl,
        WORLDSIM_PROVIDER__ACTIVE_PROFILE: 'fake',
        WORLDSIM_SECURITY__API_KEY: KEY,
        WORLDSIM_APP__HOST: '127.0.0.1'
      }
    }
  )
  child.unref()
  if (child.pid) ownedApiPids.add(child.pid)
  return child.pid
}

async function requireFakeProfile() {
  // No mutations until the scratch API proves it is deterministic.
  const res = await fetch(`${API}/api/v1/health/ready`)
  if (!res.ok) throw new Error(`scratch API not ready: ${res.status}`)
  const body = await res.json()
  const profile = (body.checks || []).find((c) => c.name === 'model_profile')
  if (!profile || !/active:fake/.test(profile.detail || '')) {
    throw new Error(
      `refusing mutations: scratch API is not fake-profile (${profile?.detail || 'unknown'})`
    )
  }
}

function requireScratchDbUrl(liveUrl) {
  // Explicit, validated isolation: the scratch URL must be given, must
  // parse as postgres, and must name a different database than the live
  // stack. A silent replace fallback could restart onto the live DB.
  if (!SCRATCH_DB_URL) throw new Error('missing --scratch-db-url <postgresql url>')
  let scratch
  try {
    scratch = new URL(SCRATCH_DB_URL)
  } catch {
    throw new Error('unparseable --scratch-db-url')
  }
  if (!/^postgres/.test(scratch.protocol) || !scratch.pathname || scratch.pathname === '/') {
    throw new Error('scratch URL must be a postgresql URL with a database name')
  }
  if (!liveUrl) throw new Error('live database URL unknown; refusing to guess isolation')
  let live
  try {
    live = new URL(liveUrl.replace(/\+asyncpg$/, ''))
  } catch {
    throw new Error('unparseable live database URL; refusing to guess isolation')
  }
  if (scratch.pathname === live.pathname) {
    throw new Error('scratch database matches the live database; refusing to start')
  }
  return SCRATCH_DB_URL
}

function processCommandLine(pid) {
  try {
    return execSync(
      `powershell -Command "(Get-CimInstance Win32_Process -Filter 'ProcessId=${pid}' | Select-Object -ExpandProperty CommandLine)"`,
      { stdio: 'pipe' }
    ).toString()
  } catch {
    return ''
  }
}

function verifyScratchApi(pid) {
  // Kill only a verified scratch server: the worldsim serve command on
  // the scratch port. Anything else is left alone.
  if (!pid) return false
  const cmd = processCommandLine(pid)
  return cmd.includes('worldsim.interfaces.cli') && cmd.includes('serve') && cmd.includes(API_PORT)
}

async function seedPlayerStory() {
  const presets = await apiCall('GET', '/library/presets?kind=world')
  const emberVale = presets.find((p) => p.name === 'Ember Vale')
  const chars = await apiCall('GET', '/library/presets?kind=character')
  const wren = chars.find((p) => p.name === 'Wren')
  const ash = chars.find((p) => p.name === 'Ash')
  const draft = await apiCall('POST', '/story-drafts', {
    payload: {
      world: { preset_id: emberVale.id, preset_revision: emberVale.current_revision },
      cast: [
        {
          instance_key: 'wren',
          preset_id: wren.id,
          preset_revision: wren.current_revision,
          name: 'Wren',
          location_key: 'hearth'
        },
        {
          instance_key: 'ash',
          preset_id: ash.id,
          preset_revision: ash.current_revision,
          name: 'Ash',
          location_key: 'hearth'
        }
      ],
      mode: { role: 'player', controlled_cast_key: 'wren' },
      story: { title: `Recovery scenario ${Date.now().toString(36)}` },
      ai: { art_source: 'curated' }
    },
    current_step: 'review'
  })
  const res = await fetch(`${API}/api/v1/stories`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Worldsim-Role': 'watcher',
      ...(KEY ? { Authorization: `Bearer ${KEY}` } : {}),
      'Idempotency-Key': `recovery-scenario-${Date.now()}`
    },
    body: JSON.stringify({ draft_id: draft.id, expected_draft_version: 1 })
  })
  if (!res.ok) throw new Error(`story create -> ${res.status}`)
  return (await res.json()).world_id
}

function findApiPid() {
  try {
    const out = execSync(
      `powershell -Command "(Get-NetTCPConnection -LocalPort 8102 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1).OwningProcess"`,
      { stdio: 'pipe' }
    )
      .toString()
      .trim()
    return Number(out) || 0
  } catch {
    return 0
  }
}

function killApi() {
  // Forceful termination: the in-flight beat task dies mid-execution and
  // its run row stays open. A graceful stop could let the beat commit.
  // Only a verified scratch server is ever terminated.
  if (!verifyScratchApi(killPid)) {
    throw new Error(`refusing to kill unverified pid ${killPid}`)
  }
  ownedApiPids.delete(killPid)
  process.kill(killPid)
}

function stopOwnedApi() {
  for (const pid of [...ownedApiPids]) {
    ownedApiPids.delete(pid)
    try {
      if (verifyScratchApi(pid)) process.kill(pid)
    } catch {
      /* already gone */
    }
  }
}

const advancePosts = []
const advanceResponses = []
function watchAdvances(page) {
  page.on('request', (req) => {
    if (req.url().endsWith('/api/v1/stage1/advance') && req.method() === 'POST') {
      advancePosts.push(JSON.parse(req.postData() || '{}'))
    }
  })
  page.on('response', (res) => {
    const req = res.request()
    if (req.url().endsWith('/api/v1/stage1/advance') && req.method() === 'POST') {
      res
        .json()
        .then((body) =>
          advanceResponses.push({
            status: res.status(),
            duplicate: body.duplicate,
            absolute_index: body.absolute_index
          })
        )
        .catch(() => advanceResponses.push({ status: res.status(), duplicate: '<unparseable>' }))
    }
  })
}

async function requireProxySameInstance(worldId) {
  // The browser reaches the API through the vite proxy: prove the proxy
  // lands on this same scratch instance before gameplay mutations. A
  // proxy pointed elsewhere would not know the seeded world.
  const res = await fetch(`${BASE}/api/v1/stories/${worldId}`, {
    headers: { 'X-Worldsim-Role': 'watcher', ...(KEY ? { Authorization: `Bearer ${KEY}` } : {}) }
  })
  if (!res.ok) throw new Error(`proxy story read -> ${res.status}: not our scratch instance`)
  const body = await res.json()
  if (!JSON.stringify(body).includes(worldId)) {
    throw new Error('proxy story mismatch: not our scratch instance')
  }
}

async function readRunIntents(runId) {
  // Structured committed intents for one run, scene by scene.
  const scenes = await apiCall('GET', `/stage1/scenes?phase_run_id=${runId}&limit=200`)
  const out = []
  for (const scene of scenes) {
    const detail = await apiCall('GET', `/stage1/scenes/${scene.id}`)
    for (const intent of detail.intents || []) out.push({ scene_id: scene.id, ...intent })
  }
  return out
}

async function runScenario() {
  // Everything the owned API serves runs here, under main()'s outer
  // try/finally: readiness, fake-profile proof, seeding, proxy proof,
  // browser startup, and browser cleanup. Any throw below still stops
  // the owned process. No pre-existing process is ever adopted or killed.
  await waitHealthy()
  await requireFakeProfile()
  const worldId = await seedPlayerStory()
  record('player story seeded on scratch API', true, `world ${worldId.slice(0, 8)}`)
  await requireProxySameInstance(worldId)
  record('browser proxy reaches the same scratch instance', true, `world ${worldId.slice(0, 8)}`)
  if (FAIL_AT === 'proxy') {
    throw new Error('injected proxy-verification failure (--fail-at=proxy)')
  }

  let browser
  try {
    browser = await chromium.launch({ executablePath: EDGE, headless: true })
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
    const page = await ctx.newPage()
    watchAdvances(page)
    await page.goto(`${BASE}/stories/${worldId}/play`, { waitUntil: 'domcontentloaded' })
    await page.locator('.play__badge').waitFor({ timeout: 30000 })
    const badge = await page.locator('.play__badge').innerText()
    record('room grants Player as Wren', badge.includes('Player'), badge.trim())

    // Strand a beat: ask, then kill the API mid-flight. A beat that
    // commits first is retried with a fresh topic; only a stranded run
    // exits the loop.
    let strandedIndex = 0
    let runId = null
    let q1 = Q1
    let killAt = 0
    for (let attempt = 1; attempt <= 5; attempt += 1) {
      q1 = attempt === 1 ? Q1 : `${Q1} (try ${attempt})`
      // Read the clock before sending: the target beat is next index.
      const clock = await apiCall('GET', `/simulation/status?world_id=${worldId}`)
      const targetIndex = clock.absolute_index + 1
      const speak = page.getByRole('region', { name: 'Speak as your character' })
      await page.getByLabel('Say').fill(q1)
      const askBtn = speak.getByRole('button', { name: 'Ask with the next beat' })
      await askBtn.waitFor({ timeout: 30000 })
      // The room enables Ask only once the grant, targets, and a clear
      // recovery state resolve — after the fill, not with it.
      try {
        await page.waitForFunction(
          (region) => {
            const el = [...region.querySelectorAll('button')].find((b) =>
              /Ask with the next beat/.test(b.textContent || '')
            )
            return !!el && !el.disabled
          },
          await speak.elementHandle(),
          { timeout: 30000 }
        )
      } catch (err) {
        const dump = await page.evaluate(() => {
          const selects = [...document.querySelectorAll('select')].map((s) => ({
            label: (s.closest('label')?.textContent || '').trim().slice(0, 20),
            value: s.value,
            options: s.options.length
          }))
          const btn = [...document.querySelectorAll('button')].find((b) =>
            /Ask with the next beat/.test(b.textContent || '')
          )
          const notices = [...document.querySelectorAll('.play__notice')].map((n) =>
            (n.textContent || '').trim().slice(0, 200)
          )
          const say = document.querySelector('input[placeholder*="your own words"]')
          return {
            selects,
            btn: btn ? { disabled: btn.disabled, title: btn.title || null } : null,
            notices,
            sayValue: say ? say.value : null
          }
        })
        record('ask readiness diagnostics', false, JSON.stringify(dump).slice(0, 300))
        console.log('FULL DUMP', JSON.stringify(dump))
        throw err
      }
      await askBtn.click()
      await speak.getByRole('button', { name: 'Committing beat…' }).waitFor({ timeout: 15000 })
      // Kill on admission, not on a fixed delay: poll for the open run
      // and terminate the instant it appears, while the beat is still
      // executing. A beat that commits first is retried next attempt.
      const pollUntil = Date.now() + 15000
      for (;;) {
        const seen = await apiCall('GET', `/simulation/status?world_id=${worldId}`)
        if (seen.open_run_index === targetIndex) break
        if (Date.now() > pollUntil) break
        await new Promise((r) => setTimeout(r, 25))
      }
      killAt = Date.now()
      killApi()
      killPid = startApi()
      await waitHealthy()
      await page.reload({ waitUntil: 'domcontentloaded' })
      await page.locator('.play__badge').waitFor({ timeout: 30000 })
      // The recovery banner is not the first notice on the page (the
      // provider banner sorts first): find it by its stranded-beat text.
      const stranded = page.getByText(/hasn't finished/, { exact: false })
      let banner = ''
      try {
        await stranded.first().waitFor({ timeout: 15000 })
        banner = await stranded.first().innerText()
      } catch {
        banner = ''
      }
      const m = banner.match(/Beat (\d+) hasn't finished/)
      if (m) {
        strandedIndex = Number(m[1])
        // The open run id anchors the structured intent proof later.
        const status = await apiCall('GET', `/simulation/status?world_id=${worldId}`)
        if (status.open_run_index !== strandedIndex || !status.open_run_id) {
          throw new Error('status disagrees with the stranded banner')
        }
        runId = status.open_run_id
        record('Q1 interrupted into a stranded open beat', true, `beat ${strandedIndex}`)
        break
      }
      if (attempt === 5)
        record('Q1 interrupted into a stranded open beat', false, 'no open run after 5 kills')
    }
    if (!strandedIndex) throw new Error('could not strand a beat')
    await page.screenshot({ path: path.join(OUT, 'recovery-banner.png') })

    // Type Q2 without sending, then resume: the stranded beat replays Q1.
    await page.getByLabel('Say').fill(Q2)
    await page.screenshot({ path: path.join(OUT, 'recovery-composer-q2.png') })
    // The kill orphaned the execution slot lease (300s, DB-backed): an
    // immediate resume is correctly refused with 409 and files nothing.
    // Wait the lease out exactly as a real crash recovery would, then
    // resume into a free slot.
    await page.getByRole('button', { name: `Resume beat ${strandedIndex}` }).click()
    await page
      .getByText(/already committing/, { exact: false })
      .first()
      .waitFor({ timeout: 60000 })
    record(
      'resume refused while the crashed lease is held',
      true,
      '409 committing notice, no new beat'
    )
    const resumeAt = killAt + 320000
    for (;;) {
      const remaining = resumeAt - Date.now()
      if (remaining <= 0) break
      await new Promise((r) => setTimeout(r, Math.min(remaining, 15000)))
    }
    await page.getByRole('button', { name: `Resume beat ${strandedIndex}` }).click()
    await page.getByRole('button', { name: /Commit beat/ }).waitFor({ timeout: 120000 })
    await page.screenshot({ path: path.join(OUT, 'recovery-resumed.png') })

    // Every send targets the stranded index with Q1 verbatim: the
    // initial filing, the replay refused on the orphaned lease, and the
    // real replay after expiry. (Whether the killed send surfaces as an
    // abort or a proxy 500 depends on kill timing, not the product.)
    const q1Posts = advancePosts.filter((b) => b.absolute_index === strandedIndex)
    record(
      'every send at the stranded index carries Q1 verbatim',
      q1Posts.length >= 2 &&
        q1Posts.every((b) => Object.values(b.player_intents || {})[0]?.topic === q1),
      `${q1Posts.length} advance posts at index ${strandedIndex}`
    )
    const q2Posted = advancePosts.some((b) =>
      Object.values(b.player_intents || {}).some((i) => i?.topic === Q2)
    )
    record('Q2 never posted', !q2Posted, `${advancePosts.length} advance posts total`)

    const feed = await page
      .locator('.play__feed')
      .innerText()
      .catch(() => '')
    // The deterministic stand-in narration does not echo player topics,
    // so admission is proven by the fresh commit below, not feed text.
    record('Q2 absent from the feed', !feed.includes(Q2), '')
    const composer = await page.getByLabel('Say').inputValue()
    record('Q2 retained in the composer', composer === Q2, composer.slice(0, 80))

    // Server-side exactly-once: the clock advanced by exactly the resumed
    // beat (no duplicate new beat), and the timeline holds committed
    // entries at the stranded index and none beyond it.
    const beatLabel = await page
      .locator('.play__meta')
      .innerText()
      .catch(() => '')
    const clockOk = new RegExp(`Beat ${strandedIndex}(?!\\d)`).test(beatLabel)
    record('room clock shows exactly the resumed beat', clockOk, beatLabel.slice(0, 120))
    const timeline = await apiCall('GET', `/stage2/timeline?world_id=${worldId}&after=0&limit=50`)
    const atIndex = (timeline.entries || []).filter((e) => e.absolute_index === strandedIndex)
    const beyond = (timeline.entries || []).filter((e) => e.absolute_index > strandedIndex)
    record(
      'timeline holds committed entries at the stranded index and none beyond',
      atIndex.length > 0 && beyond.length === 0,
      `at=${atIndex.length} beyond=${beyond.length}`
    )
    // Read-only committed-intent proof from structured scene records
    // (not presentation text): exactly one `communicate` intent with
    // Wren's runtime id, Ash's target id, and the exact Q1 topic; Q2 in
    // none of the run's intents.
    const characters = await apiCall('GET', `/stage1/characters?world_id=${worldId}`)
    const wrenId = characters.find((c) => c.name === 'Wren')?.id
    const ashId = characters.find((c) => c.name === 'Ash')?.id
    if (!wrenId || !ashId) throw new Error('seeded cast missing from character roster')
    const runIntents = await readRunIntents(runId)
    const q1Committed = runIntents.filter(
      (i) =>
        i.family === 'communicate' &&
        i.author_character_id === wrenId &&
        i.detail?.target_character_id === ashId &&
        i.detail?.topic === q1
    )
    const q2Committed = runIntents.filter((i) => i.detail?.topic === Q2)
    const committedSources = q1Committed.map((i) => ({
      intent_id: i.id,
      scene_id: i.scene_id,
      author_character_id: i.author_character_id,
      family: i.family,
      topic: i.detail?.topic,
      target_character_id: i.detail?.target_character_id
    }))
    record(
      'committed intent is Q1 exactly once with actor and target IDs; Q2 zero times',
      q1Committed.length === 1 && q2Committed.length === 0,
      `q1=${q1Committed.length} q2=${q2Committed.length} intents=${runIntents.length}`
    )
    const busyCount = advanceResponses.filter((r) => r.status === 409).length
    record('refused resume is HTTP 409', busyCount === 1, `${busyCount} busy responses`)

    const stored = await page.evaluate((wid) => {
      const out = []
      for (let i = 0; i < localStorage.length; i += 1) {
        const key = localStorage.key(i)
        if (key && key.includes(wid)) out.push({ key, value: localStorage.getItem(key) })
      }
      return out
    }, worldId)
    const topics = stored
      .map((s) => {
        try {
          const parsed = JSON.parse(s.value)
          const items = Array.isArray(parsed) ? parsed : [parsed]
          return items.map((r) => Object.values(r.intents || {})[0]?.topic)
        } catch {
          return ['<unparseable>']
        }
      })
      .flat()
    console.log('STORED', JSON.stringify(stored).slice(0, 1500))
    console.log('RESPONSES', JSON.stringify(advanceResponses))
    const resumeResponses = advanceResponses.filter((r) => r.status === 200)
    record(
      'resume committed fresh, never as a duplicate',
      resumeResponses.length === 1 && resumeResponses[0].duplicate === false,
      JSON.stringify(resumeResponses).slice(0, 200)
    )
    record(
      'Q1 filing retired and Q2 never stored',
      !topics.includes(q1) && !topics.includes(Q2),
      topics.join(' | ').slice(0, 200) || 'no filings'
    )

    await ctx.close()
    writeResults({ committedIntents: committedSources })
  } finally {
    // Browser cleanup must never skip API cleanup: stop the browser if
    // it started, then the owned API — with main()'s outer finally as
    // the second net if browser cleanup itself throws.
    try {
      if (browser) await browser.close()
    } finally {
      stopOwnedApi()
    }
  }
}

async function main() {
  // Own the scratch API for the whole run: validate isolation first,
  // refuse an occupied scratch port, then start the single owned
  // instance. Everything after — including browser startup and browser
  // cleanup — runs under one outer try/finally, so the owned process is
  // always stopped, even on early failure.
  requireScratchDbUrl(loadDotEnv().WORLDSIM_DATABASE__URL)
  if (findApiPid()) throw new Error('refusing: scratch port 8102 already occupied')
  killPid = startApi()
  try {
    await runScenario()
  } finally {
    stopOwnedApi()
  }
}

main().catch((err) => {
  record('scenario completed', false, err?.message || String(err))
  writeResults()
})
