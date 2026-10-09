# Ember Vale launcher

A terminal app that starts the whole game for you: no commands to remember.

**Start it:** double-click `Start Ember Vale.cmd` in the game folder (or run
`./start-ember-vale.sh` on macOS/Linux). The first start downloads the ready-made
launcher for your computer from the newest
[release](https://github.com/joelhenwang/ember-vale/releases/latest), checks it
against the release's `SHA256SUMS`, and keeps it in `launcher/bin/`. Nothing to
install. Add `update` (`Start Ember Vale.cmd update`, `./start-ember-vale.sh
update`) to fetch the newest launcher again.

Ready-made launchers: Windows x64, macOS (Apple silicon and Intel), Linux x64 and
arm64 (static, any distribution). Without a download (offline, another
computer type) the scripts build it from source when [Rust](https://rustup.rs) is
installed.

## What it does

1. **Gear check:** looks for Docker Desktop (installed and running), Node.js,
   the game files, your settings file, a storyteller AI key, free ports, free
   memory and the optional smart memory. Anything red can usually be fixed by
   selecting it and pressing **F**: it opens the download page, starts Docker
   Desktop, installs the game files or creates the settings file.
2. **Settings (S):** storyteller (Practice, OpenRouter or Venice), AI key
   (typed hidden, saved only in `.env`), model, fast turns, smart memory, place
   spotting, graphics card, game port, open-browser, rebuild-on-start and
   what quitting stops.
3. **Start (Enter):** `docker compose up -d` (database and game server),
   waits for the server to answer, starts smart memory (`local-models/`) if
   it's on and set up, starts the game screen (Vite) and opens the browser.
4. **While playing:** live status of every part, logs per part (**Tab**),
   **O** opens the game again, **R** restarts, **Q** quits and stops what the
   launcher started (and the server too, unless you chose to keep it warm).
5. **Backups (B, while playing):** your game (stories and pictures) is backed
   up every day into `backups/` in the game folder, and the newest 7 are kept.
   The screen lists them by local date and time, with how many stories each
   holds and its size. **N** backs up now. **Enter** puts the chosen backup
   back after asking first: it backs up the game as it is now (so the restore
   can be undone), stops the game server, restores, starts the server again
   and waits for it to answer. Each step shows in the log; if Docker isn't
   running or a step fails, the screen says which step and what was changed.

Where things are kept:

- Backend choices: the root `.env`, edited line by line so comments survive.
- Launcher choices: `launcher/launcher.toml` (ignored by git).

## Releases

`.github/workflows/launcher.yml` builds and tests the launcher on Windows, macOS
and Linux for every change under `launcher/`. Pushing a tag publishes a release
the start scripts download:

```bash
# bump version in launcher/Cargo.toml first
git tag launcher-v0.2.0 && git push origin launcher-v0.2.0
```

## Development

```bash
cargo run                      # from launcher/
cargo test                     # unit tests
cargo clippy --all-targets
SNAPSHOT_DIR=/some/dir cargo test snapshots -- --ignored   # every screen as coloured HTML
cargo test live_launch -- --ignored   # really starts the stack (memory off, port 5190)
```

Built with [ratatui](https://ratatui.rs/). The code is split by concern:

| File | Role |
| --- | --- |
| `checks.rs` | gear checks |
| `config.rs` | `.env` and `launcher.toml` |
| `services.rs` | launch, watch and stop |
| `backups.rs` | list, take and restore backups (compose `backup` service) |
| `app.rs` | state and keys |
| `ui.rs` | screens |
| `theme.rs` | palette, title and embers |
