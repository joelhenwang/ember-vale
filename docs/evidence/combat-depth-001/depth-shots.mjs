// Combat depth: a cleric hero against two goblins (each its own health), a
// spent slot and "no slot left", an XP gain and a level-up, and the dice in
// Watch. Runs against the worktree API serving scripted_storyteller.py.
// Usage: node depth-shots.mjs <out-dir> <python> [base-url]
import { execFileSync } from 'node:child_process'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { chromium } from 'playwright-core'

const [out, python, base = 'http://localhost:5182'] = process.argv.slice(2)
const here = dirname(fileURLToPath(import.meta.url))
const browser = await chromium.launch({ channel: 'msedge' })
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
const errors = []
page.on('pageerror', (e) => errors.push(String(e).slice(0, 200)))
page.on('console', (m) => m.type() === 'error' && errors.push(m.text().slice(0, 200)))
const shot = (name, opts = {}) => page.screenshot({ path: `${out}/${name}.png`, ...opts })
// The party block sits in a column that scrolls on its own: photograph the
// full party in the Character details drawer instead.
async function partyShot(name) {
  await page.getByRole('button', { name: /Character details/ }).click()
  await page.waitForTimeout(1200)
  await page.locator('.sheet__party').screenshot({ path: `${out}/${name}.png` })
  await page.locator('.drawer__close').click()
  await page.waitForTimeout(800)
}
// Quick start fills Wren and Ash in Ember Vale; step back to Play mode.
await page.goto(`${base}/new-story?quickstart`, { waitUntil: 'networkidle' })
await page.waitForTimeout(1500)
await page.locator('.setup__row', { hasText: 'Play mode' }).getByRole('button', { name: 'Edit' }).click()
await page.waitForTimeout(800)
await page.getByRole('button', { name: /An adventure with fights/ }).click()
await page.waitForTimeout(500)
await page.getByRole('radio', { name: 'Human' }).click()
await page.getByRole('radio', { name: 'Cleric' }).click()
await page.waitForTimeout(400)
for (let i = 0; i < 3; i++) {
  await page.locator('.nsv__footer').getByRole('button', { name: /Continue to/ }).click()
  await page.waitForTimeout(700)
}
await page.getByRole('button', { name: 'Begin the story' }).click()
await page.waitForURL(/\/stories\/.*\/adventure/, { timeout: 60000 })
const storyId = page.url().match(/stories\/([0-9a-f-]{36})/)[1]
// One goblin (50 XP) should cross level 2 (300 XP) in a short run.
execFileSync(python, [join(here, 'prime_xp.py'), storyId, '260'], { stdio: 'inherit' })
await page.reload({ waitUntil: 'networkidle' })
await page.waitForTimeout(2500)

const turns = []
let levelled = false
for (let t = 1; t <= 6 && !levelled; t++) {
  await page.locator('.composer__wait').click()
  await page.waitForFunction(() => !document.querySelector('.log__thinking'), null, {
    timeout: 90000
  })
  await page.waitForTimeout(5000)
  const rolls = await page.locator('.rolls').last().innerText()
  turns.push({ turn: t, rolls })
  levelled = (await page.locator('.roll--level').count()) > 0
  if (t === 1) {
    await shot('1-turn-1')
    await page.locator('.rolls').last().screenshot({ path: `${out}/2-dice-two-goblins-no-slot.png` })
    await partyShot('3-party-two-goblins')
  }
}
await page.locator('.rolls').last().scrollIntoViewIfNeeded()
await page.waitForTimeout(400)
await shot('4-level-up-turn')
await page.locator('.rolls').last().screenshot({ path: `${out}/5-dice-xp-level-up.png` })
await partyShot('6-party-level-up')
const party = await page.locator('.lead__party').innerText()
await page.getByRole('button', { name: /Character details/ }).click()
await page.waitForTimeout(1200)
await shot('7-character-details')
const tags = await page.evaluate(() => /(ENCOUNTER|ATTACK|CAST|RECRUIT)\[/.test(document.body.innerText))

// The same story in Watch: the feed marks scenes with dice; the event view shows them.
await page.goto(`${base}/stories/${storyId}/watch`, { waitUntil: 'networkidle' })
await page.waitForTimeout(3000)
await page.getByRole('tab', { name: /Events/ }).click().catch(() => {})
await shot('8-watch-feed')
const marked = page.locator('.ef__entry', { has: page.locator('.ef__dice') })
const markedCount = await marked.count()
await marked.last().click()
await page.waitForTimeout(2000)
await shot('9-watch-event-dice')
const watchDice = await page.locator('.em .rolls').innerText().catch(() => '')
await browser.close()
console.log(
  JSON.stringify(
    { storyId, turns, levelled, party, markedCount, watchDice, tagsVisible: tags, errors },
    null,
    1
  )
)
