import { chromium } from 'playwright-core'
const [out] = process.argv.slice(2)
const browser = await chromium.launch({ channel: 'msedge' })
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
const errors = []
page.on('pageerror', (e) => errors.push(String(e).slice(0, 200)))
await page.goto('http://localhost:5180/stories', { waitUntil: 'networkidle' })
await page.waitForTimeout(1500)
await page.screenshot({ path: out })
const branched = await page.getByText(/Branched from/).count()
await browser.close()
console.log(JSON.stringify({ branched, errors }))
