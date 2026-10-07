import { chromium } from 'file:///C:/Users/JoelWang/Documents/dev/ember-vale/node_modules/playwright-core/index.mjs'
const [out, story] = process.argv.slice(2)
const browser = await chromium.launch({ channel: 'msedge', headless: true })
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
page.on('pageerror', (e) => console.log('page error:', e.message))
page.on('console', (m) => m.type() === 'error' && console.log('console error:', m.text()))
await page.goto(`http://localhost:5180/stories/${story}/adventure`, { waitUntil: 'load', timeout: 90000 })
await page.waitForSelector('.composer', { timeout: 60000 })
await page.waitForTimeout(3000)
const turns = [
  ['do', "Ring my grandmother's brass bell softly and listen for an answer from the bay"],
  ['say', "You're not from the islands. What brings you to the Mirewake at dawn?"],
  ['do', "Look for the bell-keepers' landing and check the tide chart"],
  ['chip', 'Go to'],
  ['wait', ''],
  ['do', "Ask the harbor folk what they know about the drowned city's bells"],
  ['wait', ''],
  ['do', 'Show Ash the burn mark on my palm and tell him how I got it']
]
const results = []
for (const [i, [kind, words]] of turns.entries()) {
  const before = await page.locator('.log__lines > *').count()
  const t = Date.now()
  if (kind === 'chip') {
    const chip = page.locator('.composer__chips button', { hasText: words }).first()
    if (!(await chip.count())) { console.log('no chip', words); continue }
    console.log('chip:', await chip.textContent())
    await chip.click()
  } else if (kind === 'wait') {
    await page.locator('.composer__wait').click()
  } else {
    await page.getByRole('tab', { name: kind === 'say' ? 'Say' : 'Do' }).click()
    await page.fill('.composer__input', words)
    await page.locator('.composer__act').click()
  }
  await page.waitForTimeout(800)
  await page.waitForFunction(() => !document.querySelector('.log__thinking'), null, { timeout: 400000 })
  await page.waitForTimeout(1500)
  const lines = await page.locator('.log__lines > *').allInnerTexts()
  const secs = (Date.now() - t) / 1000
  results.push({ turn: i + 1, kind, words, secs, lines: lines.slice(before) })
  console.log(`--- turn ${i + 1} (${kind}) ${secs}s`)
  console.log(lines.slice(before).join('\n').slice(0, 1500))
  await page.screenshot({ path: `${out}/turn-${i + 1}.png`, fullPage: true })
}
const fs = await import('node:fs')
fs.writeFileSync(`${out}/turns.json`, JSON.stringify(results, null, 2))
await browser.close()
