import { chromium } from 'file:///C:/Users/JoelWang/Documents/dev/ember-vale/node_modules/playwright-core/index.mjs'
const [out, story] = process.argv.slice(2)
const browser = await chromium.launch({ channel: 'msedge', headless: true })
for (const [w, h] of [[1440, 1000], [1440, 800], [1920, 1080], [400, 860]]) {
  const page = await browser.newPage({ viewport: { width: w, height: h } })
  await page.goto(`http://localhost:5180/stories/${story}/adventure`, { waitUntil: 'load', timeout: 90000 })
  await page.waitForSelector('.composer', { timeout: 60000 })
  await page.waitForTimeout(3000)
  const m = await page.evaluate(() => {
    const st = document.querySelector('.adv__stage').getBoundingClientRect()
    const sd = document.querySelector('.adv__side').getBoundingClientRect()
    return { stageBottom: Math.round(st.bottom), sideBottom: Math.round(sd.bottom), pageScroll: document.documentElement.scrollHeight - innerHeight, overflowX: document.documentElement.scrollWidth - innerWidth }
  })
  console.log(w, h, JSON.stringify(m))
  await page.screenshot({ path: `${out}/adv-${w}x${h}.png`, fullPage: true })
  await page.close()
}
await browser.close()
