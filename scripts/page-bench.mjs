#!/usr/bin/env node
/**
 * Page performance bench for the built app (read-only: never plays a turn,
 * paints or creates anything).
 *
 *   npx vite build --outDir <dir> && npx vite preview --port 5181 --outDir <dir>
 *   node scripts/page-bench.mjs [--base http://localhost:5181] [--runs 3]
 *        [--idle 10] [--motion full|reduced] [--only home,adventure]
 *        [--memory 30] [--rested] [--json out.json]
 *
 * Per page, in a fresh browser context (cold cache) each run:
 *   - load: DOMContentLoaded, load, FCP, LCP, CLS, bytes over the wire, requests
 *   - script: long tasks, TBT (sum of long-task time over 50 ms, first 5 s)
 *   - memory: JS heap after a forced GC, DOM nodes, listeners
 *   - idle: renderer main-thread busy % (CDP TaskDuration) and whole-browser
 *     CPU % (all processes, so compositor/GPU work from CSS animations
 *     counts; 100 % = one core) while nothing is touched; then frames per
 *     second and janky frames (> 25 ms) over a separate 3 s window
 * Medians over the runs are printed. `--memory N` instead navigates the app
 * in place N times around its pages and reports heap growth.
 */
import { chromium } from 'playwright-core'
import { writeFileSync } from 'node:fs'

const args = Object.fromEntries(
  process.argv.slice(2).reduce((acc, a, i, all) => {
    if (a.startsWith('--'))
      acc.push([a.slice(2), all[i + 1]?.startsWith('--') ? '1' : (all[i + 1] ?? '1')])
    return acc
  }, [])
)
const BASE = args.base ?? 'http://localhost:5181'
const RUNS = Number(args.runs ?? 3)
const IDLE = Number(args.idle ?? 10)
const MOTION = args.motion ?? 'full'

const PAGES = {
  home: '/',
  stories: '/stories',
  library: '/library',
  newstory: '/new-story',
  studio: '/library/character/67907779-9d37-4c92-9434-e289b2e47609',
  adventure: '/stories/bdea0982-79bd-492e-b836-ad5717af4479/adventure',
  watch: '/stories/54dfd756-49b4-4594-99b3-1b4b234315fe/watch',
  settings: '/settings'
}
const only = args.only ? args.only.split(',') : Object.keys(PAGES)

/* Installed before any page script: collects paint, LCP, CLS and long tasks. */
function observe() {
  const m = (window.__bench = { lcp: 0, cls: 0, long: [], fcp: 0 })
  new PerformanceObserver((l) => {
    for (const e of l.getEntries()) m.lcp = e.startTime
  }).observe({ type: 'largest-contentful-paint', buffered: true })
  new PerformanceObserver((l) => {
    for (const e of l.getEntries()) if (!e.hadRecentInput) m.cls += e.value
  }).observe({ type: 'layout-shift', buffered: true })
  new PerformanceObserver((l) => {
    for (const e of l.getEntries()) m.long.push([e.startTime, e.duration])
  }).observe({ type: 'longtask', buffered: true })
  new PerformanceObserver((l) => {
    for (const e of l.getEntries()) if (e.name === 'first-contentful-paint') m.fcp = e.startTime
  }).observe({ type: 'paint', buffered: true })
}

const median = (xs) => {
  const s = [...xs].sort((a, b) => a - b)
  return s.length ? s[Math.floor((s.length - 1) / 2)] : 0
}
const metric = (list, name) => list.metrics.find((x) => x.name === name)?.value ?? 0

async function cpuTotal(browserSession) {
  const info = await browserSession.send('SystemInfo.getProcessInfo')
  return info.processInfo.reduce((sum, p) => sum + p.cpuTime, 0)
}

async function measure(browser, browserSession, name, path) {
  const context = await browser.newContext({ viewport: { width: 1366, height: 820 } })
  await context.addInitScript((motion) => {
    try {
      localStorage.setItem('ev.motion', motion)
    } catch {
      /* ignore */
    }
  }, MOTION)
  await context.addInitScript(observe)
  const page = await context.newPage()
  const cdp = await context.newCDPSession(page)
  await cdp.send('Performance.enable')
  await cdp.send('Network.enable')
  let bytes = 0
  let requests = 0
  cdp.on('Network.loadingFinished', (e) => {
    bytes += e.encodedDataLength
    requests += 1
  })
  await page.goto(BASE + path, { waitUntil: 'load' })
  await page.waitForTimeout(5000) // data, pictures and entrance animations settle
  const load = await page.evaluate(() => {
    const n = performance.getEntriesByType('navigation')[0]
    const b = window.__bench
    const tbt = b.long
      .filter(([t]) => t < 5000 + n.loadEventEnd)
      .reduce((s, [, d]) => s + Math.max(0, d - 50), 0)
    return {
      dcl: n.domContentLoadedEventEnd,
      load: n.loadEventEnd,
      fcp: b.fcp,
      lcp: b.lcp,
      cls: b.cls,
      longTasks: b.long.length,
      tbt
    }
  })
  const loadBytes = bytes
  const loadRequests = requests

  // memory after a forced GC
  await cdp.send('HeapProfiler.collectGarbage')
  const mem = await cdp.send('Performance.getMetrics')

  // --rested: first leave the page alone past the app's rest threshold
  // (60 s, src/game/motion.ts REST_AFTER_MS), so ambient loops have paused.
  if (args.rested) await page.waitForTimeout(70000)

  // idle: nothing touched for IDLE seconds. No rAF loop runs here: one
  // would force a frame every refresh and inflate the cost being measured.
  const before = await cdp.send('Performance.getMetrics')
  const cpu0 = await cpuTotal(browserSession)
  await page.waitForTimeout(IDLE * 1000)
  const after = await cdp.send('Performance.getMetrics')
  const cpu1 = await cpuTotal(browserSession)
  // then frame pacing over a short separate window
  const FPS_SECS = 3
  const frames = page.evaluate(
    (ms) =>
      new Promise((resolve) => {
        let n = 0
        let janky = 0
        let last = performance.now()
        const end = last + ms
        const tick = (t) => {
          n += 1
          if (t - last > 25) janky += 1
          last = t
          if (t < end) requestAnimationFrame(tick)
          else resolve({ n, janky })
        }
        requestAnimationFrame(tick)
      }),
    FPS_SECS * 1000
  )
  const f = await frames
  const busy = metric(after, 'TaskDuration') - metric(before, 'TaskDuration')
  const style = metric(after, 'RecalcStyleDuration') - metric(before, 'RecalcStyleDuration')
  const layout = metric(after, 'LayoutDuration') - metric(before, 'LayoutDuration')
  const idleBytes = bytes - loadBytes
  const idleRequests = requests - loadRequests
  const animations = await page.evaluate(
    () =>
      document.getAnimations().filter((a) => a.effect?.getTiming().iterations === Infinity).length
  )
  await context.close()
  return {
    page: name,
    dcl: load.dcl,
    load: load.load,
    fcp: load.fcp,
    lcp: load.lcp,
    cls: load.cls,
    kb: loadBytes / 1024,
    requests: loadRequests,
    longTasks: load.longTasks,
    tbt: load.tbt,
    heapMB: metric(mem, 'JSHeapUsedSize') / 1048576,
    nodes: metric(mem, 'Nodes'),
    listeners: metric(mem, 'JSEventListeners'),
    loops: animations,
    mainBusyPct: (busy / IDLE) * 100,
    styleMs: style * 1000,
    layoutMs: layout * 1000,
    cpuPct: ((cpu1 - cpu0) / IDLE) * 100,
    fps: f.n / FPS_SECS,
    janky: f.janky,
    idleRequests,
    idleKB: idleBytes / 1024
  }
}

async function memoryWalk(browser, laps) {
  const context = await browser.newContext({ viewport: { width: 1366, height: 820 } })
  await context.addInitScript((motion) => localStorage.setItem('ev.motion', motion), MOTION)
  const page = await context.newPage()
  const cdp = await context.newCDPSession(page)
  await cdp.send('Performance.enable')
  await page.goto(BASE + '/', { waitUntil: 'load' })
  await page.waitForTimeout(3000)
  const route = [
    '/stories',
    '/library',
    '/settings',
    PAGES.adventure,
    '/',
    '/new-story',
    PAGES.watch,
    '/'
  ]
  const sample = async () => {
    await cdp.send('HeapProfiler.collectGarbage')
    const m = await cdp.send('Performance.getMetrics')
    return {
      heapMB: metric(m, 'JSHeapUsedSize') / 1048576,
      nodes: metric(m, 'Nodes'),
      listeners: metric(m, 'JSEventListeners')
    }
  }
  const rows = [{ lap: 0, ...(await sample()) }]
  for (let lap = 1; lap <= laps; lap += 1) {
    for (const path of route) {
      // in-app navigation, as a player clicking around (no reload)
      await page.evaluate((p) => {
        history.pushState(history.state ?? {}, '', p)
        window.dispatchEvent(new PopStateEvent('popstate', { state: history.state }))
      }, path)
      await page.waitForTimeout(700)
    }
    if (lap % 5 === 0 || lap === 1) rows.push({ lap, ...(await sample()) })
  }
  await context.close()
  return rows
}

const browser = await chromium.launch({ channel: 'msedge' })
const browserSession = await browser.newBrowserCDPSession()
const out = { base: BASE, runs: RUNS, idle: IDLE, motion: MOTION, pages: [] }

if (args.memory) {
  out.memory = await memoryWalk(browser, Number(args.memory))
  console.table(out.memory.map((r) => ({ ...r, heapMB: r.heapMB.toFixed(1) })))
} else {
  for (const name of only) {
    const runs = []
    for (let i = 0; i < RUNS; i += 1)
      runs.push(await measure(browser, browserSession, name, PAGES[name]))
    const row = { page: name }
    for (const k of Object.keys(runs[0])) if (k !== 'page') row[k] = median(runs.map((r) => r[k]))
    out.pages.push(row)
    process.stderr.write(`${name} done\n`)
  }
  const fmt = (v, d = 0) => (typeof v === 'number' ? v.toFixed(d) : v)
  console.table(
    out.pages.map((r) => ({
      page: r.page,
      fcp: fmt(r.fcp),
      lcp: fmt(r.lcp),
      cls: fmt(r.cls, 3),
      kb: fmt(r.kb),
      req: r.requests,
      tbt: fmt(r.tbt),
      heapMB: fmt(r.heapMB, 1),
      nodes: r.nodes,
      loops: r.loops,
      main: fmt(r.mainBusyPct, 1),
      style: fmt(r.styleMs),
      cpu: fmt(r.cpuPct, 1),
      fps: fmt(r.fps, 1),
      janky: r.janky,
      idleReq: r.idleRequests
    }))
  )
}
if (args.json) writeFileSync(args.json, JSON.stringify(out, null, 2))
await browser.close()
