//! Starting, watching and stopping the game's parts.

use std::path::PathBuf;
use std::process::{Child, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::mpsc::Sender;
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::{Duration, Instant};

use crate::checks::{CheckId, Outcome};
use crate::config::{LOCAL_MODELS_PORT, Prefs};
use crate::sys;

/// Which part of the game a log line came from.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Source {
    Launcher,
    Server,
    Memory,
    Screen,
    Backups,
}

impl Source {
    pub fn label(self) -> &'static str {
        match self {
            Self::Launcher => "launcher",
            Self::Server => "server",
            Self::Memory => "memory",
            Self::Screen => "screen",
            Self::Backups => "backups",
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum StepState {
    Waiting,
    Running,
    Done,
    Skipped,
    Failed,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Step {
    Server,
    Answer,
    Memory,
    Screen,
    Browser,
}

impl Step {
    pub const ALL: [Self; 5] = [
        Self::Server,
        Self::Answer,
        Self::Memory,
        Self::Screen,
        Self::Browser,
    ];

    pub fn title(self) -> &'static str {
        match self {
            Self::Server => "Waking the database and game server",
            Self::Answer => "Waiting for the game server to answer",
            Self::Memory => "Starting smart memory",
            Self::Screen => "Preparing the game screen",
            Self::Browser => "Opening the game in your browser",
        }
    }
}

/// How each part is doing, as seen by the watcher.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct Health {
    pub database: bool,
    pub server: bool,
    pub memory: Option<bool>,
    pub screen: bool,
}

/// Everything background work reports back to the screen.
pub enum Msg {
    Check(CheckId, Outcome),
    ChecksDone,
    Log(Source, String),
    Step(Step, StepState, String),
    Launched(Result<(), String>),
    Fixed(Result<String, String>),
    Health(Health),
    Stopped,
    /// The backups on disk, newest first (or why they couldn't be read).
    BackupList(Result<Vec<crate::backups::Backup>, String>),
    /// What a backup or restore is doing right now.
    BackupBusy(String),
    /// A backup or restore ended: what to tell the player.
    BackupDone(Result<String, String>),
}

/// Processes this launcher started (and so must stop).
#[derive(Clone, Default)]
pub struct Owned(Arc<Mutex<Vec<(Source, Child)>>>);

impl Owned {
    fn add(&self, source: Source, child: Child) {
        if let Ok(mut list) = self.0.lock() {
            list.push((source, child));
        }
    }

    pub fn owns(&self, source: Source) -> bool {
        self.0
            .lock()
            .is_ok_and(|list| list.iter().any(|(s, _)| *s == source))
    }

    /// Stops `source` (or everything), returning what was stopped.
    pub fn stop(&self, only: Option<Source>) -> Vec<Source> {
        let Ok(mut list) = self.0.lock() else {
            return vec![];
        };
        let mut stopped = vec![];
        list.retain_mut(|(source, child)| {
            if only.is_none_or(|o| o == *source) {
                sys::kill_tree(child);
                stopped.push(*source);
                false
            } else {
                true
            }
        });
        stopped
    }

    /// True when a process we started has ended on its own.
    pub fn exited(&self, source: Source) -> bool {
        let Ok(mut list) = self.0.lock() else {
            return false;
        };
        list.iter_mut()
            .filter(|(s, _)| *s == source)
            .any(|(_, child)| matches!(child.try_wait(), Ok(Some(_))))
    }
}

/// What the launch needs to know.
#[derive(Clone)]
pub struct Plan {
    pub root: PathBuf,
    pub prefs: Prefs,
    pub api_port: u16,
    pub db_port: u16,
    /// Set when the player quits mid-launch.
    pub cancel: Arc<AtomicBool>,
}

impl Plan {
    pub fn game_url(&self) -> String {
        format!("http://localhost:{}", self.prefs.game_port)
    }

    fn cancelled(&self) -> bool {
        self.cancel.load(Ordering::Relaxed)
    }
}

/// Starts everything in order, reporting each step. Runs on its own thread.
pub fn launch(plan: Plan, tx: Sender<Msg>, owned: Owned) {
    let step = |s, state, detail: &str| {
        let _ = tx.send(Msg::Step(s, state, detail.to_string()));
    };
    let say = |text: String| {
        let _ = tx.send(Msg::Log(Source::Launcher, text));
    };

    // 1. Docker: database + game server.
    step(
        Step::Server,
        StepState::Running,
        if plan.prefs.rebuild {
            "rebuilding (a few minutes)…"
        } else {
            ""
        },
    );
    let mut args = vec![
        "compose",
        "--ansi",
        "never",
        "--progress",
        "plain",
        "up",
        "-d",
    ];
    if plan.prefs.rebuild {
        args.push("--build");
    }
    say(format!("docker {}", args.join(" ")));
    let started = sys::command("docker")
        .current_dir(&plan.root)
        .args(&args)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn();
    let ok = match started {
        Ok(mut child) => {
            sys::pipe_lines(&mut child, &tx, |line| Msg::Log(Source::Server, line));
            loop {
                if plan.cancelled() {
                    sys::kill_tree(&mut child);
                    return;
                }
                match child.try_wait() {
                    Ok(Some(status)) => break status.success(),
                    Ok(None) => thread::sleep(Duration::from_millis(200)),
                    Err(_) => break false,
                }
            }
        }
        Err(err) => {
            say(format!("could not run docker: {err}"));
            false
        }
    };
    if !ok {
        step(Step::Server, StepState::Failed, "Docker couldn't start it");
        let _ = tx.send(Msg::Launched(Err(
            "Docker couldn't start the game server. The log below says why.".into(),
        )));
        return;
    }
    step(Step::Server, StepState::Done, "");

    // 2. The game server answers once its database is migrated.
    step(Step::Answer, StepState::Running, "");
    let started = Instant::now();
    let limit = Duration::from_secs(240);
    loop {
        if sys::http_get(plan.api_port, "/api/v1/health/live").is_some_and(|(c, _)| c == 200) {
            step(
                Step::Answer,
                StepState::Done,
                &format!("answered after {}s", started.elapsed().as_secs()),
            );
            break;
        }
        if plan.cancelled() {
            return;
        }
        if started.elapsed() > limit {
            server_last_words(&plan, &tx);
            step(Step::Answer, StepState::Failed, "no answer after 4 minutes");
            let _ = tx.send(Msg::Launched(Err(
                "The game server didn't wake up. Its last words are in the log below.".into(),
            )));
            return;
        }
        step(
            Step::Answer,
            StepState::Running,
            &format!("{}s…", started.elapsed().as_secs()),
        );
        thread::sleep(Duration::from_secs(1));
    }

    // 3. Optional smart memory, natively on this PC.
    start_memory(&plan, &tx, &owned);
    if plan.cancelled() {
        return;
    }

    // 4. The game screen (Vite dev server).
    step(Step::Screen, StepState::Running, "");
    let mut screen = sys::command("node");
    screen
        .current_dir(&plan.root)
        .args(["node_modules/vite/bin/vite.js", "--port"])
        .arg(plan.prefs.game_port.to_string())
        .arg("--strictPort")
        .env("NO_COLOR", "1")
        .env("FORCE_COLOR", "0")
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    if plan.api_port != 8101 {
        screen.env(
            "EMBER_VALE_API_TARGET",
            format!("http://localhost:{}", plan.api_port),
        );
    }
    match screen.spawn() {
        Ok(mut child) => {
            sys::pipe_lines(&mut child, &tx, |line| Msg::Log(Source::Screen, line));
            owned.add(Source::Screen, child);
        }
        Err(err) => {
            say(format!("could not run node: {err}"));
            step(Step::Screen, StepState::Failed, "Node.js didn't start");
            let _ = tx.send(Msg::Launched(Err("The game screen couldn't start.".into())));
            return;
        }
    }
    let started = Instant::now();
    loop {
        if sys::port_in_use(plan.prefs.game_port) {
            step(Step::Screen, StepState::Done, &plan.game_url());
            break;
        }
        if plan.cancelled() {
            return;
        }
        if owned.exited(Source::Screen) || started.elapsed() > Duration::from_secs(60) {
            owned.stop(Some(Source::Screen));
            step(Step::Screen, StepState::Failed, "it stopped early");
            let _ = tx.send(Msg::Launched(Err(
                "The game screen stopped before it was ready. The log below says why.".into(),
            )));
            return;
        }
        thread::sleep(Duration::from_millis(250));
    }

    // 5. Into the browser.
    if plan.prefs.open_browser {
        sys::open_url(&plan.game_url());
        step(Step::Browser, StepState::Done, "opened");
    } else {
        step(Step::Browser, StepState::Skipped, "press O to open it");
    }
    let _ = tx.send(Msg::Launched(Ok(())));
}

fn start_memory(plan: &Plan, tx: &Sender<Msg>, owned: &Owned) {
    let step = |state, detail: &str| {
        let _ = tx.send(Msg::Step(Step::Memory, state, detail.to_string()));
    };
    if !plan.prefs.smart_memory {
        return step(StepState::Skipped, "off in Settings");
    }
    if ready(sys::http_get(LOCAL_MODELS_PORT, "/health")) {
        return step(StepState::Done, "already running");
    }
    let python = sys::venv_python(&plan.root);
    if !python.exists() || sys::port_in_use(LOCAL_MODELS_PORT) {
        return step(StepState::Skipped, "not available; playing without it");
    }
    step(StepState::Running, "");
    let mut cmd = sys::command(&python.to_string_lossy());
    cmd.current_dir(plan.root.join("local-models"))
        .args(["-m", "local_models.server", "--port"])
        .arg(LOCAL_MODELS_PORT.to_string())
        .env("PYTHONUNBUFFERED", "1")
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    if !plan.prefs.place_spotting {
        cmd.env("LOCAL_MODELS_EXTRACT", "0");
    }
    if plan.prefs.graphics_card {
        cmd.env("LOCAL_MODELS_DEVICE", "CPU+GPU");
    }
    match cmd.spawn() {
        Ok(mut child) => {
            sys::pipe_lines(&mut child, tx, |line| Msg::Log(Source::Memory, line));
            owned.add(Source::Memory, child);
        }
        Err(_) => return step(StepState::Skipped, "couldn't start; playing without it"),
    }
    let started = Instant::now();
    loop {
        if ready(sys::http_get(LOCAL_MODELS_PORT, "/health")) {
            return step(
                StepState::Done,
                &format!("ready after {}s", started.elapsed().as_secs()),
            );
        }
        if plan.cancelled() {
            return;
        }
        if owned.exited(Source::Memory) || started.elapsed() > Duration::from_secs(180) {
            owned.stop(Some(Source::Memory));
            return step(StepState::Skipped, "couldn't start; playing without it");
        }
        step(
            StepState::Running,
            &format!("loading the models… {}s", started.elapsed().as_secs()),
        );
        thread::sleep(Duration::from_secs(1));
    }
}

/// The local models answer at once but are ready only when loading ends.
fn ready(reply: Option<(u16, String)>) -> bool {
    reply.is_some_and(|(code, body)| {
        code == 200 && body.replace(' ', "").contains("\"loading\":false")
    })
}

fn server_last_words(plan: &Plan, tx: &Sender<Msg>) {
    let (_, out) = sys::run(
        sys::command("docker").current_dir(&plan.root).args([
            "compose",
            "logs",
            "--no-color",
            "--tail",
            "40",
            "api",
        ]),
        Duration::from_secs(20),
    );
    for line in out.lines().filter(|l| !l.trim().is_empty()) {
        let _ = tx.send(Msg::Log(Source::Server, sys::strip_ansi(line)));
    }
}

/// Checks every part every few seconds until `stop` is set.
pub fn watch(plan: Plan, tx: Sender<Msg>, owned: Owned, stop: Arc<AtomicBool>) {
    thread::spawn(move || {
        while !stop.load(Ordering::Relaxed) {
            let memory = (plan.prefs.smart_memory)
                .then(|| ready(sys::http_get(LOCAL_MODELS_PORT, "/health")));
            let health = Health {
                database: sys::port_in_use(plan.db_port),
                server: sys::http_get(plan.api_port, "/api/v1/health/live")
                    .is_some_and(|(c, _)| c == 200),
                memory,
                screen: sys::port_in_use(plan.prefs.game_port) && !owned.exited(Source::Screen),
            };
            if tx.send(Msg::Health(health)).is_err() {
                break;
            }
            for _ in 0..30 {
                if stop.load(Ordering::Relaxed) {
                    break;
                }
                thread::sleep(Duration::from_millis(100));
            }
        }
    });
}

/// Stops what we started and, when asked, the game server too.
pub fn shut_down(root: PathBuf, owned: Owned, stop_server: bool, tx: Sender<Msg>) {
    thread::spawn(move || {
        for source in owned.stop(None) {
            let _ = tx.send(Msg::Log(
                Source::Launcher,
                format!("stopped {}", source.label()),
            ));
        }
        if stop_server {
            let _ = tx.send(Msg::Log(
                Source::Launcher,
                "stopping the game server…".into(),
            ));
            let _ = sys::run(
                sys::command("docker")
                    .current_dir(&root)
                    .args(["compose", "stop"]),
                Duration::from_secs(60),
            );
        }
        let _ = tx.send(Msg::Stopped);
    });
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn memory_is_ready_only_after_loading() {
        assert!(!ready(Some((200, r#"{"loading": true}"#.into()))));
        assert!(ready(Some((
            200,
            r#"{"loading": false, "embed": {}}"#.into()
        ))));
        assert!(!ready(None));
    }
}

#[cfg(test)]
mod live {
    use std::sync::mpsc::channel;

    use super::*;

    /// `cargo test live_launch -- --ignored`: really starts the stack
    /// (smart memory off, game screen on port 5190), then stops what it began.
    #[test]
    #[ignore]
    fn live_launch() {
        let root = sys::find_root().expect("run inside the repo");
        let prefs = Prefs {
            smart_memory: false,
            open_browser: false,
            game_port: 5190,
            ..Prefs::default()
        };
        let plan = Plan {
            root: root.clone(),
            prefs,
            api_port: 8101,
            db_port: 5433,
            cancel: Arc::default(),
        };
        let (tx, rx) = channel();
        let owned = Owned::default();
        let started = Instant::now();
        launch(plan, tx.clone(), owned.clone());
        let mut result = None;
        for msg in rx.try_iter() {
            match msg {
                Msg::Step(step, state, detail) => println!("{step:?} {state:?} {detail}"),
                Msg::Launched(r) => result = Some(r),
                _ => {}
            }
        }
        println!("launched in {:?}", started.elapsed());
        assert_eq!(result, Some(Ok(())));
        assert!(sys::port_in_use(5190));
        let page = sys::http_get(5190, "/").expect("screen answers");
        assert_eq!(page.0, 200);
        let proxied = sys::http_get(5190, "/api/v1/health/live").expect("proxy answers");
        assert_eq!(proxied.0, 200);
        shut_down(root, owned, false, tx);
        while !matches!(rx.recv_timeout(Duration::from_secs(30)), Ok(Msg::Stopped)) {}
        thread::sleep(Duration::from_millis(500));
        assert!(
            !sys::port_in_use(5190),
            "the game screen stops with the launcher"
        );
    }
}
