// Which running animations are NOT composited, and why (Chromium trace).
import { chromium } from 'playwright-core'
const path = process.argv[2] ?? '/'
const b = await chromium.launch({ channel: 'msedge' })
const c = await b.newContext({ viewport: { width: 1366, height: 820 } })
await c.addInitScript(() => localStorage.setItem('ev.motion', 'full'))
const p = await c.newPage()
const natural = process.argv[3] === 'natural'
if (natural) {
  await b.startTracing(p, {
    categories: ['blink.animations', 'devtools.timeline', 'disabled-by-default-devtools.timeline']
  })
  await p.goto('http://localhost:5181' + path, { waitUntil: 'load' })
  await p.waitForTimeout(6000)
} else {
  await p.goto('http://localhost:5181' + path, { waitUntil: 'load' })
  await p.waitForTimeout(6000)
  // restart infinite animations so their start (and composite decision) lands in the trace
  await b.startTracing(p, {
    categories: ['blink.animations', 'devtools.timeline', 'disabled-by-default-devtools.timeline']
  })
  await p.evaluate(() =>
    document.getAnimations().forEach((a) => {
      if (a.effect?.getTiming().iterations === Infinity) {
        const t = a.currentTime
        a.cancel()
        a.play()
        a.currentTime = t
      }
    })
  )
  await p.waitForTimeout(1500)
}
const buf = await b.stopTracing()
const trace = JSON.parse(buf.toString())
const events = trace.traceEvents ?? trace
const byId = new Map()
for (const e of events) {
  if (e.name !== 'Animation') continue
  const id = e.id2?.local ?? e.id
  const d = e.args?.data ?? {}
  const r = byId.get(id) ?? { name: '', node: '', failed: new Set(), unsupported: new Set() }
  if (d.displayName) r.name = d.displayName
  if (d.nodeName) r.node = d.nodeName.slice(0, 40)
  if (d.compositeFailed !== undefined) r.failed.add(d.compositeFailed)
  for (const x of d.unsupportedProperties ?? []) r.unsupported.add(x)
  byId.set(id, r)
}
const agg = new Map()
for (const r of byId.values()) {
  const k = r.name + ' | ' + [...r.failed].join(',') + ' | ' + [...r.unsupported].join(',')
  const a = agg.get(k) ?? { ...r, n: 0 }
  a.n++
  agg.set(k, a)
}
for (const a of agg.values())
  console.log(
    String(a.n).padStart(3),
    (a.name || '?').padEnd(26),
    a.node.padEnd(42),
    'failed=' + ([...a.failed].join(',') || '-'),
    [...a.unsupported].join(',')
  )
await b.close()
