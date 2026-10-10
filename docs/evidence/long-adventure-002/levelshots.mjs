// Screenshots of a story where the hero levelled up: the waiting choice, the
// choice panel (spells), and the level-up line in the dice.
import { chromium } from 'playwright-core'

const [, , base, story, out] = process.argv
const browser = await chromium.launch({ channel: 'msedge' })
const page = await browser.newPage({ viewport: { width: 1300, height: 900 } })
await page.goto(`${base}/stories/${story}/adventure`, { waitUntil: 'networkidle' })
await page.waitForTimeout(2500)
await page.screenshot({ path: `${out}/1-adventure.png` })

const waiting = page.getByRole('button', { name: /level-up choice is waiting/i })
console.log('waiting button:', await waiting.count())
if (await waiting.count()) {
  await waiting.first().click()
  await page.waitForTimeout(1200)
  const panel = page.locator('.lc').first()
  await panel.scrollIntoViewIfNeeded()
  await page.screenshot({ path: `${out}/2-choice.png` })
}

// The level-up line in the dice, wherever it sits in the story.
await page.keyboard.press('Escape')
await page.waitForTimeout(500)
const up = page.getByText(/Level up! .* reaches level/i).first()
console.log('level-up line:', await up.count())
if (await up.count()) {
  await up.scrollIntoViewIfNeeded()
  await page.waitForTimeout(600)
  await page.screenshot({ path: `${out}/3-dice.png` })
}

await page.setViewportSize({ width: 400, height: 860 })
await page.waitForTimeout(1200)
await page.locator('.adv__party').first().scrollIntoViewIfNeeded().catch(() => {})
await page.screenshot({ path: `${out}/4-phone.png` })
await browser.close()
