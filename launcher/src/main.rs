//! Ember Vale launcher: checks the PC, lets the player pick options, then
//! starts the game server (Docker), the optional local models and the game
//! screen (Vite), and stops them again on quit.

mod app;
mod checks;
mod config;
mod services;
mod sys;
mod theme;
mod ui;

use std::io::stdout;
use std::time::Duration;

use ratatui::crossterm::event::{
    self, DisableBracketedPaste, EnableBracketedPaste, Event, KeyEventKind,
};
use ratatui::crossterm::execute;

const FRAME: Duration = Duration::from_millis(50);

fn main() {
    let Some(root) = sys::find_root() else {
        eprintln!(
            "Couldn't find the Ember Vale folder.\n\
             Run the launcher from inside the game folder (the one with compose.yaml)."
        );
        std::process::exit(1);
    };
    let mut terminal = ratatui::init();
    let _ = execute!(stdout(), EnableBracketedPaste);
    let mut app = app::App::new(root);
    let result = (|| -> std::io::Result<()> {
        while !app.quit {
            let header = ui::header_area(terminal.size()?.into());
            app.update(header);
            terminal.draw(|frame| ui::draw(frame, &app))?;
            if event::poll(FRAME)? {
                match event::read()? {
                    Event::Key(key) if key.kind == KeyEventKind::Press => app.on_key(key),
                    Event::Paste(text) => app.on_paste(&text),
                    _ => {}
                }
            }
        }
        Ok(())
    })();
    drop(app);
    let _ = execute!(stdout(), DisableBracketedPaste);
    ratatui::restore();
    if let Err(err) = result {
        eprintln!("The launcher stopped unexpectedly: {err}");
    }
}
