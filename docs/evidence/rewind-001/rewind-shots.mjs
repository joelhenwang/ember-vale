// Go back to this turn: the two actions on a turn, the confirmation, the
// story after going back, and the path not taken in the Stories list.
//   node rewind-shots.mjs <story id> <out dir> [base url]
import { chromium } from 'playwright-core'

const [story, out, base = 'http://localhost:5183'] = process.argv.slice(2)
const browser = await chromium.launch({ channel: 'msedge' })
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
const errors = []
page.on('pageerror', (e) => errors.push(String(e).slice(0, 200)))
page.on('console', (m) => m.type() === 'error' && errors.push(m.text().slice(0, 200)))
const shot = (name, opts = {}) => page.screenshot({ path: `${out}/${name}.png`, ...opts })

// 1. Adventure: an earlier kept turn offers both actions.
await page.goto(`${base}/stories/${story}/adventure`, { waitUntil: 'networkidle' })
await page.waitForTimeout(1500)
const back = page.locator('.log__branch', { hasText: 'Go back to this turn' })
const offeredBack = await back.count()
const offeredBranch = await page.locator('.log__branch', { hasText: 'Branch from here' }).count()
const action = back.nth(1)
await action.scrollIntoViewIfNeeded()
await action.hover()
await page.waitForTimeout(500)
await shot('1-adventure-turn-actions')

// 2. The confirmation says plainly what happens.
await action.click()
await page.waitForSelector('.branch__card')
await page.waitForTimeout(700)
const confirmText = await page.locator('.branch__card').innerText()
await shot('2-rewind-confirmation')

// 3. Gone back: where the later turns went.
await page.locator('.branch__go').click()
await page.waitForSelector('.branch__kicker:text("Gone back")', { timeout: 30000 })
await page.waitForTimeout(800)
const doneText = await page.locator('.branch__card').innerText()
await shot('3-gone-back')

// 4. The story after going back, reloaded in place.
await page.locator('.branch__go').click()
await page.waitForTimeout(1500)
const url = page.url()
const headings = await page.locator('.log__time').allInnerTexts()
await shot('4-story-after-going-back')

// 5. Stories list: the path not taken is a story of its own.
await page.goto(`${base}/stories`, { waitUntil: 'networkidle' })
await page.waitForTimeout(1500)
const card = page.locator('.scard', { hasText: 'the path not taken' }).first()
await card.scrollIntoViewIfNeeded()
const cardText = await card.innerText()
await shot('5-stories-path-not-taken')

// 6. Watch: the feed offers it to watchers; the confirmation at phone width.
await page.goto(`${base}/stories/${story}/watch`, { waitUntil: 'networkidle' })
await page.waitForTimeout(1500)
const feedBack = await page.locator('.ef__branch', { hasText: 'Go back' }).count()
await shot('6-watch-feed')
await page.locator('.ef__branch', { hasText: 'Go back' }).first().click()
await page.waitForSelector('.branch__card')
await page.setViewportSize({ width: 390, height: 844 })
await page.waitForTimeout(700)
await shot('7-confirmation-phone')

await browser.close()
console.log(
  JSON.stringify(
    { offeredBack, offeredBranch, confirmText, doneText, url, headings, cardText, feedBack, errors },
    null,
    1
  )
)
