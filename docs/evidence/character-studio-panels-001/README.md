# Character studio: a side panel that helps with each step

**Your review:**
- The right-hand panel never changed between steps.
- Some steps left large gaps or looked unrefined.

**What the screenshots showed** (`before-1920-step*.png`):
- **Same panel everywhere:** the full preview appeared on all five steps.
- **Empty gaps:** Overview and Voice left a large gap under a short form.
- **Cramped portrait:** on Appearance it sat under the form, so the page scrolled at 1080 px. At 16:10 it fell below the button bar.
- **Thin Review step:** a small form, then the publishing note as a card of its own.

## What changed

| Step | Side panel | Form |
| --- | --- | --- |
| 1 Overview | **Character concept**: who they are, then where they come from, what draws them on and what they keep close. These are read from the later steps' fields; "Not written yet — step 3" links to the step. | Unchanged. |
| 2 Appearance | **Portrait studio**: the picture large, Generate again / Import image, framing, and where it shows (card and map token). | Basics (age, race, sex on one row), Features (hair, eyes, height, build), Distinctive details. The portrait moved out of the form. |
| 3 Background & personality | **Character compass**: wants, fears, will not cross, inner tension, under pressure. | Origins, Personality, Motivations. The four deeper fields fold under "More about them · 4 of 4 written" because the compass already shows them. |
| 4 Voice | **How they sound**: their lines as speech bubbles beside their face, and "Try a situation" → **Hear a sample**. | "How Mara speaks" group. |
| 5 Review | **Character sheet** (the full preview, as before). | Gear & condition, then **Review your character**: one line per step with **Edit**, and the publishing note as a quiet line. |

**Also:**
- The header reads "Character studio · Mara Vell | Editing character".
- The step bar names every step when the column has room. Below 740 px it names only the current step.
- The side panel never grows taller than the window; it scrolls inside instead.
- "Body" is now "Build", and "Extra" is now "Marks and keepsakes".

## The voice sample

- **Endpoint:** `POST /library/writing/sample` (`application/library/writing.py` `SAMPLE_PROMPT`). It uses the library writer, gpt-6-luna.
- **Input:** the character's traits, tone, "when they care", example lines, speaking style and manner with strangers, plus a situation.
- **Output:** a 3–6 line exchange. A stranger speaks first. The character's own example lines must not be repeated word for word.
- **When it runs:** only when the player asks. Nothing is saved.

**Live (`voice-sample-1920.png`):** 1.7 s and about $0.0001 for "Hearing a distant, unexplained sound".
> A stranger: Did you hear that? It came from somewhere past the ridge.
> Mara: I heard it. Give me the rope—I'll take a look. You can stay right there and keep being sensible.

## Checks

| Width | Result |
| --- | --- |
| 1920×1080 | Steps 1, 2 and 4 fit without scrolling. Steps 3 and 5 scroll 21 px and 76 px. |
| 1440×900 | The forms scroll under the fixed button bar, and the side panel stays in view. |
| 400 | The panel stacks under the form. No sideways scroll on any step. |

**Spend:** OpenRouter about $0.0001 (10.6101 → 10.6102 of $20).
