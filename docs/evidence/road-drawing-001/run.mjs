import { chromium } from 'file:///C:/Users/JoelWang/Documents/dev/ember-vale/node_modules/playwright-core/index.mjs'
const [out, world] = process.argv.slice(2)
const browser = await chromium.launch({ channel: 'msedge', headless: true })
const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } })
page.on('pageerror', (e) => console.log('page error:', e.message))
page.on('console', (m) => m.type() === 'error' && console.log('console error:', m.text()))
await page.goto(`http://localhost:5180/library/world/${world}/map`, { waitUntil: 'domcontentloaded' })
await page.getByRole('button', { name: 'Blank parchment' }).click()
await page.waitForSelector('.mapframe img', { timeout: 60000 })
await page.waitForTimeout(1200)
const frame = page.locator('.mapframe')
const at = async (fx, fy) => {
  const b = await frame.boundingBox()
  return [b.x + b.width * fx, b.y + b.height * fy]
}
const click = async (fx, fy) => { const [x, y] = await at(fx, fy); await page.mouse.click(x, y) }
const note = async () => (await page.locator('.card__note--road').textContent().catch(() => ''))?.trim()

async function addPlace(fx, fy, name, key) {
  await page.getByRole('button', { name: 'Add a place' }).click()
  await click(fx, fy)
  await page.locator('.inspect input.ev-input').first().fill(name)
  if (key) await page.locator('.inspect select').first().selectOption(key)
}
await addPlace(0.2, 0.3, 'Hearth', 'hearth')
await addPlace(0.78, 0.65, 'Market', 'market')
await addPlace(0.5, 0.15, 'Old Mill', null)
await page.locator('.boardwrap').screenshot({ path: `${out}/1-places.png` })

await page.getByRole('button', { name: 'Draw a road' }).click()
await click(0.2, 0.3) // Hearth pin
await click(0.33, 0.55)
await click(0.5, 0.48)
await click(0.62, 0.72)
await page.keyboard.press('Backspace') // take the last bend back
await click(0.6, 0.7)
const [hx, hy] = await at(0.765, 0.64) // near Market: should snap
await page.mouse.move(hx, hy, { steps: 4 })
await page.waitForTimeout(300)
console.log('snap target shown:', await page.locator('.pin--target').count())
await page.locator('.boardwrap').screenshot({ path: `${out}/2-drawing.png` })
const [hx2, hy2] = await at(0.765, 0.64) // the screenshot may have scrolled the page
await page.mouse.click(hx2, hy2)
console.log('after first road:', await note())
// A straight one, then one with a bend; then a duplicate.
await click(0.2, 0.3); await click(0.5, 0.15)
await click(0.5, 0.15); await click(0.7, 0.3); await click(0.78, 0.65)
await click(0.78, 0.65); await click(0.2, 0.3)
console.log('duplicate:', await note())
await page.keyboard.press('Escape')
await page.keyboard.press('Escape')
console.log('tool after two Esc:', await page.getByRole('button', { name: 'Draw a road' }).count() ? 'select' : 'still drawing')
console.log('roads in table:', await page.locator('.roads tbody tr').count())

// Select the straight Hearth to Old Mill road by clicking its middle.
await click(0.35, 0.225)
console.log('bends shown on selected road:', await page.locator('button.bend:not(.bend--middle)').count(),
  'middles:', await page.locator('.bend--middle').count())
// Pull a bend out of its middle.
const mid = await page.locator('.bend--middle').first().boundingBox()
await page.mouse.move(mid.x + mid.width / 2, mid.y + mid.height / 2)
await page.mouse.down()
const [tx, ty] = await at(0.3, 0.12)
await page.mouse.move(tx, ty, { steps: 6 })
await page.mouse.up()
await page.waitForTimeout(200)
console.log('bends after pulling one out:', await page.locator('button.bend:not(.bend--middle)').count(),
  'road still selected:', await page.locator('.inspect select').count() > 0)
await page.locator('.boardwrap').screenshot({ path: `${out}/3-editing.png` })
const [tx2, ty2] = await at(0.3, 0.12)
// Double-click removes it again.
await page.locator('button.bend:not(.bend--middle)').first().dblclick()
console.log('bends after double-click:', await page.locator('button.bend:not(.bend--middle)').count())
// Put it back for the save.
const mid2 = await page.locator('.bend--middle').first().boundingBox()
await page.mouse.move(mid2.x + mid2.width / 2, mid2.y + mid2.height / 2)
await page.mouse.down(); await page.mouse.move(tx2, ty2, { steps: 6 }); await page.mouse.up()

await page.locator('.roads').screenshot({ path: `${out}/4-roads-table.png` })
await page.getByRole('button', { name: 'Save the map to this world' }).click()
await page.waitForFunction(() => /Saved\. New stories/.test(document.body.innerText), null, { timeout: 30000 })
await page.reload({ waitUntil: 'domcontentloaded' })
await page.waitForSelector('.mapframe img', { timeout: 30000 })
await page.waitForTimeout(1500)
console.log('after reload: pins', await page.locator('.pin').count(), 'roads', await page.locator('.roads tbody tr').count())
await page.locator('.boardwrap').screenshot({ path: `${out}/5-saved.png` })
await page.setViewportSize({ width: 400, height: 900 })
await page.waitForTimeout(500)
console.log('phone overflow:', await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth))
await browser.close()
