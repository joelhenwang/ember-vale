import { chromium } from 'playwright-core'
const [story, out] = process.argv.slice(2)
const browser = await chromium.launch({ channel: 'msedge' })
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
const errors = []
page.on('pageerror', (e) => errors.push(String(e).slice(0, 200)))
await page.goto(`http://localhost:5180/stories/${story}/adventure`, { waitUntil: 'networkidle' })
await page.waitForTimeout(2500)
await page.screenshot({ path: out })
const dice = await page.getByText('The dice').count()
const party = await page.getByText('Your party').count()
await browser.close()
console.log(JSON.stringify({ dice, party, errors }))
