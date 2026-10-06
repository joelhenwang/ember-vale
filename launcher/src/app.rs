//! Launcher state and what each key does on each screen.

use std::collections::VecDeque;
use std::path::PathBuf;
use std::sync::Arc;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::mpsc::{Receiver, Sender, channel};
use std::thread::{self, JoinHandle};
use std::time::{Duration, Instant};

use ratatui::crossterm::event::{KeyCode, KeyEvent, KeyModifiers};

use crate::checks::{self, CheckId, Fix, Outcome, Status};
use crate::config::{self, EnvFile, Prefs, Storyteller};
use crate::services::{self, Health, Msg, Owned, Plan, Source, Step, StepState};
use crate::sys;
use crate::theme::Embers;

const LOG_LINES: usize = 2000;
const RECHECK_EVERY: Duration = Duration::from_secs(5);
const TOAST_FOR: Duration = Duration::from_secs(5);
/// Ports the game's own parts already use.
const RESERVED_PORTS: [u16; 3] = [5433, 8101, config::LOCAL_MODELS_PORT];

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Screen {
    Checks,
    Settings,
    Launch,
    Playing,
    Closing,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Tone {
    Good,
    Info,
    Bad,
}

/// One line of the settings screen.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Item {
    Storyteller,
    Key,
    Model,
    FastTurns,
    SmartMemory,
    PlaceSpotting,
    GraphicsCard,
    Port,
    OpenBrowser,
    Rebuild,
    StopOnQuit,
}

pub const SECTIONS: [(&str, &[Item]); 3] = [
    ("Storyteller", &[Item::Storyteller, Item::Key, Item::Model]),
    (
        "Gameplay",
        &[
            Item::FastTurns,
            Item::SmartMemory,
            Item::PlaceSpotting,
            Item::GraphicsCard,
        ],
    ),
    (
        "Launching",
        &[
            Item::Port,
            Item::OpenBrowser,
            Item::Rebuild,
            Item::StopOnQuit,
        ],
    ),
];

impl Item {
    pub fn all() -> Vec<Item> {
        SECTIONS
            .iter()
            .flat_map(|(_, items)| items.iter().copied())
            .collect()
    }

    pub fn label(self) -> &'static str {
        match self {
            Item::Storyteller => "Storyteller AI",
            Item::Key => "AI account key",
            Item::Model => "AI model",
            Item::FastTurns => "Fast turns",
            Item::SmartMemory => "Smart memory",
            Item::PlaceSpotting => "Place spotting",
            Item::GraphicsCard => "Use graphics card",
            Item::Port => "Game screen port",
            Item::OpenBrowser => "Open browser when ready",
            Item::Rebuild => "Update game server on start",
            Item::StopOnQuit => "When I quit",
        }
    }

    pub fn about(self) -> &'static str {
        match self {
            Item::Storyteller => {
                "Who writes your story. Practice is free and offline but scripted. OpenRouter \
                 and Venice are AI services: create an account on their website, add a little \
                 credit, and paste your key below. A typical evening of play costs cents."
            }
            Item::Key => {
                "Your secret key from the storyteller's website (OpenRouter: openrouter.ai/keys). \
                 It is saved only in the .env file on this PC and never shown again here."
            }
            Item::Model => {
                "Which AI model plays the characters. Leave it as it is unless you know you \
                 want another one (for example deepseek/deepseek-v4-flash on OpenRouter)."
            }
            Item::FastTurns => {
                "Your turn comes back as soon as the world has moved, and the narration finishes \
                 writing itself a few seconds later. Makes the game feel much snappier."
            }
            Item::SmartMemory => {
                "A small AI on your own PC that helps characters remember what matters, instead \
                 of only what happened last. Uses about 1-2 GB of memory while playing."
            }
            Item::PlaceSpotting => {
                "Part of smart memory: notices when characters talk about places that aren't on \
                 the map yet, so the world can grow. Turn it off if your PC is low on memory."
            }
            Item::GraphicsCard => {
                "Experimental: lets smart memory use your graphics chip as well. Leave it off \
                 unless memory feels slow; some graphics drivers misbehave with it."
            }
            Item::Port => {
                "The number in the game's web address (http://localhost:PORT). Change it only if \
                 another program already uses it."
            }
            Item::OpenBrowser => {
                "Opens the game in your web browser as soon as everything is ready."
            }
            Item::Rebuild => {
                "Rebuilds the game server before starting. Turn it on once after updating the \
                 game; it takes a few minutes, so it's off by default."
            }
            Item::StopOnQuit => {
                "Stop everything frees your PC's memory when you're done. Keep the server \
                 warm makes the next start faster, but it keeps running in the background."
            }
        }
    }

    fn edits_text(self) -> bool {
        matches!(self, Item::Key | Item::Model | Item::Port)
    }
}

pub struct Toast {
    pub text: String,
    pub tone: Tone,
    at: Instant,
}

pub struct App {
    pub root: PathBuf,
    pub prefs: Prefs,
    pub env: EnvFile,
    pub screen: Screen,
    tx: Sender<Msg>,
    rx: Receiver<Msg>,
    pub tick: u64,
    pub embers: Embers,
    pub quit: bool,
    pub toast: Option<Toast>,

    pub checks: Vec<(CheckId, Outcome)>,
    pub checking: bool,
    last_check: Instant,
    pub check_sel: usize,
    pub fixing: Option<String>,

    pub setting_sel: usize,
    pub editing: Option<String>,

    pub steps: Vec<(Step, StepState, String)>,
    pub launch_error: Option<String>,
    pub launching: bool,
    launch_thread: Option<JoinHandle<()>>,
    pub plan: Option<Plan>,
    owned: Owned,
    watch_stop: Arc<AtomicBool>,
    pub health: Health,

    pub logs: VecDeque<(Source, String)>,
    pub log_filter: Option<Source>,
    pub log_full: bool,
    pub log_scroll: usize,
}

impl App {
    pub fn new(root: PathBuf) -> Self {
        let (tx, rx) = channel();
        let mut app = Self {
            prefs: Prefs::load(&root),
            env: EnvFile::load(&root),
            root,
            screen: Screen::Checks,
            tx,
            rx,
            tick: 0,
            embers: Embers::default(),
            quit: false,
            toast: None,
            checks: CheckId::ALL
                .iter()
                .map(|id| (*id, Outcome::waiting()))
                .collect(),
            checking: false,
            last_check: Instant::now(),
            check_sel: 0,
            fixing: None,
            setting_sel: 0,
            editing: None,
            steps: vec![],
            launch_error: None,
            launching: false,
            launch_thread: None,
            plan: None,
            owned: Owned::default(),
            watch_stop: Arc::new(AtomicBool::new(false)),
            health: Health::default(),
            logs: VecDeque::new(),
            log_filter: None,
            log_full: false,
            log_scroll: 0,
        };
        app.recheck();
        app
    }

    // ---- background work -------------------------------------------------

    fn recheck(&mut self) {
        if self.checking {
            return;
        }
        self.checking = true;
        self.env = EnvFile::load(&self.root);
        let (root, prefs, tx) = (self.root.clone(), self.prefs.clone(), self.tx.clone());
        thread::spawn(move || {
            checks::run_all(&root, &prefs, |id, outcome| {
                let _ = tx.send(Msg::Check(id, outcome));
            });
            let _ = tx.send(Msg::ChecksDone);
        });
    }

    /// Applies everything background threads reported, then ticks animations.
    pub fn update(&mut self, header: ratatui::layout::Rect) {
        self.tick = self.tick.wrapping_add(1);
        self.embers.tick(header);
        while let Ok(msg) = self.rx.try_recv() {
            self.apply(msg);
        }
        if self
            .toast
            .as_ref()
            .is_some_and(|t| t.at.elapsed() > TOAST_FOR)
        {
            self.toast = None;
        }
        let needs_attention = self.checks.iter().any(|(_, o)| o.status == Status::Problem);
        if self.screen == Screen::Checks
            && needs_attention
            && self.fixing.is_none()
            && !self.checking
            && self.last_check.elapsed() > RECHECK_EVERY
        {
            self.recheck();
        }
    }

    fn apply(&mut self, msg: Msg) {
        match msg {
            Msg::Check(id, outcome) => {
                if let Some(slot) = self.checks.iter_mut().find(|(c, _)| *c == id) {
                    slot.1 = outcome;
                }
            }
            Msg::ChecksDone => {
                self.checking = false;
                self.last_check = Instant::now();
            }
            Msg::Log(source, line) => self.log(source, line),
            Msg::Step(step, state, detail) => {
                if let Some(slot) = self.steps.iter_mut().find(|(s, _, _)| *s == step) {
                    slot.1 = state;
                    slot.2 = detail;
                }
            }
            Msg::Launched(result) => {
                self.launching = false;
                match result {
                    Ok(()) => {
                        self.screen = Screen::Playing;
                        self.start_watching();
                    }
                    Err(why) => {
                        self.log(Source::Launcher, why.clone());
                        self.launch_error = Some(why);
                    }
                }
            }
            Msg::Fixed(result) => {
                self.fixing = None;
                match result {
                    Ok(text) => self.say(text, Tone::Good),
                    Err(text) => self.say(text, Tone::Bad),
                }
                self.recheck();
            }
            Msg::Health(health) => self.health = health,
            Msg::Stopped => self.quit = true,
        }
    }

    fn log(&mut self, source: Source, line: String) {
        if self.logs.len() >= LOG_LINES {
            self.logs.pop_front();
        }
        self.logs.push_back((source, line));
    }

    fn say(&mut self, text: impl Into<String>, tone: Tone) {
        self.toast = Some(Toast {
            text: text.into(),
            tone,
            at: Instant::now(),
        });
    }

    pub fn blocking_problems(&self) -> usize {
        self.checks
            .iter()
            .filter(|(_, o)| o.status == Status::Problem && o.blocking)
            .count()
    }

    pub fn notes(&self) -> usize {
        self.checks
            .iter()
            .filter(|(_, o)| o.status == Status::Note)
            .count()
    }

    pub fn visible_logs(&self) -> Vec<&(Source, String)> {
        self.logs
            .iter()
            .filter(|(s, _)| self.log_filter.is_none_or(|f| f == *s))
            .collect()
    }

    // ---- keys --------------------------------------------------------------

    pub fn on_key(&mut self, key: KeyEvent) {
        let ctrl_c =
            key.modifiers.contains(KeyModifiers::CONTROL) && key.code == KeyCode::Char('c');
        if ctrl_c {
            return self.leave();
        }
        if self.editing.is_some() {
            return self.on_edit_key(key);
        }
        match self.screen {
            Screen::Checks => self.on_checks_key(key.code),
            Screen::Settings => self.on_settings_key(key.code),
            Screen::Launch | Screen::Playing => self.on_running_key(key.code),
            Screen::Closing => {}
        }
    }

    pub fn on_paste(&mut self, text: &str) {
        if let Some(buffer) = self.editing.as_mut() {
            buffer.push_str(text.trim());
        }
    }

    fn on_checks_key(&mut self, code: KeyCode) {
        match code {
            KeyCode::Up | KeyCode::Char('k') => self.check_sel = self.check_sel.saturating_sub(1),
            KeyCode::Down | KeyCode::Char('j') => {
                self.check_sel = (self.check_sel + 1).min(self.checks.len() - 1)
            }
            KeyCode::Enter => self.start(),
            KeyCode::Char('s' | 'S') => self.open_settings(None),
            KeyCode::Char('f' | 'F') => self.fix_selected(),
            KeyCode::Char('r' | 'R') => {
                self.recheck();
                self.say("Checking everything again…", Tone::Info);
            }
            KeyCode::Char('q' | 'Q') => self.leave(),
            _ => {}
        }
    }

    fn on_settings_key(&mut self, code: KeyCode) {
        let items = Item::all();
        let item = items[self.setting_sel];
        match code {
            KeyCode::Up | KeyCode::Char('k') => {
                self.setting_sel = self.setting_sel.saturating_sub(1)
            }
            KeyCode::Down | KeyCode::Char('j') => {
                self.setting_sel = (self.setting_sel + 1).min(items.len() - 1)
            }
            KeyCode::Left | KeyCode::Char('h') => self.change(item, -1),
            KeyCode::Right | KeyCode::Char('l') | KeyCode::Char(' ') => self.change(item, 1),
            KeyCode::Enter => {
                if item.edits_text() {
                    self.begin_edit(item);
                } else {
                    self.change(item, 1);
                }
            }
            KeyCode::Esc | KeyCode::Char('s' | 'S' | 'b' | 'B') => {
                self.screen = Screen::Checks;
                self.recheck();
            }
            KeyCode::Char('q' | 'Q') => self.leave(),
            _ => {}
        }
    }

    fn on_running_key(&mut self, code: KeyCode) {
        let failed = self.launch_error.is_some();
        match code {
            KeyCode::Char('o' | 'O') if self.screen == Screen::Playing => {
                if let Some(plan) = &self.plan {
                    sys::open_url(&plan.game_url());
                    self.say("Opened the game in your browser.", Tone::Good);
                }
            }
            KeyCode::Char('l' | 'L') => self.log_full = !self.log_full,
            KeyCode::Tab => {
                let order = [
                    None,
                    Some(Source::Server),
                    Some(Source::Memory),
                    Some(Source::Screen),
                    Some(Source::Launcher),
                ];
                let at = order
                    .iter()
                    .position(|f| *f == self.log_filter)
                    .unwrap_or(0);
                self.log_filter = order[(at + 1) % order.len()];
                self.log_scroll = 0;
            }
            KeyCode::Up => self.log_scroll = self.log_scroll.saturating_add(1),
            KeyCode::Down => self.log_scroll = self.log_scroll.saturating_sub(1),
            KeyCode::PageUp => self.log_scroll = self.log_scroll.saturating_add(10),
            KeyCode::PageDown => self.log_scroll = self.log_scroll.saturating_sub(10),
            KeyCode::End => self.log_scroll = 0,
            KeyCode::Char('r' | 'R') if failed || self.screen == Screen::Playing => {
                self.stop_owned();
                self.start();
            }
            KeyCode::Char('b' | 'B') if failed => {
                self.stop_owned();
                self.screen = Screen::Checks;
                self.recheck();
            }
            KeyCode::Char('q' | 'Q') | KeyCode::Esc => self.leave(),
            _ => {}
        }
    }

    // ---- settings ----------------------------------------------------------

    fn open_settings(&mut self, focus: Option<Item>) {
        self.env = EnvFile::load(&self.root);
        if let Some(item) = focus {
            self.setting_sel = Item::all().iter().position(|i| *i == item).unwrap_or(0);
        }
        self.screen = Screen::Settings;
    }

    /// Whether an item can be changed right now (and why not).
    pub fn disabled(&self, item: Item) -> Option<&'static str> {
        let practice = self.env.storyteller() == Storyteller::Practice;
        match item {
            Item::Key | Item::Model if practice => Some("not needed in Practice"),
            Item::PlaceSpotting | Item::GraphicsCard if !self.prefs.smart_memory => {
                Some("needs smart memory")
            }
            _ if !self.env.exists
                && matches!(
                    item,
                    Item::Storyteller | Item::Key | Item::Model | Item::FastTurns
                ) =>
            {
                Some("create the settings file first")
            }
            _ => None,
        }
    }

    fn change(&mut self, item: Item, direction: i32) {
        if let Some(why) = self.disabled(item) {
            return self.say(format!("{} is {why}.", item.label()), Tone::Info);
        }
        match item {
            Item::Storyteller => {
                let all = Storyteller::ALL;
                let at = all
                    .iter()
                    .position(|s| *s == self.env.storyteller())
                    .unwrap_or(0) as i32;
                let next = all[(at + direction).rem_euclid(all.len() as i32) as usize];
                self.env.set(config::PROFILE, next.profile());
                self.save_env();
            }
            Item::FastTurns => {
                let on = self
                    .env
                    .get(config::FAST_TURNS)
                    .is_some_and(|v| v == "true");
                self.env
                    .set(config::FAST_TURNS, if on { "false" } else { "true" });
                self.save_env();
            }
            Item::Key | Item::Model | Item::Port => self.begin_edit(item),
            _ => {
                let prefs = &mut self.prefs;
                let flag = match item {
                    Item::SmartMemory => &mut prefs.smart_memory,
                    Item::PlaceSpotting => &mut prefs.place_spotting,
                    Item::GraphicsCard => &mut prefs.graphics_card,
                    Item::OpenBrowser => &mut prefs.open_browser,
                    Item::Rebuild => &mut prefs.rebuild,
                    _ => &mut prefs.stop_on_quit,
                };
                *flag = !*flag;
                self.save_prefs();
            }
        }
    }

    fn begin_edit(&mut self, item: Item) {
        if let Some(why) = self.disabled(item) {
            return self.say(format!("{} is {why}.", item.label()), Tone::Info);
        }
        let teller = self.env.storyteller();
        self.editing = Some(match item {
            Item::Model => teller
                .model_name()
                .and_then(|k| self.env.get(k))
                .unwrap_or_default(),
            Item::Port => self.prefs.game_port.to_string(),
            _ => String::new(), // keys are never shown back
        });
    }

    fn on_edit_key(&mut self, key: KeyEvent) {
        let Some(buffer) = self.editing.as_mut() else {
            return;
        };
        match key.code {
            KeyCode::Char(c) => buffer.push(c),
            KeyCode::Backspace => {
                buffer.pop();
            }
            KeyCode::Esc => self.editing = None,
            KeyCode::Enter => {
                let value = buffer.trim().to_string();
                self.editing = None;
                self.commit_edit(Item::all()[self.setting_sel], value);
            }
            _ => {}
        }
    }

    fn commit_edit(&mut self, item: Item, value: String) {
        let teller = self.env.storyteller();
        match item {
            Item::Key => {
                if value.is_empty() {
                    return self.say("Nothing pasted, so your key is unchanged.", Tone::Info);
                }
                if let Some(name) = teller.key_name() {
                    self.env.set(name, &value);
                    self.save_env();
                }
            }
            Item::Model => {
                if let Some(name) = teller.model_name().filter(|_| !value.is_empty()) {
                    self.env.set(name, &value);
                    self.save_env();
                }
            }
            Item::Port => match value.parse::<u16>() {
                Ok(port) if port >= 1024 && !RESERVED_PORTS.contains(&port) => {
                    self.prefs.game_port = port;
                    self.save_prefs();
                }
                _ => self.say(
                    "Pick a number between 1024 and 65535 that the game doesn't already use.",
                    Tone::Bad,
                ),
            },
            _ => {}
        }
    }

    fn save_env(&mut self) {
        match self.env.save() {
            Ok(()) => self.say("Saved. Takes effect the next time you start.", Tone::Good),
            Err(err) => self.say(format!("Couldn't save the settings file: {err}"), Tone::Bad),
        }
    }

    fn save_prefs(&mut self) {
        match self.prefs.save(&self.root) {
            Ok(()) => self.say("Saved.", Tone::Good),
            Err(err) => self.say(format!("Couldn't save launcher choices: {err}"), Tone::Bad),
        }
    }

    // ---- fixes -------------------------------------------------------------

    fn fix_selected(&mut self) {
        let (id, outcome) = self.checks[self.check_sel].clone();
        let Some(fix) = outcome.fix else {
            return self.say("Nothing to fix here automatically.", Tone::Info);
        };
        if self.fixing.is_some() {
            return self.say("One moment, still busy with the last fix.", Tone::Info);
        }
        match fix {
            Fix::OpenPage(url) => {
                sys::open_url(url);
                self.say(
                    "Opened the download page. Check again (R) once it's installed.",
                    Tone::Info,
                );
            }
            Fix::StartDocker(app) => {
                if sys::start_docker_desktop(&app) {
                    self.say(
                        "Docker Desktop is starting. This takes a minute; I'll keep checking.",
                        Tone::Info,
                    );
                } else {
                    self.say(
                        "Couldn't start Docker Desktop. Please open it from the Start menu.",
                        Tone::Bad,
                    );
                }
            }
            Fix::CreateSettings => match EnvFile::create_from_example(&self.root) {
                Ok(env) => {
                    self.env = env;
                    self.say("Created your settings file.", Tone::Good);
                    self.recheck();
                }
                Err(err) => self.say(format!("Couldn't create it: {err}"), Tone::Bad),
            },
            Fix::InstallGameFiles => self.install_game_files(),
            Fix::OpenSettings => {
                let focus = match id {
                    CheckId::Ports => Item::Port,
                    CheckId::Memory => Item::PlaceSpotting,
                    CheckId::SmartMemory => Item::SmartMemory,
                    _ => Item::Storyteller,
                };
                self.open_settings(Some(focus));
            }
        }
    }

    fn install_game_files(&mut self) {
        self.fixing = Some("Installing the game files…".into());
        let (root, tx) = (self.root.clone(), self.tx.clone());
        thread::spawn(move || {
            let mut cmd = sys::command(sys::npm());
            cmd.current_dir(&root)
                .args(["install", "--no-fund", "--no-audit"]);
            let (ok, out) = sys::run(&mut cmd, Duration::from_secs(900));
            for line in out.lines().filter(|l| !l.trim().is_empty()) {
                let _ = tx.send(Msg::Log(Source::Launcher, sys::strip_ansi(line)));
            }
            let _ = tx.send(Msg::Fixed(if ok {
                Ok("Game files installed.".into())
            } else {
                Err("Installing failed. Check your internet connection and try again.".into())
            }));
        });
    }

    // ---- launching and stopping -------------------------------------------

    fn start(&mut self) {
        if self.checking && self.screen == Screen::Checks {
            return self.say("Still checking, one moment…", Tone::Info);
        }
        if self.blocking_problems() > 0 {
            return self.say(
                "Fix the red items first (select one and press F).",
                Tone::Bad,
            );
        }
        self.env = EnvFile::load(&self.root);
        self.env.sync_with(&self.prefs);
        if let Err(err) = self.env.save() {
            return self.say(
                format!("Couldn't update the settings file: {err}"),
                Tone::Bad,
            );
        }
        let plan = Plan {
            root: self.root.clone(),
            prefs: self.prefs.clone(),
            api_port: self.env.api_port(),
            db_port: self.env.db_port(),
            cancel: Arc::new(AtomicBool::new(false)),
        };
        self.steps = Step::ALL
            .iter()
            .map(|s| (*s, StepState::Waiting, String::new()))
            .collect();
        self.launch_error = None;
        self.launching = true;
        self.screen = Screen::Launch;
        self.log(Source::Launcher, "Lighting the hearth…".into());
        let (tx, owned, run) = (self.tx.clone(), self.owned.clone(), plan.clone());
        self.launch_thread = Some(thread::spawn(move || services::launch(run, tx, owned)));
        self.plan = Some(plan);
    }

    fn start_watching(&mut self) {
        self.watch_stop.store(true, Ordering::Relaxed);
        self.watch_stop = Arc::new(AtomicBool::new(false));
        if let Some(plan) = self.plan.clone() {
            services::watch(
                plan,
                self.tx.clone(),
                self.owned.clone(),
                self.watch_stop.clone(),
            );
        }
    }

    fn stop_owned(&mut self) {
        self.watch_stop.store(true, Ordering::Relaxed);
        if let Some(plan) = &self.plan {
            plan.cancel.store(true, Ordering::Relaxed);
        }
        if let Some(handle) = self.launch_thread.take() {
            let _ = handle.join();
        }
        self.owned.stop(None);
        self.health = Health::default();
    }

    /// Quit: right away when nothing runs, otherwise via the closing screen.
    fn leave(&mut self) {
        if matches!(self.screen, Screen::Checks | Screen::Settings)
            || self.screen == Screen::Closing
        {
            if self.screen != Screen::Closing {
                self.quit = true;
            }
            return;
        }
        self.screen = Screen::Closing;
        self.editing = None;
        self.watch_stop.store(true, Ordering::Relaxed);
        if let Some(plan) = &self.plan {
            plan.cancel.store(true, Ordering::Relaxed);
        }
        let (root, owned, tx) = (self.root.clone(), self.owned.clone(), self.tx.clone());
        let launch = self.launch_thread.take();
        let stop_server = self.prefs.stop_on_quit;
        thread::spawn(move || {
            if let Some(handle) = launch {
                let _ = handle.join();
            }
            services::shut_down(root, owned, stop_server, tx);
        });
    }

    pub fn owns(&self, source: Source) -> bool {
        self.owned.owns(source)
    }
}

impl Drop for App {
    fn drop(&mut self) {
        self.owned.stop(None);
    }
}
