// Watch: open an event, paint the scene, wait for the picture, open the moment view.
import { chromium } from 'playwright-core'

const [story, out] = process.argv.slice(2)
const browser = await chromium.launch({ channel: 'msedge' })
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
const errors = []
page.on('pageerror', (e) => errors.push(String(e).slice(0, 200)))
page.on('console', (m) => m.type() === 'error' && errors.push(m.text().slice(0, 200)))
const shot = (name) => page.screenshot({ path: `${out}/${name}.png` })

await page.goto(`http://localhost:5180/stories/${story}/watch`, { waitUntil: 'networkidle' })
// The newest scene entry (an entry with narrated text, not "World ticked.").
const entry = page.locator('.ef__entry', { hasNotText: 'World ticked' }).first()
await entry.click()
await page.waitForSelector('dialog.em[open]')
await page.waitForTimeout(1200)
await shot('1-event-no-picture')
const captionBefore = await page.locator('.em__caption').innerText()

await page.getByRole('button', { name: /Paint this scene/ }).click()
await page.waitForSelector('.paint-dlg__go:not([disabled])', { timeout: 30000 })
await page.waitForTimeout(800)
await shot('2-paint-dialog')
await page.locator('.paint-dlg__go').click()
await page.waitForTimeout(1500)
await shot('3-after-paint')

// Reopen the same event while it paints, then wait for the picture.
await page.keyboard.press('Escape').catch(() => {})
await page.waitForTimeout(600)
await entry.click()
await page.waitForSelector('dialog.em[open]')
await page.waitForTimeout(800)
const captionPainting = await page.locator('.em__caption').innerText()
await shot('4-event-painting')
await page.keyboard.press('Escape')
const started = Date.now()
let ready = false
while (Date.now() - started < 180000) {
  await page.waitForTimeout(5000)
  await page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')))
  await entry.click()
  await page.waitForSelector('dialog.em[open]')
  await page.waitForTimeout(600)
  if ((await page.locator('.em__picture').count()) > 0) {
    ready = true
    break
  }
  await page.keyboard.press('Escape')
}
const waited = Math.round((Date.now() - started) / 1000)
await page.waitForTimeout(1500)
await shot('5-event-with-picture')
let momentOpened = false
if (ready) {
  await page.getByRole('button', { name: 'See the moment' }).click()
  await page.waitForTimeout(2000)
  momentOpened = await page.locator('.moment-dlg, [class*="moment-dlg"]').first().isVisible()
  await shot('6-moment-view')
}
await browser.close()
console.log(JSON.stringify({ captionBefore, captionPainting, ready, waited, momentOpened, errors }, null, 1))
