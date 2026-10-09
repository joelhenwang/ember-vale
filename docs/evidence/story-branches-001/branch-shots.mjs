// Branch from here: the action (Adventure and Watch), the confirmation,
// the new story open, and the Stories list line saying where it came from.
//   node branch-shots.mjs <story id> <out dir> [base url]
import { chromium } from 'playwright-core'

const [story, out, base = 'http://localhost:5183'] = process.argv.slice(2)
const browser = await chromium.launch({ channel: 'msedge' })
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
const errors = []
page.on('pageerror', (e) => errors.push(String(e).slice(0, 200)))
page.on('console', (m) => m.type() === 'error' && errors.push(m.text().slice(0, 200)))
const shot = (name, opts = {}) => page.screenshot({ path: `${out}/${name}.png`, ...opts })

// 1. Adventure: each kept turn's heading offers "Branch from here".
await page.goto(`${base}/stories/${story}/adventure`, { waitUntil: 'networkidle' })
await page.waitForTimeout(1500)
const action = page.locator('.log__branch').nth(1)
await action.scrollIntoViewIfNeeded()
await action.hover()
await page.waitForTimeout(500)
const offered = await page.locator('.log__branch').count()
await shot('1-adventure-branch-action')

// 2. The confirmation says plainly what happens.
await action.click()
await page.waitForSelector('.branch__card')
await page.waitForTimeout(700)
const confirmText = await page.locator('.branch__card').innerText()
await shot('2-confirmation')

// 3. The new story opens.
await page.locator('.branch__go').click()
await page.waitForURL((url) => !url.pathname.includes(story), { timeout: 30000 })
await page.waitForLoadState('networkidle')
await page.waitForTimeout(1500)
const branchUrl = page.url()
await shot('3-new-story-open')

// 4. Stories list: where it came from.
await page.goto(`${base}/stories`, { waitUntil: 'networkidle' })
await page.waitForTimeout(1500)
const origin = page.locator('.scard__origin').first()
await origin.scrollIntoViewIfNeeded()
const originText = await origin.innerText()
await shot('4-stories-provenance')

// 5. Watch: the feed and the event view offer it too.
await page.goto(`${base}/stories/${story}/watch`, { waitUntil: 'networkidle' })
await page.waitForTimeout(1500)
const feedOffers = await page.locator('.ef__branch').count()
await shot('5-watch-feed')
await page.locator('.ef__entry', { hasNotText: 'World ticked' }).first().click()
await page.waitForSelector('dialog.em[open]')
await page.waitForTimeout(1000)
const modalOffers = await page.locator('.em__foot').count()
await shot('6-watch-event-view')
await page.locator('.em__foot .em__act').click()
await page.waitForSelector('.branch__card')
await page.waitForTimeout(700)
await shot('7-watch-confirmation')

// 6. Phone width: the confirmation fits.
await page.setViewportSize({ width: 390, height: 844 })
await page.waitForTimeout(500)
await shot('8-confirmation-phone')

await browser.close()
console.log(
  JSON.stringify(
    { offered, confirmText, branchUrl, originText, feedOffers, modalOffers, errors },
    null,
    1
  )
)
