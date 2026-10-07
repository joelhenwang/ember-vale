import { chromium } from 'file:///C:/Users/JoelWang/Documents/dev/ember-vale/node_modules/playwright-core/index.mjs'
// usage: node shot.mjs OUTDIR WIDTH name=path [name=path...]
const [out, width, ...pages] = process.argv.slice(2)
const browser = await chromium.launch({ channel: 'msedge', headless: true })
const page = await browser.newPage({ viewport: { width: Number(width), height: 1000 } })
page.on('pageerror', (e) => console.log('page error:', e.message))
for (const spec of pages) {
  const name = spec.slice(0, spec.indexOf('=')); const path = spec.slice(spec.indexOf('=') + 1)
  await page.goto(`http://localhost:5180/${path}`, { waitUntil: 'load', timeout: 90000 })
  await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => {})
  await page.waitForTimeout(1500)
  await page.screenshot({ path: `${out}/${name}.png`, fullPage: true })
  const over = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
  console.log(name, 'overflow', over)
}
await browser.close()
