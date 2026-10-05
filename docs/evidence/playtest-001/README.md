# Playtest 001 — 10 live beats through server-side autoplay

Story `90c75e0f`, Wren and Ash both starting at the Hearth, watcher mode,
`deepseek/deepseek-v4-flash-0731` with reasoning off. Beats 1–5 on e95577a /
4d85fe7, beat 5 (resumed) to 10 on a9ce935. Spend ≈ $0.015. Full chronicle in
`chronicle.json`.

## Engine

| | |
| --- | --- |
| Beat wall time | 72, 27, 44, 22 s (beats 1–4); 6–49 s (6–10) |
| Model calls | 58, of which 1 repair (narrator: dialogue did not quote cited speech) |
| Failures | beat 5: resolver invented a move `0000…` → `1111…`; the commit hit a foreign key. Fixed in a9ce935 (move endpoints from the attempt; unknown places go to repair). Autoplay paused with the reason and later resumed the open beat. |
| Autoplay | stopped at the beat limit; first attempt paused after 1 beat because the automated browser tab was hidden (presence is only sent while the page is visible) |

Repairs fell from 4 per 23 calls (beat-latency-001) to 1 per 58 after e95577a.

## Story quality

1. **No conversational memory.** Beats 1–3 replay the same opening ("what
   brings you here?"); beat 3's narration calls it "a first attempt at
   conversation". Decision context holds only *attempt* summaries — never
   the replies (reaction speech) — unordered and undated; memories mostly
   duplicate the actor's own lines.
2. **No shared intent.** They agree to walk to the market together; Ash goes
   alone (beat 5), Wren leaves (6), returns (9), and they end apart. There
   is no "accompany/follow" action and no record of the plan.
3. **Idle when apart.** Goals and relationships are empty and the prompt
   ends "When in doubt, wait.": beats 7, 8, 10 are both characters waiting.
4. **Bland or broken narration for solitary beats.** "Wren waits." Beat 5's
   narration carries a stray "Appreciated." and "Ash moves."
5. **Continuity drift.** Pronouns vary (Ash: him/their; cards carry none);
   beat 2 sets the scene "in the stall's shade" while both are at the Hearth
   (the narrator is not told the place).
6. **The director never acts.** Every run: `noop`, "nothing pressing".
