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

async function apiCall(method, urlPath, body) {
  const res = await fetch(`${API}${urlPath}`, {
    method,
    headers: { 'Content-Type': 'application/json', 'X-Worldsim-Role': 'watcher' },
    body: body === undefined ? undefined : JSON.stringify(body)
  })
  if (!res.ok)
    throw new Error(`${method} ${urlPath} -> ${res.status}: ${(await res.text()).slice(0, 200)}`)
  return res.json()
}

const browser = await chromium.launch({ executablePath: EDGE, headless: true })

try {
  // ---- Observer journey (desktop) -------------------------------------
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

  // ---- Player journey (Wren controlled, Ash sorts first) ----------------
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

  // ---- Wizard Player creation (explicit Wren selection) -----------------
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

  // ---- Director seat and intervention queue ---------------------------
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

  // ---- Dirty in-app navigation and recovery ------------------------------
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

  // ---- Begin, leave mid-create, release: no redirect --------------------
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

  // ---- Failed wizard save ----------------------------------------------
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

  // ---- Route compile gate -------------------------------------------------
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

  // ---- Narrow viewport ----------------------------------------------------
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
      { ok: process.exitCode !== 1, base: BASE, at: new Date().toISOString(), results },
      null,
      2
    )
  )
  console.log(process.exitCode === 1 ? 'WALKTHROUGH FAILED' : 'WALKTHROUGH PASSED')
  await browser.close()
}
