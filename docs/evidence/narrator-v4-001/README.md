# narrator-v4-001: a guided storyteller prompt against flat prose and missing spots

**Question.** narrator.v3 is a list of grounding rules with no craft guidance
("Understatement beats invention"). On Venice it wrote record-like summaries ("Wren
attempts to communicate with Ash about…") and named a listed spot in about a third of
scenes. Does a more guided system prompt fix both without losing structural validity?

**Method.** `fixture.json`: 24 narrator user prompts the app actually sent (from
`model_call`, prompt version narrator.v3), 8 of them listing spots (from the "Inside
Corvane" story; two with the older optional wording). `backend/scripts/narrator_prompt_eval.py`
replays each prompt with only the system prompt changed and scores it the way the app
accepts narration (parse, drop recap-only beats, soften dialogue, `beats_valid`, one
repair with `repair_instruction`). "Stock phrases" counts fact-record wording in the
accepted text ("attempts to communicate", "speaks to", "brings up", "the topic",
"decides to", "perhaps", "the scene"). Each run folder holds every raw answer.

| run | model | prompt | valid (after repair) | spot named | stock phrases | words/answer | tokens in/out |
| --- | --- | --- | --- | --- | --- | --- | --- |
| run-1* | Venice | v3 | 15/24 | 4/6 | 32 | 39 | 33k/3.6k |
| run-1* | Venice | v4 draft | 6/24 | 0/0 | 0 | 52 | 44k/6.2k |
| run-2 | Venice | v3 | 22/24 (2) | 4/6 | 32 | 34 | 40k/5.4k |
| run-2 | Venice | v4 + format example | 20/24 (6) | 5/5 | 3 | 51 | 64k/7.2k |
| run-3 | Venice | v3 | 22/24 (0) | 3/6 | 38 | 39 | 37k/5.4k |
| run-3 | Venice | v4 + placeholder example | 24/24 (2) | 8/8 | 19 | 69 | 48k/4.5k |
| run-4 | Venice | v4 + record-to-beat example | 24/24 (2) | 8/8 | 4 | 72 | 50k/5.2k |
| run-5 | DeepSeek V4 Flash | v3 | 22/24 (0) | 4/6 | 8 | 64 | 36k/7.8k |
| run-5 | DeepSeek V4 Flash | v4 (run-4) | 22/24 (3) | 5/6 | 2 | 74 | 55k/7.4k |
| run-6 | Venice | v4 final | 24/24 (2) | 8/8 | 2 | 74 | 51k/5.0k |
| run-6 | DeepSeek V4 Flash | v4 (run-6) | 22/24 (1) | 6/6 | 1 | 73 | 52k/6.0k |

Run-7 adds the app's `drop_retold` step (sentences that copy the recap are cut before
storage) and counts what it cut, after a live play showed v4 re-describing a spot the
recap had just described (the whole opening beat was cut, leaving bare dialogue):

| run | model | prompt | valid (after repair) | spot named | stock phrases | retold sentences cut | words/answer | tokens in/out |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| run-7 | Venice | v3 | 22/24 (1) | 1/6 | 23 | 9 | 23 | 39k/5.1k |
| run-7 | Venice | v4 final | 24/24 (2) | 8/8 | 8 | 2 | 65 | 52k/4.6k |
| run-7 | DeepSeek V4 Flash | v3 | 22/24 (1) | 3/6 | 5 | 7 | 71 | 37k/9.2k |
| run-7 | DeepSeek V4 Flash | v4 final | 21/24 (1) | 5/5 | 1 | 2 | 60 | 56k/6.2k |

DeepSeek's one extra failure in run-7 is an invented key (`places`) and one summary
rendered as dialogue that survived the repair; run-6 had it level with v3 (22/24). A
failed narration falls back to the deterministic beats, as before.

\* run-1's harness skipped the app's recap drop, dialogue softening and repair, so it
under-counts both versions; kept as the record of the draft's format failure.

What each revision fixed:

- **Draft (run-1):** craft guidance alone made the small Venice model lose the output
  format: 9/24 answers were bare prose or restated the instructions.
- **Format first with an example (run-2):** the format came back, but the model copied
  the example's keys (`attempt:move`, `spots`) and learned that reaction keys make dialogue.
- **Placeholder example (run-3):** every answer valid; spots always named; record wording
  still in about one answer in three, since the fact lines themselves say "attempts to
  communicate".
- **A record-to-beat example (run-4):** "Record: Wren attempts to communicate with Ash;
  topic: the rocky islets. Beat: Wren leans across the table and asks Ash what waits out
  on the rocky islets." Stock wording fell from 19 to 4.
- **Summaries stay narration (run-6):** DeepSeek had turned attributed summaries into
  dialogue (3 repairs in run-5); one repair left.
- **No re-describing (run-7):** "When the recap shows the same people already at this
  spot, do not describe it again". Retold sentences fell from 9 (v3) to 2 on Venice.

The two answers no version gets right are one fixture scene whose speaker is not in its
audience (`speaker outside the audience`), in every run and both models.

Same scene, v3 then v4 (Venice):

> Wren attempts to communicate with Ash about the rocky islets south of Corvane, while
> Ash waits. Ash speaks to Wren about the rocky islets south of Corvane.

> The sun hangs low in the sky, casting long shadows across the Market square. … Wren and
> Ash stand near the Market well, their conversation from the previous night still
> lingering in the air. Wren leans in, their voice barely above a whisper, asking Ash
> about the rocky islets south of Corvane…

> Fisher waits at the Rocky islets south of Corvane.

> The rocky islets south of Corvane are bathed in the soft light of the afternoon sun,
> the waves lapping gently against the shore. Fisher stands on the shore, eyes scanning
> the horizon, waiting for something or someone.

**Costs and trade-offs.** v4's system prompt is about 600 tokens longer: prompt tokens per
call rise ~35–45 %; answers run about twice as long on Venice. Small inventions of
atmosphere remain ("the nearby baker's stall") although the prompt forbids new buildings.
OpenRouter spend for runs 5–7 was $0.022 (DeepSeek); Venice is billed separately.

**Decision.** `NARRATOR_PROMPT_VERSION = "narrator.v4"`; v3 stays on disk for replays.
