#!/usr/bin/env node
/**
 * Browser walkthrough for the playable milestone (fourth-push review §7).
 *
 * Drives the real UI in headless Edge against the dev server (proxy injects
 * the operator key, so no credentials are needed here):
 *
 *   observer  — Quick Start review -> Begin -> travel -> beat -> reload/continue -> Home
 *   player    — API-seeded Player-as-Wren story: grant badge, locked actor, movement
 *   failedsave— API stopped mid-wizard: failed state, retry, saved again
 *   narrow    — review + room screenshots at a narrow viewport
 *
 * Usage:
 *   node scripts/walkthrough.mjs [--base http://127.0.0.1:5173] [--out docs/evidence/walkthrough]
 *
 * Requires the compose stack and `npm run dev` up. Writes results.json plus
 * screenshots into --out (committed as milestone evidence). Exit non-zero on
 * any failed step; results.json is still written.
 */

import { execSync } from 'node:child_process'
import { createHash } from 'node:crypto'
import fs from 'node:fs'
import path from 'node:path'
import { chromium } from 'playwright-core'

const args = process.argv.slice(2)
const opt = (name, fallback) => {
  const i = args.indexOf(name)
  return i >= 0 && args[i + 1] ? args[i + 1] : fallback
}

const BASE = opt('--base', 'http://127.0.0.1:5173')
const OUT = opt('--out', 'docs/evidence/walkthrough')
const EDGE = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe'
const API = `${BASE}/api/v1`
// Subset runner for iteration: --only adoptretry,publishretry,...
const ONLY = new Set(
  opt('--only', '')
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean)
)
const run = (name) => ONLY.size === 0 || ONLY.has(name)
const COMMIT = execSync('git rev-parse --short HEAD', { stdio: 'pipe' }).toString().trim()
// Tested-tree identity, captured at run start: a record run should be a
// clean committed tree (dirty === false, only === []). Anything else is
// partial or baseline-plus-modifications evidence — see PROVENANCE.md.
let DIRTY = false
let DIFF_SHA = null
let UNTRACKED = []
try {
  const porcelain = execSync('git status --porcelain', { stdio: 'pipe' }).toString().trim()
  DIRTY = porcelain.length > 0
  UNTRACKED = porcelain
    .split('\n')
    .filter((line) => line.startsWith('??'))
    .map((line) => line.slice(3).trim())
    .filter(Boolean)
  DIFF_SHA = createHash('sha256')
    .update(execSync('git diff HEAD', { stdio: 'pipe', maxBuffer: 64 * 1024 * 1024 }))
    .digest('hex')
} catch {
  /* not a git tree: provenance stays null, the run still records */
}

fs.mkdirSync(OUT, { recursive: true })

const results = []
function record(scenario, step, ok, detail = '') {
  results.push({ scenario, step, ok, detail })
  console.log(`${ok ? 'PASS' : 'FAIL'} [${scenario}] ${step}${detail ? ` — ${detail}` : ''}`)
  if (!ok) process.exitCode = 1
}

function docker(cmd) {
  execSync(`docker ${cmd}`, { stdio: 'pipe', timeout: 120000 })
}

async function waitApiReady() {
  const deadline = Date.now() + 120000
  for (;;) {
    try {
      const res = await fetch(`${API.replace(':5173', ':8101')}/health/ready`)
      if (res.ok) return
    } catch {
      /* still down */
    }
    if (Date.now() > deadline) throw new Error('API did not come back')
    await new Promise((r) => setTimeout(r, 2000))
  }
}

async function apiCall(method, urlPath, body, extraHeaders = {}) {
  const res = await fetch(`${API}${urlPath}`, {
    method,
    headers: { 'Content-Type': 'application/json', 'X-Worldsim-Role': 'watcher', ...extraHeaders },
    body: body === undefined ? undefined : JSON.stringify(body)
  })
  if (!res.ok)
    throw new Error(`${method} ${urlPath} -> ${res.status}: ${(await res.text()).slice(0, 200)}`)
  return res.json()
}

/** Throwaway world preset for the studio view flows (archived afterwards). */
async function createStudioWorld(tag) {
  const stamp = Date.now().toString(36)
  const name = `Walkthrough ${tag} ${stamp}`
  return apiCall(
    'POST',
    '/library/presets',
    {
      kind: 'world',
      name,
      payload: {
        kind: 'world',
        name,
        description: `${name} basin.`,
        lore: `${name} lore.`,
        locations: [
          { key: 'hearth', name: 'Hearth', description: 'A warm room.' },
          { key: 'market', name: 'Market', description: 'Stalls and bells.' }
        ],
        travel: [
          ['hearth', 'market'],
          ['market', 'hearth']
        ],
        starting_location_key: 'hearth'
      }
    },
    { 'Idempotency-Key': `walkthrough-studio-${stamp}-${tag}` }
  )
}

async function archiveStudioWorld(id) {
  const detail = await apiCall('GET', `/library/presets/${id}`)
  await apiCall('POST', `/library/presets/${id}/archive`, { expected_version: detail.version })
}

/** Studio fields pair a bare span label with their control: scope by label. */
const fieldControl = (page, label, tag) =>
  page.locator(`div:has(> .ev-field-label:text-is("${label}")) ${tag}`)

const browser = await chromium.launch({ executablePath: EDGE, headless: true })

try {
  if (run('observer')) // ---- Observer journey (desktop) -------------------------------------
  {
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
    const page = await ctx.newPage()
    const S = 'observer'
    await page.goto(`${BASE}/new-story?quickstart=1`, { waitUntil: 'networkidle' })
    await page.getByRole('button', { name: 'Begin the story' }).waitFor({ timeout: 30000 })
    record(S, 'quickstart review renders with Begin enabled', true)
    const staleIssues = await page.locator('.nsv__issues').count()
    record(
      S,
      'no stale server validation on a filled review',
      staleIssues === 0,
      `issues blocks: ${staleIssues}`
    )

    await page.getByRole('button', { name: 'Begin the story' }).click()
    await page.waitForURL(/\/stories\/.+\/play/, { timeout: 30000 })
    const storyId = page.url().match(/\/stories\/(.+)\/play/)[1]
    record(S, 'begin navigates to the room', true, storyId)
    await page.getByText('Observer', { exact: false }).first().waitFor({ timeout: 15000 })
    const badge = await page.locator('.play__badge').innerText()
    record(S, 'observer badge is read-only grant state', badge.includes('Observer'), badge)
    // The room fetches backend readiness asynchronously on mount; wait for
    // the banner instead of asserting on first paint (cold stacks flake).
    await page.getByText('Development model active', { exact: false }).waitFor({ timeout: 15000 })
    const profile = await page.locator('.play').innerText()
    record(
      S,
      'room shows the development-model status',
      profile.includes('Development model active'),
      ''
    )

    await page.getByLabel('Who').selectOption(
      await page.getByLabel('Who').evaluate((el) => {
        const at = Array.from(el.options).findIndex((o) => o.text.includes('Wren'))
        if (at < 0) throw new Error('no Wren option')
        return { index: at }
      })
    )
    await page.getByRole('button', { name: 'Start journey' }).click()
    await page.getByText('Journey begun', { exact: false }).waitFor({ timeout: 15000 })
    record(S, 'travel starts for Wren', true)

    await page.getByRole('button', { name: /Commit beat/ }).click()
    await page.getByRole('button', { name: /Commit beat 2/ }).waitFor({ timeout: 60000 })
    record(S, 'first beat commits', true)
    const cast = await page.locator('.play__cast').innerText()
    record(
      S,
      'Wren reaches Market after the beat',
      /Wren[\s\S]*Market/.test(cast),
      cast.slice(0, 160)
    )
    const feedCount = await page.locator('.play__feed li').count()
    record(S, 'feed shows committed events', feedCount > 0, `${feedCount} entries`)

    await page.screenshot({ path: path.join(OUT, 'room-observer.png') })
    await page.reload({ waitUntil: 'networkidle' })
    await page.getByRole('button', { name: /Commit beat 2/ }).waitFor({ timeout: 30000 })
    const stillThere = await page.locator('.play__feed li').count()
    record(
      S,
      'reload continues the same story',
      stillThere > 0 && page.url().includes(storyId),
      `${stillThere} entries`
    )

    await page.goto(`${BASE}/`, { waitUntil: 'networkidle' })
    const home = await page.locator('main').innerText()
    record(S, 'home features the story after play', home.includes('A Morning in Ember Vale'), '')
    await ctx.close()
  }

  if (run('player')) // ---- Player journey (Wren controlled, Ash sorts first) ----------------
  {
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
            location_key: 'market'
          }
        ],
        mode: { role: 'player', controlled_cast_key: 'wren' },
        story: { title: `Walkthrough player ${Date.now().toString(36)}` },
        ai: { art_source: 'curated' }
      },
      current_step: 'review'
    })
    // Creation needs an idempotency key: raw fetch for this one call.
    const keyRes = await fetch(`${API}/stories`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Worldsim-Role': 'watcher',
        'Idempotency-Key': `walkthrough-player-${Date.now()}`
      },
      body: JSON.stringify({ draft_id: draft.id, expected_draft_version: 1 })
    })
    if (!keyRes.ok) throw new Error(`player create -> ${keyRes.status}`)
    const playerStory = (await keyRes.json()).world_id

    const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
    const page = await ctx.newPage()
    const S = 'player'
    await page.goto(`${BASE}/stories/${playerStory}/play`, { waitUntil: 'networkidle' })
    await page.locator('.play__badge').waitFor({ timeout: 30000 })
    const badge = await page.locator('.play__badge').innerText()
    record(S, 'player badge follows the persisted grant', badge.includes('Player'), badge)
    const meta = await page.locator('.play__meta').innerText()
    record(
      S,
      'room names Wren as the controlled actor',
      meta.includes('Playing as Wren'),
      meta.slice(0, 160)
    )
    const whoDisabled = await page.getByLabel('Who').isDisabled()
    const whoText = await page.getByLabel('Who').innerText()
    record(
      S,
      'travel actor locked to the controlled id (Ash first ignored)',
      whoDisabled && /Wren/.test(whoText),
      whoText.slice(0, 120)
    )

    await page.getByRole('button', { name: 'Start journey' }).click()
    await page.getByText('Journey begun', { exact: false }).waitFor({ timeout: 15000 })
    await page.getByRole('button', { name: /Commit beat/ }).click()
    await page.getByRole('button', { name: /Commit beat 2/ }).waitFor({ timeout: 60000 })
    const cast = await page.locator('.play__cast').innerText()
    record(
      S,
      'player movement commits (Wren to Market)',
      /Wren[\s\S]*Market/.test(cast),
      cast.slice(0, 160)
    )
    await page.screenshot({ path: path.join(OUT, 'room-player.png') })
    await ctx.close()
  }

  if (
    run('wizardplayer')
  ) // ---- Wizard Player creation (explicit Wren selection) -----------------
  {
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
    const page = await ctx.newPage()
    const S = 'wizardplayer'
    const title = `Walkthrough wizard ${Date.now().toString(36)}`
    await page.goto(`${BASE}/new-story`, { waitUntil: 'networkidle' })
    await page
      .getByRole('button', { name: /Ember Vale/ })
      .first()
      .waitFor({ timeout: 30000 })
    await page
      .getByRole('button', { name: /Ember Vale/ })
      .first()
      .click()
    await page.getByRole('button', { name: 'Continue', exact: true }).click()
    await page.getByRole('button', { name: /Wren/ }).click()
    await page.getByRole('button', { name: /Ash/ }).click()
    await page.getByRole('button', { name: 'Continue', exact: true }).click()
    await page.getByRole('button', { name: 'Player' }).click()
    await page.getByLabel('Play as').selectOption(
      await page.getByLabel('Play as').evaluate((el) => {
        const at = Array.from(el.options).findIndex((o) => o.text.includes('Wren'))
        if (at < 0) throw new Error('no Wren option')
        return { index: at }
      })
    )
    const playAs = await page.getByLabel('Play as').innerText()
    await page.getByRole('button', { name: 'Continue', exact: true }).click()
    await page.getByLabel('Title').fill(title)
    await page.getByRole('button', { name: 'Continue', exact: true }).click()
    await page.getByRole('button', { name: 'Continue', exact: true }).click()
    await page.getByText(`Player as Wren`, { exact: false }).waitFor({ timeout: 15000 })
    record(
      S,
      'review shows the explicit Wren selection',
      playAs.includes('Wren'),
      playAs.slice(0, 80)
    )
    await page.getByRole('button', { name: 'Begin the story' }).click()
    await page.waitForURL(/\/stories\/.+\/play/, { timeout: 30000 })
    await page.locator('.play__badge').waitFor({ timeout: 30000 })
    const badge = await page.locator('.play__badge').innerText()
    record(S, 'wizard-created story grants Player', badge.includes('Player'), badge)
    await page.reload({ waitUntil: 'networkidle' })
    await page.locator('.play__badge').waitFor({ timeout: 30000 })
    const badgeAfter = await page.locator('.play__badge').innerText()
    const metaAfter = await page.locator('.play__meta').innerText()
    record(
      S,
      'grant and locked actor survive reload',
      badgeAfter.includes('Player') && metaAfter.includes('Playing as Wren'),
      `${badgeAfter} / ${metaAfter.slice(0, 80)}`
    )
    await page.screenshot({ path: path.join(OUT, 'room-wizard-player.png') })
    await ctx.close()
  }

  if (run('director')) // ---- Director seat and intervention queue ---------------------------
  {
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
    const page = await ctx.newPage()
    const S = 'director'
    await page.goto(`${BASE}/new-story?quickstart=1`, { waitUntil: 'networkidle' })
    await page.getByRole('button', { name: 'Begin the story' }).waitFor({ timeout: 30000 })
    await page.getByRole('button', { name: 'Begin the story' }).click()
    await page.waitForURL(/\/stories\/.+\/play/, { timeout: 30000 })
    await page.locator('.play__badge').waitFor({ timeout: 30000 })
    // Observer story: no bound player seat, so the operator seats are offered.
    await page.getByRole('button', { name: 'Take the Director seat' }).click()
    await page.getByText('Direct the story', { exact: false }).waitFor({ timeout: 30000 })
    const badge = await page.locator('.play__badge').innerText()
    record(S, 'director badge follows the seat grant', badge.includes('Director'), badge)
    // The dev gateway cannot map names to a typed plan: filing surfaces
    // needs_clarification deterministically instead of fake success.
    await page.getByLabel('Direction').fill('Send Wren to the Market')
    await page.getByRole('button', { name: /File direction/ }).click()
    await page
      .getByText('needs clarification', { exact: false })
      .first()
      .waitFor({ timeout: 30000 })
    const queue = await page.locator('.play__queue').innerText()
    record(
      S,
      'unmappable direction files as clarification, not silent success',
      /needs clarification/.test(queue),
      queue.slice(0, 160)
    )
    // Edit reinterprets with a bumped version; cancel preserves history.
    await page.locator('.play__queue button').first().click()
    await page.getByLabel('Revised text').fill('A peddler arrives at the Hearth.')
    await page.getByRole('button', { name: 'Resubmit text' }).click()
    await page.getByText('v1', { exact: false }).waitFor({ timeout: 30000 })
    const revised = await page.locator('.play__queue').innerText()
    record(S, 'edit reinterprets with a bumped version', /v1/.test(revised), revised.slice(0, 120))
    await page.getByRole('button', { name: 'Cancel direction' }).click()
    await page.getByText('cancelled', { exact: false }).first().waitFor({ timeout: 30000 })
    record(S, 'cancel preserves the direction as cancelled', true)
    await page.getByRole('button', { name: 'Return to Observer seat' }).click()
    await page.getByRole('button', { name: 'Take the Director seat' }).waitFor({ timeout: 30000 })
    const badgeAfter = await page.locator('.play__badge').innerText()
    record(S, 'returning restores the observer seat', badgeAfter.includes('Observer'), badgeAfter)
    await ctx.close()
  }

  if (run('dirtynav')) // ---- Dirty in-app navigation and recovery ------------------------------
  {
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
    const page = await ctx.newPage()
    const S = 'dirtynav'
    await page.goto(`${BASE}/new-story`, { waitUntil: 'networkidle' })
    await page
      .getByRole('button', { name: /Ember Vale/ })
      .first()
      .waitFor({ timeout: 30000 })
    await page
      .getByRole('button', { name: /Ember Vale/ })
      .first()
      .click()
    await page.getByRole('button', { name: 'Continue', exact: true }).click()
    await page.getByRole('button', { name: /Wren/ }).click()
    const draftId = page.url().match(/[?&]draft=([^&]+)/)[1]
    // Leave for Home without pressing Save: the leave snapshot must keep Wren.
    await page.getByRole('link', { name: 'Home' }).click()
    await page.waitForURL(`${BASE}/`, { timeout: 30000 })
    await page.goto(`${BASE}/new-story?draft=${draftId}`, { waitUntil: 'networkidle' })
    await page.getByText('Selected', { exact: false }).waitFor({ timeout: 30000 })
    const restored = await page.locator('main').innerText()
    record(S, 'unsaved cast survives Home and back', /1 of 6 max/.test(restored), '')
    record(S, 'recovery is labeled local, not saved', /locally/i.test(restored), '')

    // Fail a save, edit again AFTER the failure, leave, reopen: the
    // newest edit — not the pre-failure one — survives.
    const newestTitle = `Newest edit ${Date.now().toString(36)}`
    docker('stop ember-vale-api-1')
    try {
      await page.getByRole('button', { name: /Ash/ }).click()
      await page.getByRole('button', { name: 'Save draft' }).click()
      await page
        .getByText(/save failed/i)
        .first()
        .waitFor({ timeout: 60000 })
      await page.getByRole('button', { name: 'Story' }).click()
      await page.getByLabel('Title').fill(newestTitle)
      await page.getByRole('link', { name: 'Home' }).click()
      await page.waitForURL(`${BASE}/`, { timeout: 30000 })
    } finally {
      docker('start ember-vale-api-1')
      await waitApiReady()
    }
    await page.goto(`${BASE}/new-story?draft=${draftId}`, { waitUntil: 'networkidle' })
    // Recovery restores the saved step too (Title step here): assert the
    // input value, then step back to Characters for the cast count.
    await page.getByLabel('Title').waitFor({ timeout: 60000 })
    const restoredTitle = await page.getByLabel('Title').inputValue()
    await page.getByRole('button', { name: 'Characters' }).click()
    await page.getByText('Selected', { exact: false }).waitFor({ timeout: 30000 })
    const afterFailure = await page.locator('main').innerText()
    record(
      S,
      'post-failure edit survives leave and reopen',
      /2 of 6 max/.test(afterFailure) && restoredTitle === newestTitle,
      restoredTitle
    )
    await ctx.close()
  }

  if (run('createleave')) // ---- Begin, leave mid-create, release: no redirect --------------------
  {
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
    const page = await ctx.newPage()
    const S = 'createleave'
    await page.goto(`${BASE}/new-story?quickstart=1`, { waitUntil: 'networkidle' })
    await page.getByRole('button', { name: 'Begin the story' }).waitFor({ timeout: 30000 })
    // Pause first so the create response is deterministically held: Begin
    // issues the POST, then the user leaves while it is still pending.
    docker('pause ember-vale-api-1')
    try {
      await page.getByRole('button', { name: 'Begin the story' }).click()
      await page.getByRole('button', { name: 'Creating…' }).waitFor({ timeout: 15000 })
      await page.getByRole('link', { name: 'Home' }).click()
      await page.waitForURL(`${BASE}/`, { timeout: 15000 })
    } finally {
      docker('unpause ember-vale-api-1')
      await waitApiReady()
    }
    await page.waitForTimeout(3000)
    record(
      S,
      'departed user is not redirected by the late create',
      page.url() === `${BASE}/`,
      page.url()
    )
    await ctx.close()
  }

  if (run('failedsave')) // ---- Failed wizard save ----------------------------------------------
  {
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
    const page = await ctx.newPage()
    const S = 'failedsave'
    await page.goto(`${BASE}/new-story`, { waitUntil: 'networkidle' })
    await page
      .getByRole('button', { name: /Ember Vale/ })
      .first()
      .waitFor({ timeout: 30000 })
    docker('stop ember-vale-api-1')
    try {
      await page
        .getByRole('button', { name: /Ember Vale/ })
        .first()
        .click()
      await page.getByRole('button', { name: 'Continue', exact: true }).click()
      await page
        .getByText(/save failed/i)
        .first()
        .waitFor({ timeout: 30000 })
      record(S, 'failed save surfaces a failed state, input kept', true)
      const retryVisible = await page.getByRole('button', { name: 'Retry save' }).count()
      record(S, 'retry action is offered', retryVisible > 0, '')
    } finally {
      docker('start ember-vale-api-1')
      await waitApiReady()
    }
    await page.getByRole('button', { name: 'Retry save' }).click()
    await page
      .getByText(/· saved/)
      .first()
      .waitFor({ timeout: 30000 })
    record(S, 'retry after recovery persists the draft', true)
    await page.screenshot({ path: path.join(OUT, 'wizard-failedsave.png') })
    await ctx.close()
  }

  if (run('adoptretry')) // ---- Failed adoption -> failed restore -> retry dismissal ----
  {
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
    const page = await ctx.newPage()
    const S = 'adoptretry'
    const world = await createStudioWorld('Adopt')
    record(S, 'throwaway world preset created', true, `${world.id} rev ${world.current_revision}`)
    await page.goto(`${BASE}/new-story`, { waitUntil: 'networkidle' })
    await page.getByRole('button', { name: world.name }).first().waitFor({ timeout: 30000 })
    await page.getByRole('button', { name: world.name }).first().click()
    await page.getByRole('button', { name: 'Continue', exact: true }).click()
    await page.waitForURL(/draft=/, { timeout: 30000 })
    const draftId = page.url().match(/[?&]draft=([^&]+)/)[1]
    await page.getByRole('button', { name: /Wren/ }).click()
    await page.getByRole('button', { name: /Ash/ }).click()
    await page.getByRole('button', { name: 'Save draft', exact: true }).click()
    await page
      .getByText(/· saved/, { exact: false })
      .first()
      .waitFor({ timeout: 30000 })
    const before = await apiCall('GET', `/story-drafts/${draftId}`)
    const pinsOf = (d) => ({
      world: [d.payload.world.preset_id, d.payload.world.preset_revision],
      cast: d.payload.cast.map((m) => [
        m.instance_key,
        m.preset_id,
        m.preset_revision,
        m.location_key
      ])
    })
    record(
      S,
      'wizard draft pins world rev 1 with cast',
      before.payload.world.preset_revision === 1,
      JSON.stringify(pinsOf(before))
    )

    // Publish a new world revision from the studio: the return carries
    // the adoption offer bound to this draft.
    await page.goto(`${BASE}/new-story/world/${world.id}?draft=${draftId}`, {
      waitUntil: 'networkidle'
    })
    await page.getByRole('button', { name: 'Publish new revision' }).waitFor({ timeout: 30000 })
    await fieldControl(page, 'Distinctive details', 'textarea').fill('Adoption walkthrough marker.')
    await page.getByRole('button', { name: 'Publish new revision' }).click()
    await page.waitForURL(/adopt_revision=2/, { timeout: 60000 })
    await page.getByRole('group', { name: 'Adopt published revision' }).waitFor({ timeout: 30000 })
    record(S, 'studio publish returns the rev-2 adoption offer', true)

    // Accept while the API is down: the pins change locally but the
    // failure notice says the server is untouched.
    docker('stop ember-vale-api-1')
    try {
      await page.getByRole('button', { name: /Adopt revision 2/ }).click()
      await page.getByText('Adoption could not save', { exact: false }).waitFor({ timeout: 60000 })
      record(S, 'failed accept keeps the offer and says pins are unchanged', true)
      // Dismiss while still down: the restoration cannot save either.
      await page.getByRole('button', { name: 'Keep current pins' }).click()
      await page
        .getByText('Could not save the restored pins', { exact: false })
        .waitFor({ timeout: 60000 })
      record(S, 'failed dismissal keeps recovery state for retry', true)
    } finally {
      docker('start ember-vale-api-1')
      await waitApiReady()
    }
    // Retry the dismissal with the API back: the originals restore.
    await page.getByRole('button', { name: 'Keep current pins' }).click()
    await page
      .getByRole('group', { name: 'Adopt published revision' })
      .waitFor({ state: 'detached', timeout: 30000 })
    record(S, 'retry dismissal clears the offer', true)

    // Reload: the durable outcome is the ORIGINAL pins and locations.
    await page.reload({ waitUntil: 'networkidle' })
    await page.getByText(/This draft pins .* rev 1/, { exact: false }).waitFor({ timeout: 30000 })
    const after = await apiCall('GET', `/story-drafts/${draftId}`)
    record(
      S,
      'reload shows original pins and starting locations',
      JSON.stringify(pinsOf(after)) === JSON.stringify(pinsOf(before)),
      JSON.stringify(pinsOf(after))
    )
    await archiveStudioWorld(world.id)
    await ctx.close()
  }

  if (run('addrollback')) // ---- Failed character-add accept restores control ----
  {
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
    const page = await ctx.newPage()
    const S = 'addrollback'
    const emberVale = (await apiCall('GET', '/library/presets?kind=world')).find(
      (p) => p.name === 'Ember Vale'
    )
    const chars = await apiCall('GET', '/library/presets?kind=character')
    const ash = chars.find((p) => p.name === 'Ash')
    const whoOptions = (pg) =>
      pg
        .getByLabel('Play as')
        .evaluate((el) => Array.from(el.options).map((o) => ({ text: o.text, value: o.value })))
    // Player-mode draft with an empty cast: uncontrolled, so accepting
    // Ash (player-ready, outside the cast) takes the add path and hands
    // Ash control. The stepper reaches step 3 without gates. The tone
    // matches the wizard default so failure-stored recovery snapshots
    // compare covered against the server instead of forcing a choice UI.
    const draft = await apiCall('POST', '/story-drafts', {
      payload: {
        world: { preset_id: emberVale.id, preset_revision: emberVale.current_revision },
        cast: [],
        mode: { role: 'player' },
        story: {
          title: `Walkthrough addrollback ${Date.now().toString(36)}`,
          tone: 'hopeful mystery'
        },
        ai: { art_source: 'curated' }
      },
      current_step: 'characters'
    })
    const offerUrl =
      `${BASE}/new-story?draft=${draft.id}` +
      `&adopt_kind=character&adopt_preset=${ash.id}` +
      `&adopt_revision=${ash.current_revision}&adopt_draft=${draft.id}`
    await page.goto(offerUrl, { waitUntil: 'networkidle' })
    await page.getByRole('group', { name: 'Adopt published revision' }).waitFor({ timeout: 30000 })
    record(S, 'character-add offer presents for the mounted draft', true)
    // Step 3 hosts the Play-as control; the offer rides along.
    await page.getByRole('button', { name: 'Play Mode' }).click()
    await page.getByLabel('Play as').waitFor({ timeout: 30000 })
    const beforeOpts = await whoOptions(page)
    record(S, 'uncontrolled draft offers no one', beforeOpts.length === 0, `${beforeOpts.length}`)
    // Fail the accept: Ash joins locally and takes control, but nothing
    // persists.
    docker('stop ember-vale-api-1')
    try {
      await page.getByRole('button', { name: /Adopt revision \d+ \(character\)/ }).click()
      await page.getByText('Adoption could not save', { exact: false }).waitFor({ timeout: 60000 })
      record(S, 'failed accept keeps the offer and says pins are unchanged', true)
      const duringOpts = await whoOptions(page)
      const duringValue = await page.getByLabel('Play as').inputValue()
      record(
        S,
        'failed accept controls the added character locally',
        duringOpts.length === 1 && duringValue === 'ash',
        `${duringValue} in ${duringOpts.map((o) => o.value).join(',')}`
      )
      // Dismiss while still down: the restoration cannot save either.
      await page.getByRole('button', { name: 'Keep current pins' }).click()
      await page
        .getByText('Could not save the restored pins', { exact: false })
        .waitFor({ timeout: 60000 })
      record(S, 'failed dismissal keeps recovery state for retry', true)
    } finally {
      docker('start ember-vale-api-1')
      await waitApiReady()
    }
    // Step 3 persists under the contracted `mode` slug, so the dismissal
    // retries exactly where the failure happened — no step workaround.
    await page.getByRole('button', { name: 'Keep current pins' }).click()
    await page
      .getByRole('group', { name: 'Adopt published revision' })
      .waitFor({ state: 'detached', timeout: 30000 })
    record(S, 'retry dismissal clears the offer', true)
    // Reload boots clean on step 3: no false recovery conflict, because
    // server nulls now compare covered against omitted local fields.
    await page.reload({ waitUntil: 'networkidle' })
    await page.getByLabel('Play as').waitFor({ timeout: 30000 })
    const choiceGroups = await page.getByRole('group', { name: 'Recovery choice' }).count()
    record(
      S,
      'reload boots with no false recovery conflict',
      choiceGroups === 0,
      `${choiceGroups} choice group(s)`
    )
    const after = await apiCall('GET', `/story-drafts/${draft.id}`)
    record(
      S,
      'reload leaves the cast empty and uncontrolled on the server',
      after.payload.cast.length === 0 && (after.payload.mode.controlled_cast_key ?? null) === null,
      JSON.stringify(after.payload.mode)
    )
    const afterOpts = await whoOptions(page)
    record(S, 'reload offers no one again', afterOpts.length === 0, `${afterOpts.length}`)
    // Second round: a deliberate intervening location survives dismissal.
    await page.goto(offerUrl, { waitUntil: 'networkidle' })
    await page.getByRole('group', { name: 'Adopt published revision' }).waitFor({ timeout: 30000 })
    await page.getByRole('button', { name: 'Characters' }).click()
    await page.getByText('Selected', { exact: false }).waitFor({ timeout: 30000 })
    docker('stop ember-vale-api-1')
    try {
      await page.getByRole('button', { name: /Adopt revision \d+ \(character\)/ }).click()
      await page.getByText('Adoption could not save', { exact: false }).waitFor({ timeout: 60000 })
      // Ash defaults to Market; move Ash to Hearth, then dismiss. The
      // pins no longer match the attempt, so the rollback must stand down.
      await page.getByLabel('Starts at').selectOption('hearth')
      await page.getByRole('button', { name: 'Keep current pins' }).click()
      await page
        .getByRole('group', { name: 'Adopt published revision' })
        .waitFor({ state: 'detached', timeout: 30000 })
      const keptLoc = await page.getByLabel('Starts at').inputValue()
      await page.getByRole('button', { name: 'Play Mode' }).click()
      await page.getByLabel('Play as').waitFor({ timeout: 30000 })
      const keptOpts = await whoOptions(page)
      record(
        S,
        'deliberate intervening location is preserved on dismiss',
        keptLoc === 'hearth' && keptOpts.length === 1,
        `${keptLoc} with ${keptOpts.map((o) => o.value).join(',')}`
      )
    } finally {
      docker('start ember-vale-api-1')
      await waitApiReady()
    }
    // The skipped rollback persisted nothing: the server never saw Ash.
    await page.reload({ waitUntil: 'networkidle' })
    const final = await apiCall('GET', `/story-drafts/${draft.id}`)
    record(
      S,
      'skipped rollback leaves the server draft untouched',
      final.payload.cast.length === 0 && (final.payload.mode.controlled_cast_key ?? null) === null,
      `${final.payload.cast.length} member(s)`
    )
    await ctx.close()
  }

  if (run('publishretry')) // ---- Ambiguous publish replays Older, Newest stays dirty ----
  {
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
    const page = await ctx.newPage()
    const S = 'publishretry'
    const world = await createStudioWorld('Publish')
    const OLDER = `Older marker ${Date.now().toString(36)}`
    const NEWER = `Newest marker ${Date.now().toString(36)}`
    await page.goto(`${BASE}/library/world/${world.id}`, { waitUntil: 'networkidle' })
    await page.getByRole('button', { name: 'Publish new revision' }).waitFor({ timeout: 30000 })
    await fieldControl(page, 'Distinctive details', 'textarea').fill(OLDER)
    // Lose exactly the publish response: the save commits server-side,
    // the client sees a failure and freezes the Older snapshot.
    await page.route(
      '**/editor-drafts/*/publish*',
      async (route) => {
        const real = await route.fetch()
        await real.text()
        await route.fulfill({
          status: 502,
          contentType: 'application/json',
          body: '{"error":{"code":"BAD_GATEWAY","message":"walkthrough dropped the publish response"}}'
        })
      },
      { times: 1 }
    )
    await page.getByRole('button', { name: 'Publish new revision' }).click()
    await page
      .getByRole('button', { name: 'Retry publish', exact: true })
      .waitFor({ timeout: 30000 })
    record(S, 'lost publish response surfaces Retry publish', true)
    // Newer edits land after the frozen snapshot.
    await fieldControl(page, 'Distinctive details', 'textarea').fill(`${OLDER} ${NEWER}`)
    await page.getByRole('button', { name: 'Retry publish', exact: true }).click()
    await page.getByText(/Published revision 2/, { exact: false }).waitFor({ timeout: 30000 })
    await page
      .getByText('Newer edits are still unsaved', { exact: false })
      .waitFor({ timeout: 30000 })
    record(S, 'replay publishes while newer edits stay dirty', true)
    const formText = await fieldControl(page, 'Distinctive details', 'textarea').inputValue()
    record(
      S,
      'newer edits remain in the form and recoverable',
      formText.includes(NEWER),
      formText.slice(0, 80)
    )
    // Durable outcome: exactly one new revision, carrying Older only.
    const head = await apiCall('GET', `/library/presets/${world.id}`)
    const rev2 = await apiCall('GET', `/library/presets/${world.id}?revision=2`)
    record(
      S,
      'published revision contains Older, not Newest, with no duplicate',
      head.current_revision === 2 &&
        rev2.revision.description.includes(OLDER) &&
        !rev2.revision.description.includes(NEWER),
      `rev ${head.current_revision}: ${rev2.revision.description.slice(0, 80)}`
    )
    // Finish with newer edits outstanding must stay: completing would
    // abandon them, so the studio holds its ground instead of leaving.
    const replayUrl = page.url()
    await page.getByRole('button', { name: 'Finish & return' }).click()
    await page.waitForTimeout(3000)
    record(
      S,
      'Finish with newer edits stays instead of abandoning',
      page.url() === replayUrl,
      page.url()
    )
    // Publish the newer edits too, then finish cleanly.
    await page.getByRole('button', { name: 'Publish new revision' }).click()
    await page.getByText(/Published revision 3/, { exact: false }).waitFor({ timeout: 60000 })
    await page.getByRole('button', { name: 'Finish & return' }).click()
    await page.waitForURL(/\/library\?tab=worlds/, { timeout: 30000 })
    record(S, 'finish after publishing everything returns', true)
    await archiveStudioWorld(world.id)
    await ctx.close()
  }

  if (run('finishblocked')) // ---- Failed save blocks Finish, edits intact ----
  {
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
    const page = await ctx.newPage()
    const S = 'finishblocked'
    const world = await createStudioWorld('Finish')
    const MARKER = `Finish marker ${Date.now().toString(36)}`
    await page.goto(`${BASE}/library/world/${world.id}`, { waitUntil: 'networkidle' })
    await page.getByRole('button', { name: 'Publish new revision' }).waitFor({ timeout: 30000 })
    await fieldControl(page, 'Distinctive details', 'textarea').fill(MARKER)
    const studioUrl = page.url()
    docker('stop ember-vale-api-1')
    try {
      await page.getByRole('button', { name: 'Publish new revision' }).click()
      await page.getByRole('button', { name: /retry save/ }).waitFor({ timeout: 60000 })
      record(S, 'failed publish surfaces operation-specific retry', true)
      // Finish must not navigate away while the save cannot land.
      await page.locator('.istep').getByRole('button', { name: 'Review' }).click()
      await page.getByRole('button', { name: 'Finish & save' }).click()
      await page.waitForTimeout(3000)
      const stayed = page.url() === studioUrl
      const kept = await fieldControl(page, 'Distinctive details', 'textarea').inputValue()
      record(S, 'Finish does not abandon unsaved edits', stayed && kept === MARKER, page.url())
    } finally {
      docker('start ember-vale-api-1')
      await waitApiReady()
    }
    await page.getByRole('button', { name: /retry save/ }).click()
    await page.getByText('Saved.', { exact: false }).first().waitFor({ timeout: 30000 })
    record(S, 'retry after recovery saves', true)
    // Reload: the marker persisted server-side, not just locally.
    await page.reload({ waitUntil: 'networkidle' })
    await page.getByRole('button', { name: 'Publish new revision' }).waitFor({ timeout: 30000 })
    const reloaded = await fieldControl(page, 'Distinctive details', 'textarea').inputValue()
    record(S, 'saved edit survives reload', reloaded === MARKER, reloaded.slice(0, 60))
    await archiveStudioWorld(world.id)
    await ctx.close()
  }

  if (run('duplicateroute')) // ---- Second same-named destination survives save/publish/reload ----
  {
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
    const page = await ctx.newPage()
    const S = 'duplicateroute'
    const world = await createStudioWorld('Duplicates')
    await page.goto(`${BASE}/library/world/${world.id}`, { waitUntil: 'networkidle' })
    await page.getByRole('button', { name: 'Publish new revision' }).waitFor({ timeout: 30000 })
    // A second place named Market: both Markets gain key-suffixed labels.
    await page.getByRole('button', { name: 'Add place' }).click()
    await fieldControl(page, 'Name', 'input').fill('Market')
    await page.locator('.places__tab', { hasText: 'Hearth' }).click()
    const connSel = fieldControl(page, 'Connected to', 'select')
    const options = await connSel.evaluate((el) => Array.from(el.options).map((o) => o.text))
    const dupes = options.filter((o) => /^Market \(.+\)$/.test(o))
    record(
      S,
      'duplicate names render key-disambiguated labels',
      dupes.length === 2,
      options.join(' | ')
    )
    await connSel.selectOption({ label: dupes[1] })
    const pickedKey = dupes[1].match(/\((.+)\)/)[1]
    await page.getByRole('button', { name: 'Save draft', exact: true }).click()
    await page
      .locator('.dirty', { hasText: 'Unsaved changes' })
      .waitFor({ state: 'detached', timeout: 30000 })
    await page.getByRole('button', { name: 'Publish new revision' }).click()
    await page.getByText(/Published revision 2/, { exact: false }).waitFor({ timeout: 60000 })
    record(S, 'duplicate-target save and publish land', true)
    // Reload: the destination key — not the first same name — is selected.
    await page.reload({ waitUntil: 'networkidle' })
    await page.getByRole('button', { name: 'Publish new revision' }).waitFor({ timeout: 30000 })
    await page.locator('.places__tab', { hasText: 'Hearth' }).waitFor({ timeout: 30000 })
    const rehydrated = await page.locator('.places__tab').allInnerTexts()
    record(S, 'places rehydrate after reload', rehydrated.length === 3, rehydrated.join(' | '))
    await page.screenshot({ path: path.join(OUT, 'studio-duplicates.png') })
    await page.locator('.places__tab', { hasText: 'Hearth' }).click()
    const reselected = await fieldControl(page, 'Connected to', 'select').inputValue()
    const rev2 = await apiCall('GET', `/library/presets/${world.id}?revision=2`)
    const legs = rev2.revision.travel.filter(([src]) => src === 'hearth')
    record(
      S,
      'reload keeps the second Market selected by key',
      reselected === dupes[1] && legs.length === 1 && legs[0][1] === pickedKey,
      `${reselected} / ${JSON.stringify(legs)}`
    )
    await archiveStudioWorld(world.id)
    await ctx.close()
  }

  if (run('firstcreate')) // ---- First-preset creation, frozen across reload ----
  {
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
    const page = await ctx.newPage()
    const S = 'firstcreate'
    const stamp = Date.now().toString(36)
    const pub = (page) => page.locator('section[aria-label="Publication"]')
    // World creation: name, create, land on the real studio at rev 1.
    await page.goto(`${BASE}/library/world/new`, { waitUntil: 'networkidle' })
    await page
      .getByRole('button', { name: 'Create preset', exact: true })
      .waitFor({ timeout: 30000 })
    await pub(page).locator('input').fill(`Walkthrough First ${stamp}`)
    await page.getByRole('button', { name: 'Create preset', exact: true }).click()
    await page.waitForURL(/\/library\/world\/[0-9a-f-]+/, { timeout: 60000 })
    const worldId = page.url().match(/\/library\/world\/([0-9a-f-]+)/)[1]
    const worldDetail = await apiCall('GET', `/library/presets/${worldId}`)
    record(
      S,
      'world creation persists rev 1 and hands off to its studio',
      worldDetail.current_revision === 1 && worldDetail.name === `Walkthrough First ${stamp}`,
      `${worldDetail.name} rev ${worldDetail.current_revision}`
    )
    // Character creation through the same frozen-request machinery.
    await page.goto(`${BASE}/library/character/new`, { waitUntil: 'networkidle' })
    await page
      .getByRole('button', { name: 'Create preset', exact: true })
      .waitFor({ timeout: 30000 })
    await pub(page).locator('input').fill(`Walkthrough First Char ${stamp}`)
    await page.getByRole('button', { name: 'Create preset', exact: true }).click()
    await page.waitForURL(/\/library\/character\/[0-9a-f-]+/, { timeout: 60000 })
    const charId = page.url().match(/\/library\/character\/([0-9a-f-]+)/)[1]
    const charDetail = await apiCall('GET', `/library/presets/${charId}`)
    record(
      S,
      'character creation persists rev 1',
      charDetail.current_revision === 1 && charDetail.name === `Walkthrough First Char ${stamp}`,
      `${charDetail.name} rev ${charDetail.current_revision}`
    )
    // Failed creation freezes the request; reload resumes the identical
    // bytes under the identical key, minting exactly one preset.
    const retryName = `Walkthrough Retry ${stamp}`
    const retryDetails = `Retry marker ${stamp}`
    await page.goto(`${BASE}/library/world/new`, { waitUntil: 'networkidle' })
    await page
      .getByRole('button', { name: 'Create preset', exact: true })
      .waitFor({ timeout: 30000 })
    await pub(page).locator('input').fill(retryName)
    await fieldControl(page, 'Distinctive details', 'textarea').fill(retryDetails)
    docker('stop ember-vale-api-1')
    try {
      await page.getByRole('button', { name: 'Save draft', exact: true }).click()
      await page.getByRole('button', { name: 'Create preset', exact: true }).click()
      await page
        .getByText(/request failed|network failure/, { exact: false })
        .waitFor({ timeout: 60000 })
      record(S, 'failed creation keeps the frozen request', true)
    } finally {
      docker('start ember-vale-api-1')
      await waitApiReady()
    }
    await page.reload({ waitUntil: 'networkidle' })
    await page
      .getByRole('button', { name: 'Retry creation', exact: true })
      .waitFor({ timeout: 30000 })
    const keptName = await pub(page).locator('input').inputValue()
    record(S, 'reload resumes the frozen name and offers retry', keptName === retryName, keptName)
    await page.getByRole('button', { name: 'Retry creation', exact: true }).click()
    await page.waitForURL(/\/library\/world\/[0-9a-f-]+/, { timeout: 60000 })
    const retryId = page.url().match(/\/library\/world\/([0-9a-f-]+)/)[1]
    const listed = await apiCall('GET', '/library/presets?kind=world')
    const dupes = listed.filter((p) => p.name === retryName)
    const retryDetail = await apiCall('GET', `/library/presets/${retryId}`)
    record(
      S,
      'retry after reload mints exactly one preset with its content',
      dupes.length === 1 && retryDetail.revision.description.includes(retryDetails),
      `${dupes.length} preset(s) named ${retryName}`
    )
    // Ambiguous creation: the server commits but the client sees a 502.
    // Changed content must NOT mint a second preset: the retry replays
    // the Older bytes under the Older key, and the Newer edits stay.
    const ambName = `Walkthrough Ambiguous ${stamp}`
    const OLDER_A = `Ambiguous older ${stamp}`
    const NEWER_A = `Ambiguous newer ${stamp}`
    await page.goto(`${BASE}/library/world/new`, { waitUntil: 'networkidle' })
    await page
      .getByRole('button', { name: 'Create preset', exact: true })
      .waitFor({ timeout: 30000 })
    await pub(page).locator('input').fill(ambName)
    await fieldControl(page, 'Distinctive details', 'textarea').fill(OLDER_A)
    await page.getByRole('button', { name: 'Save draft', exact: true }).click()
    await page.waitForTimeout(1000)
    let ambushed = false
    await page.route('**/library/presets**', async (route) => {
      const req = route.request()
      if (req.method() !== 'POST' || ambushed) return route.fallback()
      ambushed = true
      const real = await route.fetch()
      await real.text()
      await route.fulfill({
        status: 502,
        contentType: 'application/json',
        body: '{"error":{"code":"BAD_GATEWAY","message":"walkthrough dropped the creation response"}}'
      })
    })
    await page.getByRole('button', { name: 'Create preset', exact: true }).click()
    await page
      .getByRole('button', { name: 'Retry creation', exact: true })
      .waitFor({ timeout: 60000 })
    record(S, 'ambiguous creation keeps the frozen request with retry', true)
    // Newer edits land after the frozen snapshot; reload before retrying.
    await fieldControl(page, 'Distinctive details', 'textarea').fill(`${OLDER_A} ${NEWER_A}`)
    await page.getByRole('button', { name: 'Save draft', exact: true }).click()
    await page.waitForTimeout(1000)
    await page.reload({ waitUntil: 'networkidle' })
    await page
      .getByRole('button', { name: 'Retry creation', exact: true })
      .waitFor({ timeout: 30000 })
    const ambKeptName = await pub(page).locator('input').inputValue()
    record(
      S,
      'reload resumes the ambiguous name and offers retry',
      ambKeptName === ambName,
      ambKeptName
    )
    await page.getByRole('button', { name: 'Retry creation', exact: true }).click()
    await page.getByText(/Recovered preset/, { exact: false }).waitFor({ timeout: 60000 })
    record(S, 'replay recovers the preset instead of navigating away', true)
    const ambForm = await fieldControl(page, 'Distinctive details', 'textarea').inputValue()
    record(
      S,
      'newer edits remain in the form after recovery',
      ambForm.includes(NEWER_A),
      ambForm.slice(0, 80)
    )
    const ambListed = await apiCall('GET', '/library/presets?kind=world')
    const ambDupes = ambListed.filter((p) => p.name === ambName)
    let ambOk = ambDupes.length === 1
    let ambNote = `${ambDupes.length} preset(s) named ${ambName}`
    if (ambOk) {
      const ambDetail = await apiCall('GET', `/library/presets/${ambDupes[0].id}`)
      ambOk =
        ambDetail.current_revision === 1 &&
        ambDetail.revision.description.includes(OLDER_A) &&
        !ambDetail.revision.description.includes(NEWER_A)
      ambNote = `rev ${ambDetail.current_revision}: ${ambDetail.revision.description.slice(0, 80)}`
    }
    record(S, 'exactly one preset from the original key carries Older, not Newest', ambOk, ambNote)
    // Dismiss must not forget the creation: the association — and the
    // withheld ordinary Create — survive dismissal and reload. Only an
    // explicit separate preset could mint again.
    await page.getByRole('button', { name: 'Dismiss', exact: true }).click()
    await page.getByText(/already created preset/, { exact: false }).waitFor({ timeout: 30000 })
    record(S, 'dismiss keeps the created-preset association', true)
    await page.reload({ waitUntil: 'networkidle' })
    await page.getByText(/already created preset/, { exact: false }).waitFor({ timeout: 30000 })
    const ambFormAfter = await fieldControl(page, 'Distinctive details', 'textarea').inputValue()
    const ambListedAfter = await apiCall('GET', '/library/presets?kind=world')
    const ordinaryCreates = await page
      .getByRole('button', { name: 'Create preset', exact: true })
      .count()
    record(
      S,
      'dismiss plus reload leaves one preset, newer edits kept, ordinary Create withheld',
      ambListedAfter.filter((p) => p.name === ambName).length === 1 &&
        ambFormAfter.includes(NEWER_A) &&
        ordinaryCreates === 0,
      `${ambListedAfter.filter((p) => p.name === ambName).length} preset(s), ${ordinaryCreates} ordinary Create button(s)`
    )
    if (ambDupes.length > 0) await archiveStudioWorld(ambDupes[0].id)
    // Wizard-origin handoff: creating from the wizard returns an
    // explicit adoption offer for revision 1 — never an automatic pin.
    // A fresh context keeps this independent of the recovered slot above.
    const ctxH = await browser.newContext({ viewport: { width: 1440, height: 900 } })
    const wizH = await ctxH.newPage()
    const emberH = (await apiCall('GET', '/library/presets?kind=world')).find(
      (p) => p.name === 'Ember Vale'
    )
    const wrenH = (await apiCall('GET', '/library/presets?kind=character')).find(
      (p) => p.name === 'Wren'
    )
    const wizDraft = await apiCall('POST', '/story-drafts', {
      payload: {
        world: { preset_id: emberH.id, preset_revision: emberH.current_revision },
        cast: [
          {
            instance_key: 'wren',
            preset_id: wrenH.id,
            preset_revision: wrenH.current_revision,
            name: 'Wren',
            location_key: 'hearth'
          }
        ],
        mode: { role: 'watcher' },
        story: { title: `Walkthrough handoff ${stamp}` },
        ai: { art_source: 'curated' }
      },
      current_step: 'review'
    })
    // Created world: the return offers rev 1, accepting pins it.
    await wizH.goto(`${BASE}/new-story/world/new?draft=${wizDraft.id}`, {
      waitUntil: 'networkidle'
    })
    await wizH
      .getByRole('button', { name: 'Create preset', exact: true })
      .waitFor({ timeout: 30000 })
    await pub(wizH).locator('input').fill(`Walkthrough Handoff World ${stamp}`)
    await wizH.getByRole('button', { name: 'Create preset', exact: true }).click()
    await wizH.waitForURL(/adopt_preset=/, { timeout: 60000 })
    const handoffWorldId = new URL(wizH.url()).searchParams.get('adopt_preset')
    await wizH.getByRole('group', { name: 'Adopt created preset' }).waitFor({ timeout: 30000 })
    record(
      S,
      'wizard-origin world creation returns a created-preset offer',
      !!handoffWorldId,
      handoffWorldId ?? ''
    )
    await wizH.getByRole('button', { name: /Adopt revision 1 \(world\)/ }).click()
    await wizH.getByText(/Adopted revision 1/, { exact: false }).waitFor({ timeout: 30000 })
    const wizAfterWorld = await apiCall('GET', `/story-drafts/${wizDraft.id}`)
    record(
      S,
      'accepting pins the created world at rev 1',
      wizAfterWorld.payload.world.preset_id === handoffWorldId &&
        wizAfterWorld.payload.world.preset_revision === 1,
      `world ${wizAfterWorld.payload.world.preset_id} rev ${wizAfterWorld.payload.world.preset_revision}`
    )
    // Created character: accepting adds it to the cast at rev 1.
    await wizH.goto(`${BASE}/new-story/character/new?draft=${wizDraft.id}`, {
      waitUntil: 'networkidle'
    })
    await wizH
      .getByRole('button', { name: 'Create preset', exact: true })
      .waitFor({ timeout: 30000 })
    await pub(wizH).locator('input').fill(`Walkthrough Handoff Char ${stamp}`)
    await wizH.getByRole('button', { name: 'Create preset', exact: true }).click()
    await wizH.waitForURL(/adopt_preset=/, { timeout: 60000 })
    const handoffCharId = new URL(wizH.url()).searchParams.get('adopt_preset')
    await wizH.getByRole('group', { name: 'Adopt created preset' }).waitFor({ timeout: 30000 })
    await wizH.getByRole('button', { name: /Adopt revision 1 \(character\)/ }).click()
    await wizH.getByText(/to the cast/, { exact: false }).waitFor({ timeout: 30000 })
    const wizAfterChar = await apiCall('GET', `/story-drafts/${wizDraft.id}`)
    const addedMember = wizAfterChar.payload.cast.find((m) => m.preset_id === handoffCharId)
    record(
      S,
      'accepting adds the created character at rev 1, world pin untouched',
      addedMember?.preset_revision === 1 && wizAfterChar.payload.world.preset_id === handoffWorldId,
      `cast ${wizAfterChar.payload.cast.length} member(s)`
    )
    if (handoffWorldId) await archiveStudioWorld(handoffWorldId)
    if (handoffCharId) await archiveStudioWorld(handoffCharId)
    await ctxH.close()
    await archiveStudioWorld(worldId)
    await archiveStudioWorld(charId)
    await archiveStudioWorld(retryId)
    await ctx.close()
  }

  if (run('twostories')) // ---- Two stories stay independent across publish+adopt ----
  {
    const ctxA = await browser.newContext({ viewport: { width: 1440, height: 900 } })
    const ctxB = await browser.newContext({ viewport: { width: 1440, height: 900 } })
    const playA = await ctxA.newPage()
    const wizB = await ctxB.newPage()
    const S = 'twostories'
    const world = await createStudioWorld('TwoStories')
    const chars = await apiCall('GET', '/library/presets?kind=character')
    const wren = chars.find((p) => p.name === 'Wren')
    const ash = chars.find((p) => p.name === 'Ash')
    // Story B draft on revision 1 through the wizard.
    await wizB.goto(`${BASE}/new-story`, { waitUntil: 'networkidle' })
    await wizB.getByRole('button', { name: world.name }).first().waitFor({ timeout: 30000 })
    await wizB.getByRole('button', { name: world.name }).first().click()
    await wizB.getByRole('button', { name: 'Continue', exact: true }).click()
    await wizB.waitForURL(/draft=/, { timeout: 30000 })
    const draftB = wizB.url().match(/[?&]draft=([^&]+)/)[1]
    await wizB.getByRole('button', { name: /Wren/ }).click()
    await wizB.getByRole('button', { name: /Ash/ }).click()
    await wizB.getByRole('button', { name: 'Save draft', exact: true }).click()
    await wizB
      .getByText(/· saved/, { exact: false })
      .first()
      .waitFor({ timeout: 30000 })
    record(S, 'story B drafts on world rev 1', true)
    // Story A created on revision 1, then played: journey plus one beat.
    const draftA = await apiCall('POST', '/story-drafts', {
      payload: {
        world: { preset_id: world.id, preset_revision: 1 },
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
            location_key: 'market'
          }
        ],
        mode: { role: 'player', controlled_cast_key: 'wren' },
        story: { title: `Walkthrough two-stories A ${Date.now().toString(36)}` },
        ai: { art_source: 'curated' }
      },
      current_step: 'review'
    })
    const createRes = await fetch(`${API}/stories`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Worldsim-Role': 'watcher',
        'Idempotency-Key': `walkthrough-twostories-${Date.now()}`
      },
      body: JSON.stringify({ draft_id: draftA.id, expected_draft_version: 1 })
    })
    if (!createRes.ok) throw new Error(`story A create -> ${createRes.status}`)
    const storyA = (await createRes.json()).world_id
    await playA.goto(`${BASE}/stories/${storyA}/play`, { waitUntil: 'networkidle' })
    await playA.locator('.play__badge').waitFor({ timeout: 30000 })
    await playA.getByRole('button', { name: 'Start journey' }).click()
    await playA.getByText('Journey begun', { exact: false }).waitFor({ timeout: 15000 })
    await playA.getByRole('button', { name: /Commit beat/ }).click()
    await playA.getByRole('button', { name: /Commit beat 2/ }).waitFor({ timeout: 60000 })
    const castBefore = await playA.locator('.play__cast').innerText()
    const feedBefore = await playA.locator('.play__feed li').count()
    const setupBefore = await apiCall('GET', `/stories/${storyA}/setup`)
    record(
      S,
      'story A plays on rev 1 with committed runtime state',
      feedBefore > 0,
      `${feedBefore} entries`
    )
    // Publish revision 2 from the studio and explicitly adopt it into B.
    const R2 = `TwoStories rev2 ${Date.now().toString(36)}`
    await wizB.goto(`${BASE}/new-story/world/${world.id}?draft=${draftB}`, {
      waitUntil: 'networkidle'
    })
    await wizB.getByRole('button', { name: 'Publish new revision' }).waitFor({ timeout: 30000 })
    await fieldControl(wizB, 'Distinctive details', 'textarea').fill(R2)
    await wizB.getByRole('button', { name: 'Publish new revision' }).click()
    await wizB.waitForURL(/adopt_revision=2/, { timeout: 60000 })
    await wizB.getByRole('button', { name: /Adopt revision 2/ }).click()
    await wizB.getByText(/Adopted revision 2/, { exact: false }).waitFor({ timeout: 30000 })
    const draftBAfter = await apiCall('GET', `/story-drafts/${draftB}`)
    record(
      S,
      'story B explicitly adopts rev 2',
      draftBAfter.payload.world.preset_revision === 2,
      `world rev ${draftBAfter.payload.world.preset_revision}`
    )
    // A is untouched by the publish and the adoption: same setup bytes.
    const setupAfter = await apiCall('GET', `/stories/${storyA}/setup`)
    record(
      S,
      'story A setup is byte-identical after publish+adopt',
      JSON.stringify(setupAfter.payload) === JSON.stringify(setupBefore.payload),
      `world rev ${setupAfter.payload.world.preset_revision}`
    )
    // Create story B from the adopted draft: it must pin rev 2.
    const draftBNow = await apiCall('GET', `/story-drafts/${draftB}`)
    const createBRes = await fetch(`${API}/stories`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Worldsim-Role': 'watcher',
        'Idempotency-Key': `walkthrough-twostories-b-${Date.now()}`
      },
      body: JSON.stringify({ draft_id: draftB, expected_draft_version: draftBNow.version })
    })
    if (!createBRes.ok) throw new Error(`story B create -> ${createBRes.status}`)
    const storyB = (await createBRes.json()).world_id
    record(S, 'story B is created from the adopted draft', storyB !== storyA, storyB)
    const setupB = await apiCall('GET', `/stories/${storyB}/setup`)
    const rev2 = await apiCall('GET', `/library/presets/${world.id}?revision=2`)
    record(
      S,
      'story B initial setup pins rev 2 with its content',
      setupB.payload.world.preset_revision === 2 && rev2.revision.description.includes(R2),
      `world rev ${setupB.payload.world.preset_revision}`
    )
    // Play a beat in B as an observer: journey plus one beat, on rev 2.
    await wizB.goto(`${BASE}/stories/${storyB}/play`, { waitUntil: 'networkidle' })
    await wizB.locator('.play__badge').waitFor({ timeout: 30000 })
    await wizB.getByLabel('Who').selectOption(
      await wizB.getByLabel('Who').evaluate((el) => {
        const at = Array.from(el.options).findIndex((o) => o.text.includes('Wren'))
        if (at < 0) throw new Error('no Wren option')
        return { index: at }
      })
    )
    await wizB.getByRole('button', { name: 'Start journey' }).click()
    await wizB.getByText('Journey begun', { exact: false }).waitFor({ timeout: 15000 })
    await wizB.getByRole('button', { name: /Commit beat/ }).click()
    await wizB.getByRole('button', { name: /Commit beat 2/ }).waitFor({ timeout: 60000 })
    const castB = await wizB.locator('.play__cast').innerText()
    const feedB = await wizB.locator('.play__feed li').count()
    record(
      S,
      'story B plays on rev 2 with its own runtime state',
      feedB > 0 && /Wren[\s\S]*Market/.test(castB),
      `${feedB} entries`
    )
    // Reload both stories: distinct ids, expected setup snapshots, and
    // independent runtime state. B's actions must leave A unchanged.
    await playA.reload({ waitUntil: 'networkidle' })
    await playA.getByRole('button', { name: /Commit beat 2/ }).waitFor({ timeout: 30000 })
    const castAfter = await playA.locator('.play__cast').innerText()
    const feedAfter = await playA.locator('.play__feed li').count()
    await wizB.reload({ waitUntil: 'networkidle' })
    await wizB.getByRole('button', { name: /Commit beat 2/ }).waitFor({ timeout: 30000 })
    const castBAfter = await wizB.locator('.play__cast').innerText()
    const feedBAfter = await wizB.locator('.play__feed li').count()
    const setupAFinal = await apiCall('GET', `/stories/${storyA}/setup`)
    const setupBFinal = await apiCall('GET', `/stories/${storyB}/setup`)
    const draftBFinal = await apiCall('GET', `/story-drafts/${draftB}`)
    record(
      S,
      'reload keeps two independent stories: A on rev 1, B on rev 2',
      storyA !== storyB &&
        castAfter === castBefore &&
        feedAfter === feedBefore &&
        castBAfter === castB &&
        feedBAfter === feedB &&
        JSON.stringify(setupAFinal.payload) === JSON.stringify(setupBefore.payload) &&
        setupBFinal.payload.world.preset_revision === 2 &&
        draftBFinal.payload.world.preset_revision === 2 &&
        draftBFinal.payload.cast.every((m) => ['hearth', 'market'].includes(m.location_key)),
      `A feed ${feedAfter}, B feed ${feedBAfter}`
    )
    await archiveStudioWorld(world.id)
    await ctxA.close()
    await ctxB.close()
  }

  if (run('routes')) // ---- Route compile gate -------------------------------------------------
  {
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
    const page = await ctx.newPage()
    const S = 'routes'
    const bad = []
    page.on('requestfailed', (r) => bad.push(`${r.url().slice(0, 100)} ${r.failure()?.errorText}`))
    page.on('response', (r) => {
      if (r.status() >= 500) bad.push(`${r.url().slice(0, 100)} -> ${r.status()}`)
    })
    for (const route of ['/', '/new-story', '/stories', '/library', '/settings']) {
      await page.goto(`${BASE}${route}`, { waitUntil: 'networkidle' })
      await page.waitForTimeout(800)
    }
    record(
      S,
      'all routes compile and serve without 500s',
      bad.length === 0,
      bad.slice(0, 3).join('; ')
    )
    await ctx.close()
  }

  if (run('narrow')) // ---- Narrow viewport ----------------------------------------------------
  {
    const ctx = await browser.newContext({ viewport: { width: 390, height: 844 } })
    const page = await ctx.newPage()
    const S = 'narrow'
    await page.goto(`${BASE}/new-story?quickstart=1`, { waitUntil: 'networkidle' })
    await page.getByRole('button', { name: 'Begin the story' }).waitFor({ timeout: 30000 })
    await page.screenshot({ path: path.join(OUT, 'review-narrow.png') })
    record(S, 'review renders narrow', true)
    await page.getByRole('button', { name: 'Begin the story' }).click()
    await page.waitForURL(/\/stories\/.+\/play/, { timeout: 30000 })
    await page.locator('.play__badge').waitFor({ timeout: 30000 })
    await page.screenshot({ path: path.join(OUT, 'room-narrow.png') })
    record(S, 'room renders narrow', true)
    await ctx.close()
  }
} catch (err) {
  record('walkthrough', 'uncaught error', false, String(err).split('\n')[0])
  process.exitCode = 1
} finally {
  fs.writeFileSync(
    path.join(OUT, 'results.json'),
    JSON.stringify(
      {
        ok: process.exitCode !== 1,
        base: BASE,
        commit: COMMIT,
        dirty: DIRTY,
        diffSha256: DIFF_SHA,
        untracked: UNTRACKED,
        only: [...ONLY],
        at: new Date().toISOString(),
        results
      },
      null,
      2
    )
  )
  console.log(process.exitCode === 1 ? 'WALKTHROUGH FAILED' : 'WALKTHROUGH PASSED')
  await browser.close()
}
