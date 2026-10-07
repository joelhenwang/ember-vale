import { chromium } from 'file:///C:/Users/JoelWang/Documents/dev/ember-vale/node_modules/playwright-core/index.mjs'
const [out, ...pages] = process.argv.slice(2)
const browser = await chromium.launch({ channel: 'msedge', headless: true })
const page = await browser.newPage({ viewport: { width: 400, height: 860 } })
for (const spec of pages) {
  const name = spec.slice(0, spec.indexOf('=')); const path = spec.slice(spec.indexOf('=') + 1)
  await page.goto(`http://localhost:5180/${path}`, { waitUntil: 'load', timeout: 90000 })
  await page.waitForTimeout(3500)
  const r = await page.evaluate(() => {
    const over = document.documentElement.scrollWidth - innerWidth
    const wide = []
    for (const el of document.querySelectorAll('body *')) {
      const b = el.getBoundingClientRect()
      if (b.right > innerWidth + 1 && b.width > 0) {
        let p = el.parentElement, clipped = false
        while (p) { const o = getComputedStyle(p).overflowX; if (o === 'auto' || o === 'hidden' || o === 'scroll' || o === 'clip') { clipped = true; break } p = p.parentElement }
        if (!clipped) wide.push(`${el.tagName.toLowerCase()}.${[...el.classList].join('.')} r=${Math.round(b.right)} w=${Math.round(b.width)}`)
      }
    }
    return { over, wide: wide.slice(0, 6) }
  })
  console.log(name, r.over, r.wide.join(' | '))
  await page.screenshot({ path: `${out}/${name}.png`, fullPage: true })
}
await browser.close()
