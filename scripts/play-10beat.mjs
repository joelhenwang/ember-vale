#!/usr/bin/env node
/**
 * Ordinary 10-beat Player validation (play milestone).
 *
 * Drives the real UI in headless Edge against the dev server plus the live
 * stack: wizard-created Player-as-Wren story pinned to the selected
 * provider profile, travel, questions, a reactive travel choice, a mid-
 * session reload with continue, through 10 committed beats. No model
 * settings change here; spend is the beats themselves.
 *
 * Records per-beat waits, fallback notices, answers seen in the room, and
 * a friction log, with screenshots, into --out (committed as evidence).
 * Exit non-zero on any failed step; results are still written.
 *
 * Usage:
 *   node scripts/play-10beat.mjs [--base http://127.0.0.1:5173]
 *     [--out docs/evidence/play-10beat]
 *
 * Requires the compose stack and `npm run dev` up.
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
const OUT = opt('--out', 'docs/evidence/play-10beat')
const EDGE = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe'
const COMMIT = execSync('git rev-parse --short HEAD', { stdio: 'pipe' }).toString().trim()

const QUESTIONS = [
  'What news from the mill, Ash?',
  'Who rang the dawn bell today?',
  'Have traders come far for the market?',
  'What should I watch for on the road?',
  'Ash, what should I do next — head for the mill, or linger here at the market?',
  'What do the millers grind this season?',
  'Is the old bridge safe to cross?',
  'Who keeps the lighthouse at night?',
  'What will the weather do by evening?'
]

const results = []
const friction = []
function record(step, ok, detail = '') {
  results.push({ step, ok, detail: String(detail).slice(0, 300) })
  console.log(`${ok ? 'PASS' : 'FAIL'} [play] ${step}${detail ? ` — ${detail}` : ''}`)
  if (!ok) process.exitCode = 1
}
function note(text) {
  friction.push(text)
  console.log(`NOTE [play] ${text}`)
}

function writeResults(extra = {}) {
  fs.mkdirSync(OUT, { recursive: true })
  fs.writeFileSync(
    path.join(OUT, 'results.json'),
    JSON.stringify(
      {
        slice: 'ordinary 10-beat Player session: pinned story, travel, questions, choice, reload',
        commit: COMMIT,
        at: new Date().toISOString(),
        results,
        friction,
        ...extra
      },
      null,
      2
    ) + '\n'
  )
}

async function clockIndex(page) {
  const meta = await page
    .locator('.play__meta')
    .innerText()
    .catch(() => '')
  const m = meta.match(/Beat (\d+)/)
  return m ? Number(m[1]) : -1
}

async function waitClock(page, want, timeoutMs, label) {
  const started = Date.now()
  for (;;) {
    const at = await clockIndex(page)
    if (at >= want) return Date.now() - started
    if (Date.now() - started > timeoutMs) {
      throw new Error(`${label}: clock still at ${at}, wanted ${want}`)
    }
    await new Promise((r) => setTimeout(r, 5000))
  }
}

async function waitAskReady(page, speak) {
  await page.waitForFunction(
    (region) => {
      const el = [...region.querySelectorAll('button')].find((b) =>
        /Ask with the next beat/.test(b.textContent || '')
      )
      return !!el && !el.disabled
    },
    await speak.elementHandle(),
    { timeout: 60000 }
  )
}

async function commitBeat(page, want, label, shot, alreadyCommitting = false) {
  const started = Date.now()
  // Asking files the attempt into the beat directly (no separate commit
  // click); plain commits and journey completions use the Commit button.
  if (!alreadyCommitting) {
    await page.getByRole('button', { name: new RegExp(`Commit beat ${want}`) }).click()
  }
  // The honest waiting state appears while the beat runs: prove it once.
  if (shot) {
    await page
      .getByText(/still running/, { exact: false })
      .first()
      .waitFor({ timeout: 120000 })
      .catch(() => null)
    const waiting = await page
      .getByText(/still running/, { exact: false })
      .first()
      .innerText()
      .catch(() => '')
    if (waiting) {
      await page.screenshot({ path: path.join(OUT, shot) })
      note(`waiting state shown mid-beat: ${waiting.slice(0, 140)}`)
    }
  }
  try {
    const waited = await waitClock(page, want, 600000, label)
    return { wallMs: Date.now() - started, waited }
  } catch (err) {
    // Ordinary-user recovery, not a script retry: check, then resume.
    note(`${label} did not land in time — using check-again/resume: ${err.message}`)
    await page
      .getByRole('button', { name: /Check again/ })
      .click()
      .catch(() => null)
    await new Promise((r) => setTimeout(r, 30000))
    const at = await clockIndex(page)
    if (at >= want) return { wallMs: Date.now() - started, recovered: 'check-again' }
    const resume = page.getByRole('button', { name: new RegExp(`Resume beat ${want}`) })
    if ((await resume.count()) > 0) {
      await resume.first().click()
      const waited = await waitClock(page, want, 600000, `${label} after resume`)
      return { wallMs: Date.now() - started, waited, recovered: 'resume' }
    }
    throw new Error(`${label}: unrecoverable in-session`)
  }
}

async function askQuestion(page, targetName, topic, want, label) {
  const speak = page.getByRole('region', { name: 'Speak as your character' })
  await speak.getByLabel('Say').fill(topic)
  const options = await speak.getByLabel('To').locator('option').allInnerTexts()
  const match = options.findIndex((t) => t.includes(targetName))
  if (match >= 0) await speak.getByLabel('To').selectOption({ index: match })
  await waitAskReady(page, speak)
  await speak.getByRole('button', { name: 'Ask with the next beat' }).click()
  return commitBeat(page, want, label, want === 2 ? 'waiting.png' : null, true)
}

async function travelTo(page, placeName, want, label) {
  const cast = page.getByRole('region', { name: 'Cast and places' })
  const options = await cast.getByLabel('To').locator('option').allInnerTexts()
  const match = options.findIndex((t) => t.includes(placeName))
  if (match < 0)
    throw new Error(`${label}: no route to ${placeName} (offers: ${options.join('|')})`)
  await cast.getByLabel('To').selectOption({ index: match })
  await cast.getByRole('button', { name: /Start journey|Starting/ }).click()
  return commitBeat(page, want, label, null)
}

function beatCard(page, index) {
  return page.getByRole('article', { name: `Beat ${index}` })
}

async function settleReading(page, index) {
  // Structured beat content loads after the clock moves: wait for spoken
  // lines, or for the card to settle on legacy rendering with no pending
  // detail fetch — never assert mid-load.
  await page
    .waitForFunction(
      (n) => {
        const card = [...document.querySelectorAll('article')].find((a) =>
          new RegExp(`Beat ${n}$`).test(a.getAttribute('aria-label') || '')
        )
        if (!card) return false
        if (card.querySelector('.beat__say')) return true
        return ![...card.querySelectorAll('.beat__empty')].some((e) =>
          /Gathering/.test(e.textContent || '')
        )
      },
      index,
      { timeout: 60000 }
    )
    .catch(() => null)
}

async function answerSpeakers(page, index) {
  const card = beatCard(page, index)
  if ((await card.count()) === 0) return []
  await settleReading(page, index)
  return card
    .locator('.beat__speaker')
    .allInnerTexts()
    .catch(() => [])
}

async function main() {
  fs.mkdirSync(OUT, { recursive: true })
  const browser = await chromium.launch({ executablePath: EDGE, headless: true })
  const beats = []
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
    await page.goto(`${BASE}/new-story`, { waitUntil: 'domcontentloaded' })

    // Step 1: world.
    await page
      .getByRole('button', { name: /Ember Vale/ })
      .first()
      .click()
    await page.getByRole('button', { name: 'Continue' }).click()
    // Step 2: cast.
    await page.getByRole('button', { name: /^Wren —/ }).click()
    await page.getByRole('button', { name: /^Ash —/ }).click()
    await page.getByRole('button', { name: 'Continue' }).click()
    // Step 3: Player as Wren.
    await page.getByRole('button', { name: 'Player' }).click()
    const controlled = page.getByLabel('Play as')
    const who = await controlled.locator('option').allInnerTexts()
    const wrenAt = who.findIndex((t) => /Wren/.test(t))
    if (wrenAt < 0) throw new Error(`no Wren in Play-as options: ${who.join('|')}`)
    await controlled.selectOption({ index: wrenAt })
    await page.getByRole('button', { name: 'Continue' }).click()
    // Step 4: title.
    await page.getByLabel('Title').fill(`Ten beats ${Date.now().toString(36)}`)
    await page.getByRole('button', { name: 'Continue' }).click()
    // Step 5: pin the selected deepseek profile. Provider profiles load
    // asynchronously on entering the step: wait for the options, not a
    // fixed delay.
    const provider = page.getByLabel('Provider')
    await provider
      .locator('option', { hasText: 'Environment default' })
      .waitFor({ timeout: 30000, state: 'attached' })
    await provider
      .locator('option', { hasText: /deepseek/i })
      .waitFor({ timeout: 60000, state: 'attached' })
      .catch(() => {
        throw new Error('deepseek provider never listed')
      })
    const providers = await provider.locator('option').allInnerTexts()
    const deepAt = providers.findIndex((t) => /deepseek/i.test(t))
    await provider.selectOption({ index: deepAt })
    const profile = page.getByLabel('Profile revision')
    await profile
      .locator('option', { hasText: /rev 10/ })
      .waitFor({ timeout: 60000, state: 'attached' })
      .catch(() => {
        throw new Error('deepseek rev10 never listed')
      })
    const selectedProfile = await profile.inputValue().catch(() => '')
    const profileTexts = await profile.locator('option').allInnerTexts()
    const rev10 = profileTexts.find((t) => /rev 10/.test(t))
    record('wizard pins deepseek rev10', !!rev10, profileTexts.join(' | ').slice(0, 200))
    if (rev10) {
      const at = profileTexts.indexOf(rev10)
      await profile.selectOption({ index: at })
    }
    const pinSummary = await page
      .getByText(/Selected:/, { exact: false })
      .first()
      .innerText()
      .catch(() => '')
    record('pin summary names the model', /deepseek/i.test(pinSummary), pinSummary.slice(0, 160))
    void selectedProfile
    await page.getByRole('button', { name: 'Continue' }).click()
    // Step 6: review and begin.
    await page.getByRole('button', { name: 'Begin the story' }).click()
    await page.locator('.play__badge').waitFor({ timeout: 60000 })
    const badge = await page.locator('.play__badge').innerText()
    const meta = await page
      .locator('.play__meta')
      .innerText()
      .catch(() => '')
    record('room grants Player as Wren', badge.includes('Player') && meta.includes('Wren'), badge)
    const banner = await page
      .getByText(/live provider configured|deterministic stand-ins/, { exact: false })
      .first()
      .innerText()
      .catch(() => '')
    note(`provider banner: ${banner.slice(0, 160) || 'not shown'}`)
    const storyId = (page.url().match(/stories\/([^/]+)\/play/) ?? [])[1] ?? 'unknown'
    note(`story ${storyId}`)

    // Beat 1: travel Wren to the Market.
    let want = 1
    let r = await travelTo(page, 'Market', want, 'travel to Market')
    beats.push({ beat: want, kind: 'travel', ...r })
    record('beat 1 commits (travel)', true, `${Math.round(r.wallMs / 1000)}s`)
    want += 1

    // Beats 2-4: questions.
    for (let qi = 0; qi < 3; qi += 1) {
      r = await askQuestion(page, 'Ash', QUESTIONS[qi], want, `question ${qi + 1}`)
      const speakers = await answerSpeakers(page, want)
      const fallback = await beatCard(page, want)
        .getByText(/fell back/, { exact: false })
        .count()
        .catch(() => 0)
      beats.push({ beat: want, kind: 'question', topic: QUESTIONS[qi], speakers, fallback, ...r })
      record(
        `beat ${want} commits (question)`,
        true,
        `${Math.round(r.wallMs / 1000)}s speakers=${speakers.join(',') || 'none'} fallback=${fallback > 0}`
      )
      want += 1
    }

    // Beat 5: the choice question.
    r = await askQuestion(page, 'Ash', QUESTIONS[4], want, 'choice question')
    const advice = await beatCard(page, want)
      .innerText()
      .catch(() => '')
    beats.push({
      beat: want,
      kind: 'choice-question',
      speakers: await answerSpeakers(page, want),
      ...r
    })
    record(`beat ${want} commits (choice question)`, true, `${Math.round(r.wallMs / 1000)}s`)
    await page.screenshot({ path: path.join(OUT, 'beat-card.png') })
    want += 1

    // Beat 6: travel where Ash's answer points, else stay the course.
    const cast = page.getByRole('region', { name: 'Cast and places' })
    const offers = await cast.getByLabel('To').locator('option').allInnerTexts()
    let dest = offers[0] ?? ''
    let reason = 'default first offer'
    if (/mill/i.test(advice) && offers.some((o) => /Mill/.test(o))) {
      dest = offers.find((o) => /Mill/.test(o))
      reason = 'answer mentions the mill'
    } else if (/market|linger|stay/i.test(advice) && offers.some((o) => /Market/.test(o))) {
      dest = offers.find((o) => /Market/.test(o))
      reason = 'answer says linger'
    }
    note(`choice: travel to ${dest} (${reason})`)
    r = await travelTo(page, dest.replace(/ —.*$/, ''), want, 'choice travel')
    beats.push({ beat: want, kind: 'choice-travel', dest, reason, ...r })
    record(
      `beat ${want} commits (choice travel)`,
      true,
      `${Math.round(r.wallMs / 1000)}s to ${dest}`
    )
    want += 1

    // Mid-session reload: the room must restore clock, grant, and rich cards.
    await page.reload({ waitUntil: 'domcontentloaded' })
    await page.locator('.play__badge').waitFor({ timeout: 60000 })
    const reloadedClock = await clockIndex(page)
    record('reload restores the clock', reloadedClock === want - 1, `beat ${reloadedClock}`)
    await page
      .locator('.beat__say')
      .first()
      .waitFor({ timeout: 30000 })
      .catch(() => null)
    const richCards = await page
      .locator('.beat__say')
      .count()
      .catch(() => 0)
    record('reload keeps structured beat cards', richCards > 0, `${richCards} spoken lines`)
    await page.screenshot({ path: path.join(OUT, 'reloaded.png') })

    // Beats 7-10: questions to ten.
    for (let qi = 5; qi < QUESTIONS.length; qi += 1) {
      r = await askQuestion(page, 'Ash', QUESTIONS[qi], want, `question ${qi + 1}`)
      const speakers = await answerSpeakers(page, want)
      const fallback = await beatCard(page, want)
        .getByText(/fell back/, { exact: false })
        .count()
        .catch(() => 0)
      beats.push({ beat: want, kind: 'question', topic: QUESTIONS[qi], speakers, fallback, ...r })
      record(
        `beat ${want} commits (question)`,
        true,
        `${Math.round(r.wallMs / 1000)}s speakers=${speakers.join(',') || 'none'} fallback=${fallback > 0}`
      )
      want += 1
    }
    await page.screenshot({ path: path.join(OUT, 'final.png') })
    const clock = await clockIndex(page)
    record('ten beats committed', clock === 10, `clock at beat ${clock}`)
    writeResults({ beats, storyId })
  } finally {
    await browser.close()
  }
}

main().catch((err) => {
  record('session completed', false, err?.message || String(err))
  writeResults()
})
