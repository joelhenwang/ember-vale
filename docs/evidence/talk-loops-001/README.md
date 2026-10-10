# talk-loops-001: why characters talked in circles, and the fix

- **What happened.** In watched-party-001 run 3 (Venice), Wren and Ash agreed eight turns running to
  "ask the townsfolk about the empty stalls". No townsfolk were there to ask.
- **Not a detection failure.** The repeat guard caught the line almost every turn, for both speakers
  (the retry prompts are in `model_call`). Its word overlap scored 0.75 against a 0.6 threshold.
- **The failure was enforcement.** Told "you already said this", Venice said it again, and the second
  answer stood by design (repeat-guard-001).
- **The fix (`9a7a7b0`).**
  - `repeats()` counts every answered exchange a line repeats. Two or more is a loop (`LOOP_TIMES`),
    and the retry note then says not to talk this turn: do it, look around, or turn to something else.
  - A decision that still repeats after its retry goes unsaid, and the character looks around instead.
  - Replies keep their single retry.
- **Measured.** scorecard-049 → scorecard-050 on Venice: repeated lines 8/33/12% → 0/0/0%, all goals
  passing.
