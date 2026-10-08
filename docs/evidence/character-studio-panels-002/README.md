# Character studio: both columns start and end together

**Your review:** on every step there was unused space under the side panel. The panel began beside the page title, stopped at its own height and stuck while you scrolled, while the form ran on below it. Your designer moved the title and the step bar above both columns.

## Changes

**Layout**
- **Full-width header:** the title, its "Character studio" label and the step bar now run across the page. Only an existing character shows "Editing character"; the duplicate "New character" tag is gone.
- **Step bar:** its links share the leftover width, so it spans the page.
- **Equal columns:** the form and the side panel start on the same line and stretch to the same height. The last card on the form side grows to match, so neither column leaves a gap.
- **Panel behaviour:** the side panel no longer sticks or caps its height. When it is the taller column, the page scrolls.

**Wording and empty states**
- **Voice, before any sample:**
  - A dashed box reads "Your sample dialogue will appear here."
  - The button is now "Generate a sample".
  - An unnamed character shows "Add a name to hear them in context".
- **Review sheet:** sections with nothing in them yet (Appearance, Background & personality, Voice, Gear & condition) are listed with "Nothing written yet." An empty sheet no longer looks broken.
- **Overview hint:** "Suggestions wait for your review. Only empty fields are filled."
- **Compass rows:** slightly tighter. The situation picker wraps rather than cutting its text off.

## Checks

| Width | Character | Result |
| --- | --- | --- |
| 1920×1080 | New (empty) | Steps 1–4 fit without scrolling. Review scrolls 56 px. |
| 1920×1080 | Mara | Columns end together. When the side panel is the longer one (compass, sheet), the page scrolls by up to 172 px. |
| 1440×900 | Both | The forms scroll under the fixed button bar. |

No step scrolls sideways at any width.
