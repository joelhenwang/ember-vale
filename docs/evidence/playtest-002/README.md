# Playtest 002 — continuity changes (0b061b0), same setup as 001

Story `876a824b`, Wren and Ash at the Hearth, watcher mode,
`deepseek/deepseek-v4-flash-0731`, reasoning off, 10 beats through autoplay
with scripted presence. Spend ≈ $0.02. Full chronicle in `chronicle.json`.

## Compared with playtest-001

| | 001 | 002 |
| --- | --- | --- |
| Opening | three beats of "what brings you here?" | beat 1 already acts on a director hook (late carts at the Market) |
| Repeated questions | yes | none |
| Director | always `noop` | two hooks ("The Market's First Light", "Evening lantern-lighting at Hearth") |
| Stored intentions | — | Wren: "Stay with Ash and head to the Market together to check on the carts." Ash: "Wait for Wren at the Market … before heading to the Hearth." |
| Agreement remembered | no | beat 9: "Ash, you said you'd come with me to the Market" |
| Place in narration | drifted | names the real place |
| Repairs | 1 / 58 calls | 4 / 57 (3 director: payload nested under `propose_hook`; fixed after this run) |
| Beat time | 6–72 s | 4–46 s |

## Still wrong

1. **Moving together fails.** Decisions are simultaneous: when both decide
   to join the other, each walks to where the other *was* and they swap
   places (beat 4 "Wren moves. Ash moves."; beat 6 swaps back). They end
   apart, each intention unfulfilled. Needs an accompany/follow action or
   a meet-up rule, not prompt wording.
2. **Thin narration of movement-only beats** ("Wren moves. Ash moves.").
3. **Narrator vocabulary leak:** "An audience member watches the exchange."
4. **Pronouns** still vary (no card field yet).
