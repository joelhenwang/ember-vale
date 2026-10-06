//! The "gear check": everything that must be in place before the game starts.

use std::path::{Path, PathBuf};
use std::time::Duration;

use sysinfo::System;

use crate::config::{EnvFile, LOCAL_MODELS_PORT, Prefs};
use crate::sys;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Status {
    Waiting,
    Ok,
    Note,
    Problem,
    Off,
}

/// What pressing F does for a check that is not fine yet.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Fix {
    OpenPage(&'static str),
    StartDocker(PathBuf),
    InstallGameFiles,
    CreateSettings,
    OpenSettings,
}

impl Fix {
    pub fn label(&self) -> &'static str {
        match self {
            Fix::OpenPage(_) => "Open the download page",
            Fix::StartDocker(_) => "Start Docker Desktop for me",
            Fix::InstallGameFiles => "Install the game files (takes a minute)",
            Fix::CreateSettings => "Create a settings file for me",
            Fix::OpenSettings => "Open Settings",
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum CheckId {
    Docker,
    DockerRunning,
    Node,
    GameFiles,
    SettingsFile,
    Storyteller,
    Ports,
    Memory,
    SmartMemory,
}

impl CheckId {
    pub const ALL: [Self; 9] = [
        Self::Docker,
        Self::DockerRunning,
        Self::Node,
        Self::GameFiles,
        Self::SettingsFile,
        Self::Storyteller,
        Self::Ports,
        Self::Memory,
        Self::SmartMemory,
    ];

    pub fn title(self) -> &'static str {
        match self {
            Self::Docker => "Docker Desktop installed",
            Self::DockerRunning => "Docker Desktop running",
            Self::Node => "Node.js installed",
            Self::GameFiles => "Game files ready",
            Self::SettingsFile => "Settings file",
            Self::Storyteller => "Storyteller",
            Self::Ports => "Free connections",
            Self::Memory => "Free memory (RAM)",
            Self::SmartMemory => "Smart memory (optional)",
        }
    }

    /// Plain-words description shown beside the selected check.
    pub fn about(self) -> &'static str {
        match self {
            Self::Docker => {
                "Docker runs the game server and its save-file database in a sealed box, so \
                 nothing else on your PC is touched."
            }
            Self::DockerRunning => {
                "Docker Desktop has to be open in the background while you play. It can take \
                 a minute to wake up after starting."
            }
            Self::Node => "Node.js draws the game screen you see in your browser.",
            Self::GameFiles => {
                "The pieces of the game screen, downloaded once into the node_modules folder."
            }
            Self::SettingsFile => {
                "The .env file holds your choices for the game server: which storyteller to \
                 use, your AI key and so on. It never leaves your PC."
            }
            Self::Storyteller => {
                "The AI that plays the characters and narrates the story. Practice mode works \
                 without one but tells a scripted, repetitive tale. A real AI needs an \
                 account key from OpenRouter or Venice."
            }
            Self::Ports => {
                "The game's parts talk to each other through numbered connections (ports). \
                 Another program using one of them would get in the way."
            }
            Self::Memory => {
                "The game server and the optional smart memory need some free RAM. Closing \
                 browser tabs or other games helps if it is low."
            }
            Self::SmartMemory => {
                "A small AI that runs on your own PC and helps characters remember what \
                 matters. The game works without it, just with simpler memories."
            }
        }
    }
}

#[derive(Clone, Debug)]
pub struct Outcome {
    pub status: Status,
    pub detail: String,
    pub fix: Option<Fix>,
    /// A problem here stops the adventure from starting.
    pub blocking: bool,
}

impl Outcome {
    fn ok(detail: impl Into<String>) -> Self {
        Self {
            status: Status::Ok,
            detail: detail.into(),
            fix: None,
            blocking: false,
        }
    }
    fn note(detail: impl Into<String>, fix: Option<Fix>) -> Self {
        Self {
            status: Status::Note,
            detail: detail.into(),
            fix,
            blocking: false,
        }
    }
    fn problem(detail: impl Into<String>, fix: Option<Fix>) -> Self {
        Self {
            status: Status::Problem,
            detail: detail.into(),
            fix,
            blocking: true,
        }
    }
    fn off(detail: impl Into<String>) -> Self {
        Self {
            status: Status::Off,
            detail: detail.into(),
            fix: None,
            blocking: false,
        }
    }
    pub fn waiting() -> Self {
        Self {
            status: Status::Waiting,
            detail: "checking…".into(),
            fix: None,
            blocking: false,
        }
    }
}

/// Facts gathered once per round and shared between checks.
struct Round {
    root: PathBuf,
    env: EnvFile,
    prefs: Prefs,
    docker_up: bool,
    running: Vec<String>,
}

/// Runs every check in order, reporting each one as soon as it is known.
pub fn run_all(root: &Path, prefs: &Prefs, mut report: impl FnMut(CheckId, Outcome)) {
    let mut round = Round {
        root: root.to_path_buf(),
        env: EnvFile::load(root),
        prefs: prefs.clone(),
        docker_up: false,
        running: vec![],
    };
    for id in CheckId::ALL {
        let outcome = check(id, &mut round);
        report(id, outcome);
    }
}

fn check(id: CheckId, round: &mut Round) -> Outcome {
    match id {
        CheckId::Docker => docker_installed(),
        CheckId::DockerRunning => docker_running(round),
        CheckId::Node => node(),
        CheckId::GameFiles => game_files(&round.root),
        CheckId::SettingsFile => settings_file(&round.env),
        CheckId::Storyteller => storyteller(&round.env),
        CheckId::Ports => ports(round),
        CheckId::Memory => memory(&round.prefs),
        CheckId::SmartMemory => smart_memory(round),
    }
}

fn docker_installed() -> Outcome {
    let (ok, out) = sys::run(
        sys::command("docker").arg("--version"),
        Duration::from_secs(10),
    );
    if ok {
        let version = out
            .split(',')
            .next()
            .unwrap_or("")
            .replace("Docker version ", "");
        Outcome::ok(format!("version {}", version.trim()))
    } else {
        Outcome::problem(
            "Docker Desktop isn't installed. Install it, restart your PC, then check again.",
            Some(Fix::OpenPage(
                "https://www.docker.com/products/docker-desktop/",
            )),
        )
    }
}

fn docker_running(round: &mut Round) -> Outcome {
    let (ok, _) = sys::run(
        sys::command("docker").args(["info", "--format", "{{.ServerVersion}}"]),
        Duration::from_secs(15),
    );
    round.docker_up = ok;
    if !ok {
        let fix = sys::docker_desktop().map(Fix::StartDocker);
        return Outcome::problem("Docker Desktop is closed or still waking up.", fix);
    }
    round.running = running_services(&round.root);
    if round.running.iter().any(|s| s == "api") {
        Outcome::ok("awake · the game server is already running")
    } else {
        Outcome::ok("awake")
    }
}

/// Compose services of this game that are up right now.
fn running_services(root: &Path) -> Vec<String> {
    let (ok, out) = sys::run(
        sys::command("docker").current_dir(root).args([
            "compose",
            "ps",
            "--status",
            "running",
            "--format",
            "{{.Service}}",
        ]),
        Duration::from_secs(15),
    );
    if !ok {
        return vec![];
    }
    out.lines()
        .map(|l| l.trim().to_string())
        .filter(|l| !l.is_empty())
        .collect()
}

fn node() -> Outcome {
    let (ok, out) = sys::run(
        sys::command("node").arg("--version"),
        Duration::from_secs(10),
    );
    let version = out.trim().trim_start_matches('v').to_string();
    let major: u32 = version
        .split('.')
        .next()
        .and_then(|m| m.parse().ok())
        .unwrap_or(0);
    let page = Some(Fix::OpenPage("https://nodejs.org/en/download"));
    match (ok, major) {
        (false, _) => Outcome::problem("Node.js isn't installed (pick the LTS version).", page),
        (true, m) if m < 18 => Outcome::problem(
            format!("version {version} is too old; 18 or newer is needed."),
            page,
        ),
        _ => Outcome::ok(format!("version {version}")),
    }
}

fn game_files(root: &Path) -> Outcome {
    if root
        .join("node_modules")
        .join("vite")
        .join("bin")
        .join("vite.js")
        .exists()
    {
        Outcome::ok("installed")
    } else {
        Outcome::problem("Not downloaded yet.", Some(Fix::InstallGameFiles))
    }
}

fn settings_file(env: &EnvFile) -> Outcome {
    if env.exists {
        Outcome::ok(".env found")
    } else {
        Outcome::problem("No .env file yet.", Some(Fix::CreateSettings))
    }
}

fn storyteller(env: &EnvFile) -> Outcome {
    if !env.exists {
        return Outcome::problem("Needs the settings file first.", None);
    }
    let teller = env.storyteller();
    match (teller.key_name(), teller.model_name()) {
        (Some(key), Some(model)) => {
            if env.has_value(key) {
                let model = env.get(model).unwrap_or_else(|| "default model".into());
                Outcome::ok(format!("{} · {model}", teller.label()))
            } else {
                Outcome::problem(
                    format!("{} is picked but has no AI key yet.", teller.label()),
                    Some(Fix::OpenSettings),
                )
            }
        }
        _ => Outcome::note(
            "Practice mode: a scripted storyteller, no AI. Pick a real one in Settings.",
            Some(Fix::OpenSettings),
        ),
    }
}

fn ports(round: &Round) -> Outcome {
    let ours = |service: &str| round.running.iter().any(|s| s == service);
    let mut busy = vec![];
    if !ours("db") && sys::port_in_use(round.env.db_port()) {
        busy.push(format!("{} (database)", round.env.db_port()));
    }
    if !ours("api") && sys::port_in_use(round.env.api_port()) {
        busy.push(format!("{} (game server)", round.env.api_port()));
    }
    let game_port = round.prefs.game_port;
    if sys::port_in_use(game_port) {
        return Outcome::problem(
            format!(
                "Port {game_port} for the game screen is taken (is the game already open in \
                 another launcher?). Pick another port in Settings."
            ),
            Some(Fix::OpenSettings),
        );
    }
    if busy.is_empty() {
        Outcome::ok(format!("game screen on port {game_port}"))
    } else {
        Outcome::problem(
            format!(
                "Another program is using port {}. Close it and check again.",
                busy.join(", ")
            ),
            None,
        )
    }
}

fn memory(prefs: &Prefs) -> Outcome {
    let mut system = System::new();
    system.refresh_memory();
    let free = system.available_memory() as f64 / 1024f64.powi(3);
    let total = system.total_memory() as f64 / 1024f64.powi(3);
    let detail = format!("{free:.1} GB free of {total:.0} GB");
    let needed = if prefs.smart_memory && prefs.place_spotting {
        3.0
    } else {
        2.0
    };
    if free >= needed {
        Outcome::ok(detail)
    } else if prefs.smart_memory && prefs.place_spotting {
        Outcome::note(
            format!("{detail}. Running low: close some apps, or turn Place spotting off."),
            Some(Fix::OpenSettings),
        )
    } else {
        Outcome::note(
            format!("{detail}. Running low: close some apps if the game stutters."),
            None,
        )
    }
}

fn smart_memory(round: &Round) -> Outcome {
    if !round.prefs.smart_memory {
        return Outcome::off("Off · turn it on in Settings");
    }
    let health = sys::http_get(LOCAL_MODELS_PORT, "/health");
    if health.as_ref().is_some_and(|(code, _)| *code == 200) {
        return Outcome::ok("already running · will be reused");
    }
    if health.is_some() || sys::port_in_use(LOCAL_MODELS_PORT) {
        return Outcome::note(
            format!("Port {LOCAL_MODELS_PORT} is taken by another program; skipped this time."),
            None,
        );
    }
    let models = round.root.join("local-models").join("models");
    let has_models = models.read_dir().is_ok_and(|mut d| d.next().is_some());
    if sys::venv_python(&round.root).exists() && has_models {
        Outcome::ok("ready to start")
    } else {
        Outcome::note(
            "Not set up on this PC (see local-models/README.md). The game works without it.",
            Some(Fix::OpenSettings),
        )
    }
}
