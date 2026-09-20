# Start here: instructions for the new Ember Vale coding agent

You are working in `joelhenwang/ember-vale`. Read `Ember_Vale_Product_and_Backend_Plan.md` completely before implementation. This is the destination application. Keep its existing Vue styling, views, components, navigation and branding as the baseline.

The project is a persistent LLM-driven fantasy storytelling RPG/world simulator with Player, Observer, Director and God modes. The goal is to make this frontend work through a reliable backend, not to move it into PixelSaga or redesign it.

Use `joelhenwang/pixelsaga` as a read-only backend reference. Prefer reusing its coherent Python/FastAPI/Postgres engine where it passes the new application's acceptance tests. Do not import its frontend, CSS, router, App, project-wide instructions or conflicting layout decisions. Do not rewrite a working engine merely to change names, and do not inherit known demo/missing behavior as production behavior.

First:

1. Read the actual Ember Vale repository instructions and inspect current work/HEAD. Preserve all user changes.
2. Capture individual-page baseline screenshots and inventory the existing demo state, fake save/probe/generation timers, dead routes and contaminated screenshot-derived artwork.
3. Establish an isolated backend/database and generated API client, then connect the existing UI through small typed composables/props/events.
4. Prove a complete journey early: create a real story with Wren/Ash and Hearth/Market, advance one beat, leave, reload and resume the same state. Do not redesign the pages while doing this.
5. Implement the remaining plan packet by packet, preserving existing presentation and replacing fixtures with real persistence, permissions and generation.

Keep reusable presets separate from story state; cast selection precedes Player selection; selected revisions stay pinned. LLMs propose actions/text, validated backend commands own canon. Images never create inventory or injuries. Generate/approve a profile first, then use the actual profile image as reference for a full-body render. Runtime outfit/physical changes affect body inputs without silently replacing identity.

Use real provider results. No success from timers, nonempty endpoint fields, JSON snapshots in memory or cache-busting a placeholder image. Missing credentials/capabilities are reported honestly while independent work continues. No generation on component mount. No destructive resets of existing databases.

Do not treat PixelSaga's old static-mock gate as inherited policy. Existing Ember Vale pages are the selected visual base; follow any actual destination instructions and approvals in this session. Routine implementation decisions do not need repeated permission requests.

Finish each packet with actual checks and a short evidence report. Final delivery includes source/migrations/generated contracts, real setup/run instructions, tests and screenshots, plus separate lists of implemented, verified and externally blocked features. A screenshot alone is not completion.
