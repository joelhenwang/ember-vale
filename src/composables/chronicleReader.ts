import type { Ref } from 'vue'
import type { ChronicleEntry, ChronicleResponse } from '../../content/clients/worldsim'
import { mergeChronicle } from '../game/observatory'

/** Events read per chronicle page when a long story opens newest-first. */
export const CHRONICLE_TAIL = 100

type Fetch = (after: number, limit?: number) => Promise<ChronicleResponse>

/** Backfill yields between pages so it never crowds out the screen's own requests. */
const pause = (): Promise<void> => new Promise((done) => setTimeout(done, 50))

/**
 * Reads a story's chronicle into `entries`, shared by Adventure and Watch.
 *
 * A long story opens on its newest page: one tiny probe learns the newest
 * sequence, the last CHRONICLE_TAIL events are read, and older pages fill
 * in behind, newest first, while the player reads. Before, a 9,000-event
 * story read oldest-first, 50 a page, 20 pages a round, and needed ~9
 * rounds before the newest turn showed (perf-frontend-001). Later reads go
 * forward from the cursor, re-reading from the first scene still waiting
 * for its words so late narration replaces the placeholder.
 */
export function chronicleReader(
  fetch: Fetch,
  entries: Ref<ChronicleEntry[]>,
  alive: () => boolean = () => true
) {
  let cursor = 0
  /** Entries above this source sequence are loaded; below it, not yet. */
  let floor = 0
  /** Bumped by reset(): a backfill from before stops. */
  let generation = 0
  /** The newest-first probe runs once per opening, not on every poll. */
  let probed = false

  async function forward(from: number, limit?: number): Promise<void> {
    let after = from
    for (let page = 0; page < 20; page++) {
      const res = await fetch(after, limit)
      entries.value = mergeChronicle(entries.value, res.entries ?? [])
      after = res.next_after
      cursor = Math.max(cursor, after)
      if (!res.has_more) return
    }
  }

  async function backfill(gen: number): Promise<void> {
    while (floor > 0 && gen === generation && alive()) {
      const from = Math.max(0, floor - CHRONICLE_TAIL)
      try {
        const res = await fetch(from, CHRONICLE_TAIL)
        if (gen !== generation || !alive()) return
        entries.value = mergeChronicle(entries.value, res.entries ?? [])
      } catch {
        return // the next reset() starts over; the newest pages are already shown
      }
      floor = from
      await pause()
    }
  }

  async function read(): Promise<void> {
    if (!probed) {
      probed = true
      const probe = await fetch(0, 1)
      if (probe.watermark > CHRONICLE_TAIL) {
        floor = probe.watermark - CHRONICLE_TAIL
        await forward(floor, CHRONICLE_TAIL)
        void backfill(generation)
        return
      }
      // a short story: the probe's page counts, and reading goes on from it
      entries.value = mergeChronicle(entries.value, probe.entries ?? [])
      cursor = Math.max(cursor, probe.next_after)
      if (!probe.has_more) return
    }
    const pending = entries.value.find((e) => e.scene_id && !e.text)
    await forward(pending ? Math.min(cursor, pending.sequence - 1) : cursor)
  }

  function reset(): void {
    cursor = 0
    floor = 0
    probed = false
    generation++
  }

  return { read, reset }
}
