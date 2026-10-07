import { chromium } from 'file:///C:/Users/JoelWang/Documents/dev/ember-vale/node_modules/playwright-core/index.mjs'
const out = process.argv[2]
const browser = await chromium.launch({ channel: 'msedge', headless: true })
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
page.on('pageerror', (e) => console.log('page error:', e.message))
await page.goto('http://localhost:5180/', { waitUntil: 'load', timeout: 90000 })
await page.waitForSelector('.hero', { timeout: 60000 })
await page.waitForTimeout(1200)
// slide: home -> library, capture mid-transition
await page.click('nav.nav >> text=Library')
await page.waitForTimeout(190)
await page.screenshot({ path: `${out}/slide-mid.png` })
await page.waitForTimeout(1500)
// back to home: is the loading line ever shown?
let flashed = false
page.on('console', () => {})
await page.click('nav.nav >> text=Home')
for (let i = 0; i < 10; i++) {
  if (await page.locator('text=Opening the library').count()) flashed = true
  await page.waitForTimeout(50)
}
console.log('home loading line shown on return:', flashed)
await page.click('nav.nav >> text=Library')
await page.waitForTimeout(900)
let libFlash = await page.locator('text=Reading the archive').count()
console.log('library loading line on return:', libFlash)
// card menu
await page.locator('.libcard .cmenu__dots').first().click()
await page.waitForTimeout(350)
await page.screenshot({ path: `${out}/menu.png`, clip: { x: 0, y: 300, width: 800, height: 450 } })
console.log('menu items:', await page.locator('.cmenu__list button').allTextContents())
await page.keyboard.press('Escape')
await page.waitForTimeout(200)
console.log('menu closed:', (await page.locator('.cmenu__list').count()) === 0)
// tab marker
await page.click('text=Worlds')
await page.waitForTimeout(600)
await page.screenshot({ path: `${out}/tabs.png`, clip: { x: 0, y: 260, width: 1440, height: 120 } })
// button hover
await page.goto('http://localhost:5180/', { waitUntil: 'load' })
await page.waitForSelector('.hero__continue')
await page.waitForTimeout(800)
await page.hover('.hero__continue')
await page.waitForTimeout(500)
const b = await page.locator('.hero__continue').boundingBox()
await page.screenshot({ path: `${out}/btn-hover.png`, clip: { x: b.x - 20, y: b.y - 20, width: b.width + 40, height: b.height + 40 } })
await browser.close()
