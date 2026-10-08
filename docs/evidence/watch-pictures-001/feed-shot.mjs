// The Watch feed with a painted scene marked.
import { chromium } from 'playwright-core'
const [story, out] = process.argv.slice(2)
const browser = await chromium.launch({ channel: 'msedge' })
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
await page.goto(`http://localhost:5180/stories/${story}/watch`, { waitUntil: 'networkidle' })
await page.waitForTimeout(1500)
const marks = await page.locator('.ef__pictured').count()
await page.locator('.ef__pictured').first().scrollIntoViewIfNeeded()
await page.waitForTimeout(500)
await page.locator('.ef__pictured').first().locator('xpath=ancestor::button[1]').screenshot({ path: `${out}/7-feed-mark.png` })
await browser.close()
console.log(JSON.stringify({ marks }))
