import { chromium } from 'file:///C:/Users/JoelWang/Documents/dev/ember-vale/node_modules/playwright-core/index.mjs'
const out = process.argv[2]
const browser = await chromium.launch({ channel: 'msedge', headless: true })
const page = await browser.newPage({ viewport: { width: 400, height: 860 } })
const measure = async (name) => {
  await page.waitForTimeout(900)
  const r = await page.evaluate(() => {
    const wide = []
    for (const el of document.querySelectorAll('body *')) {
      const b = el.getBoundingClientRect()
      if (b.right > innerWidth + 1 && b.width > 0) {
        let p = el.parentElement, clipped = false
        while (p) { const o = getComputedStyle(p).overflowX; if (['auto','hidden','scroll','clip'].includes(o)) { clipped = true; break } p = p.parentElement }
        if (!clipped) wide.push(`${el.tagName.toLowerCase()}.${[...el.classList].join('.')} r=${Math.round(b.right)}`)
      }
    }
    return [document.documentElement.scrollWidth - innerWidth, wide.slice(0, 5)]
  })
  console.log(name, r[0], r[1].join(' | '))
  await page.screenshot({ path: `${out}/${name}.png`, fullPage: true })
}
await page.goto('http://localhost:5180/new-story', { waitUntil: 'load' })
await page.waitForSelector('.nsv__worlds', { timeout: 60000 })
await measure('ns-1')
for (let n = 2; n <= 6; n++) {
  const next = page.getByRole('button', { name: 'Continue' })
  if (await next.isDisabled()) { console.log('continue disabled at', n - 1); break }
  await next.click()
  await measure(`ns-${n}`)
}
for (const [kind, steps] of [['character', 5], ['world', 4]]) {
  await page.goto(`http://localhost:5180/library/${kind}/new`, { waitUntil: 'load' })
  await page.waitForSelector('.istep', { timeout: 60000 })
  for (let n = 1; n <= steps; n++) {
    await page.locator('.istep__step button').nth(n - 1).click()
    await measure(`${kind}-${n}`)
  }
}
await browser.close()
