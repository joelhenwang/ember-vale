/* Watch screen under live autoplay: Play for PLAY s, Pause, then sit idle for IDLE s.
 * Records API requests, 304s, bytes on the wire, long tasks and console errors.
 *   node docs/evidence/perf-reads-001/data/watch-live.mjs <story_id> [play_s] [idle_s]
 */
import { chromium } from 'playwright-core'

const [story, play = '60', idle = '40'] = process.argv.slice(2)
const BASE = 'http://localhost:5180'
const browser = await chromium.launch({ channel: 'msedge' })
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
const errors = []
page.on('console', (m) => m.type() === 'error' && errors.push(m.text().slice(0, 160)))
page.on('pageerror', (e) => errors.push(String(e).slice(0, 160)))
let window_ = 'load'
const rows = []
page.on('response', async (r) => {
  const url = r.url()
  if (!url.includes('/api/v1/')) return
  const sizes = await r.request().sizes().catch(() => null)
  rows.push({
    window: window_,
    path: url.split('/api/v1')[1].split('?')[0].replace(/[0-9a-f-]{36}/g, ':id'),
    status: r.status(),
    wire: sizes ? sizes.responseBodySize + sizes.responseHeadersSize : 0
  })
})
await page.addInitScript(() => {
  window.__long = []
  new PerformanceObserver((l) => {
    for (const e of l.getEntries()) window.__long.push(e.duration)
  }).observe({ type: 'longtask', buffered: true })
})
await page.goto(`${BASE}/stories/${story}/watch`, { waitUntil: 'networkidle' })
window_ = 'play'
await page.getByRole('button', { name: /Play/ }).click()
await page.waitForTimeout(Number(play) * 1000)
await page.getByRole('button', { name: /Pause/ }).click()
await page.waitForTimeout(5000)
window_ = 'idle'
await page.waitForTimeout(Number(idle) * 1000)
const long = await page.evaluate(() => window.__long)
const feed = await page.locator('main').innerText()
await browser.close()

const sum = (w) => {
  const r = rows.filter((x) => x.window === w)
  const by = {}
  for (const x of r) by[x.path] = (by[x.path] ?? 0) + 1
  return {
    requests: r.length,
    not_modified: r.filter((x) => x.status === 304).length,
    errors: r.filter((x) => x.status >= 400).length,
    kb: Math.round(r.reduce((a, x) => a + x.wire, 0) / 1024),
    by
  }
}
console.log(
  JSON.stringify(
    {
      load: sum('load'),
      play: sum('play'),
      idle: sum('idle'),
      long_tasks: long.length,
      long_ms_max: Math.round(Math.max(0, ...long)),
      console_errors: errors,
      feed_chars: feed.length
    },
    null,
    1
  )
)
