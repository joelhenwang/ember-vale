# New Story wizard, after your designer's mockups

**Before** (`before-step*.png`): a banner ("Shape your next tale") and a dot stepper over one wide panel per step. Worlds were a long list, play mode and storyteller were bare forms, Review was a plain list, and the cast step's "Selected" panel stopped short of the grid.

**Now** (`after-1920-step1…6.png`): each step has its own heading ("Choose a world", "Choose your cast", "How do you want to play?", "Name your story and set its mood", "Choose your storyteller", "Ready to begin?"), the steps run across the page, and the step sits beside a panel showing what it adds up to. Both columns end together.

| Step | Left | Right |
| --- | --- | --- |
| World | World cards with their pictures ("No picture yet" when there is none), search, Create a world | World preview: picture, places count, description, place chips, Edit this world |
| Characters | Search, filters, cast cards (unchanged) | Your cast: portrait, role, Starts at, Edit character, Remove |
| Play mode | Observer / Player cards, then "Who will you play?" with portraits | Your role: the world picture with your character on it, chips, who else is in the story |
| Story | Title; tone in your own words or one of three starting points | Story preview: title, world, who you play, cast |
| Storyteller | Use the app's storyteller (Default, names it: Venice) or choose a provider profile; Advanced details folded | Your storyteller, and the story so far |
| Review | Your story setup: one row per step with Edit | Story preview |

The footer names where you are ("The Saltreach · 16 places", "2 characters selected", the title) and its main button says where it goes ("Continue to Play mode"). Step labels are now "Play mode" and "Storyteller".

What did not change: the draft, recovery, revision pinning and validation logic; the steps still save as before.

Also fixed while testing: the banner's character picture kept the first character after you chose another (the fallback picture reads once); it now follows your choice.

Checked at 1920×1080 (steps 1 and 3–6 fit; the cast grid scrolls), 1366×768 (`after-1366-step3.png`) and 400 px (`after-phone-step3.png`, the panel stacks under the step); nothing scrolls sideways.
