// Attribute idle cost to infinite animations: measure main-thread task time,
// style recalc and whole-browser CPU with everything running, with all
// infinite animations paused, and with each animation name paused alone.
import { chromium } from 'playwright-core'
const path = process.argv[2] ?? '/'
const SECS = Number(process.argv[3] ?? 5)
const b = await chromium.launch({ channel: 'msedge' })
const bs = await b.newBrowserCDPSession()
const c = await b.newContext({ viewport: { width: 1366, height: 820 } })
await c.addInitScript(() => localStorage.setItem('ev.motion', 'full'))
const p = await c.newPage()
const cdp = await c.newCDPSession(p)
await cdp.send('Performance.enable')
await p.goto('http://localhost:5181' + path, { waitUntil: 'load' })
await p.waitForTimeout(6000)
const cpu = async () =>
  (await bs.send('SystemInfo.getProcessInfo')).processInfo.reduce((s, x) => s + x.cpuTime, 0)
const M = async () =>
  Object.fromEntries(
    (await cdp.send('Performance.getMetrics')).metrics.map((m) => [m.name, m.value])
  )
async function sample(label) {
  const a = await M()
  const c0 = await cpu()
  await p.waitForTimeout(SECS * 1000)
  const z = await M()
  const c1 = await cpu()
  return {
    label,
    main: (((z.TaskDuration - a.TaskDuration) / SECS) * 100).toFixed(1),
    style: (((z.RecalcStyleDuration - a.RecalcStyleDuration) / SECS) * 1000).toFixed(0),
    layout: (((z.LayoutDuration - a.LayoutDuration) / SECS) * 1000).toFixed(0),
    cpu: (((c1 - c0) / SECS) * 100).toFixed(1)
  }
}
const names = await p.evaluate(() => {
  const m = {}
  for (const a of document.getAnimations()) {
    if (a.effect?.getTiming().iterations !== Infinity) continue
    const n = a.animationName ?? 'waapi'
    const t = a.effect.target
    m[n] = m[n] ?? { n: 0, sample: '' }
    m[n].n++
    m[n].sample = (t?.className?.baseVal ?? t?.className ?? t?.tagName ?? '')
      .toString()
      .slice(0, 40)
  }
  return m
})
console.log('infinite animations', JSON.stringify(names))
const rows = []
rows.push(await sample('all running'))
await p.evaluate(() =>
  document
    .getAnimations()
    .forEach((a) => a.effect?.getTiming().iterations === Infinity && a.pause())
)
rows.push(await sample('all infinite paused'))
await p.evaluate(() =>
  document.getAnimations().forEach((a) => a.effect?.getTiming().iterations === Infinity && a.play())
)
for (const n of Object.keys(names)) {
  await p.evaluate(
    (n) =>
      document
        .getAnimations()
        .forEach(
          (a) =>
            a.effect?.getTiming().iterations === Infinity &&
            (a.animationName ?? 'waapi') === n &&
            a.pause()
        ),
    n
  )
  rows.push(await sample('without ' + n + ' x' + names[n].n))
  await p.evaluate(
    (n) =>
      document
        .getAnimations()
        .forEach(
          (a) =>
            a.effect?.getTiming().iterations === Infinity &&
            (a.animationName ?? 'waapi') === n &&
            a.play()
        ),
    n
  )
}
console.table(rows)
await b.close()
