// Party combat: choose a story with fights in New Story, play three turns
// against a scripted storyteller, and photograph the party and the dice.
// Usage: node combat-shots.mjs <out-dir> [base-url]
import { chromium } from 'playwright-core'

const [out, base = 'http://localhost:5182'] = process.argv.slice(2)
const browser = await chromium.launch({ channel: 'msedge' })
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
const errors = []
page.on('pageerror', (e) => errors.push(String(e).slice(0, 200)))
page.on('console', (m) => m.type() === 'error' && errors.push(m.text().slice(0, 200)))
const shot = (name, opts = {}) => page.screenshot({ path: `${out}/${name}.png`, ...opts })

// Quick start fills Wren and Ash in Ember Vale; step back to Play mode.
await page.goto(`${base}/new-story?quickstart`, { waitUntil: 'networkidle' })
await page.waitForTimeout(1500)
await page.locator('.setup__row', { hasText: 'Play mode' }).getByRole('button', { name: 'Edit' }).click()
await page.waitForTimeout(800)
await page.getByRole('button', { name: /An adventure with fights/ }).click()
await page.waitForTimeout(500)
await page.getByRole('radio', { name: 'Half-elf' }).click()
await page.getByRole('radio', { name: 'Ranger' }).click()
await page.waitForTimeout(900)
await page.locator('.hero').scrollIntoViewIfNeeded()
await shot('1-new-story-fights')
await page.getByRole('radio', { name: 'Human' }).click()
await page.getByRole('radio', { name: 'Fighter' }).click()
await page.waitForTimeout(400)
// On to Review, then begin.
for (let i = 0; i < 3; i++) {
  await page.locator('.nsv__footer').getByRole('button', { name: /Continue to/ }).click()
  await page.waitForTimeout(700)
}
await shot('2-review')
await page.getByRole('button', { name: 'Begin the story' }).click()
await page.waitForURL(/\/stories\/.*\/adventure/, { timeout: 60000 })
await page.waitForTimeout(3000)
await shot('3-adventure-start')

// Three turns: wait each time (the scripted storyteller brings the fight).
for (let t = 1; t <= 3; t++) {
  await page.locator('.composer__wait').click()
  await page.waitForFunction(() => !document.querySelector('.log__thinking'), null, {
    timeout: 90000
  })
  await page.waitForTimeout(6000)
  await shot(`4-turn-${t}`)
}
const party = await page.locator('.lead__party').innerText()
const dice = await page.locator('.rolls').allInnerTexts()
await page.locator('.rolls').first().scrollIntoViewIfNeeded()
await page.waitForTimeout(600)
await page.locator('.rolls').first().screenshot({ path: `${out}/5-dice-turn-1.png` })
await page.locator('.rolls').nth(1).screenshot({ path: `${out}/6-dice-turn-2.png` })
await page.locator('.lead__party').screenshot({ path: `${out}/7-party-block.png` })
await page.getByRole('button', { name: /Character details/ }).click()
await page.waitForTimeout(1200)
await shot('8-character-details')
const tags = await page.evaluate(() => /(ENCOUNTER|ATTACK|CAST|RECRUIT)\[/.test(document.body.innerText))
await browser.close()
console.log(JSON.stringify({ party, dice, tagsVisible: tags, errors }, null, 1))
