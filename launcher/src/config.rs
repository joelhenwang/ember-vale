//! What the player chose: launcher preferences and the game's `.env` file.

use std::fs;
use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};

/// The placeholder the example settings file ships with.
const PLACEHOLDER_KEY: &str = "change-me-before-run";
pub const LOCAL_MODELS_PORT: u16 = 8110;
const LOCAL_MODELS_URL: &str = "http://host.docker.internal:8110";

pub const PROFILE: &str = "WORLDSIM_PROVIDER__ACTIVE_PROFILE";
pub const OPENROUTER_KEY: &str = "WORLDSIM_PROVIDER__OPENROUTER_API_KEY";
pub const OPENROUTER_MODEL: &str = "WORLDSIM_PROVIDER__OPENROUTER_MODEL";
pub const VENICE_KEY: &str = "WORLDSIM_PROVIDER__VENICE_API_KEY";
pub const VENICE_MODEL: &str = "WORLDSIM_PROVIDER__VENICE_MODEL";
pub const FAST_TURNS: &str = "WORLDSIM_APP__BACKGROUND_NARRATION";
const LOCAL_MODELS: &str = "WORLDSIM_LOCAL_MODELS__URL";
const SECURITY_KEY: &str = "WORLDSIM_SECURITY__API_KEY";

/// Launcher-only choices, kept next to the launcher in `launcher.toml`.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct Prefs {
    pub smart_memory: bool,
    pub place_spotting: bool,
    pub graphics_card: bool,
    pub game_port: u16,
    pub open_browser: bool,
    pub rebuild: bool,
    pub stop_on_quit: bool,
}

impl Default for Prefs {
    fn default() -> Self {
        Self {
            smart_memory: true,
            place_spotting: true,
            graphics_card: false,
            game_port: 5180,
            open_browser: true,
            rebuild: false,
            stop_on_quit: true,
        }
    }
}

impl Prefs {
    pub fn path(root: &Path) -> PathBuf {
        root.join("launcher").join("launcher.toml")
    }

    pub fn load(root: &Path) -> Self {
        fs::read_to_string(Self::path(root))
            .ok()
            .and_then(|text| toml::from_str(&text).ok())
            .unwrap_or_default()
    }

    pub fn save(&self, root: &Path) -> std::io::Result<()> {
        let text = toml::to_string_pretty(self).map_err(std::io::Error::other)?;
        fs::write(
            Self::path(root),
            format!("# Ember Vale launcher choices.\n{text}"),
        )
    }
}

/// Which storyteller writes the story.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Storyteller {
    Practice,
    OpenRouter,
    Venice,
}

impl Storyteller {
    pub const ALL: [Self; 3] = [Self::Practice, Self::OpenRouter, Self::Venice];

    pub fn from_profile(profile: &str) -> Self {
        match profile {
            "openrouter" => Self::OpenRouter,
            "venice" => Self::Venice,
            _ => Self::Practice,
        }
    }

    pub fn profile(self) -> &'static str {
        match self {
            Self::Practice => "fake",
            Self::OpenRouter => "openrouter",
            Self::Venice => "venice",
        }
    }

    pub fn label(self) -> &'static str {
        match self {
            Self::Practice => "Practice (no AI)",
            Self::OpenRouter => "OpenRouter",
            Self::Venice => "Venice",
        }
    }

    pub fn key_name(self) -> Option<&'static str> {
        match self {
            Self::Practice => None,
            Self::OpenRouter => Some(OPENROUTER_KEY),
            Self::Venice => Some(VENICE_KEY),
        }
    }

    pub fn model_name(self) -> Option<&'static str> {
        match self {
            Self::Practice => None,
            Self::OpenRouter => Some(OPENROUTER_MODEL),
            Self::Venice => Some(VENICE_MODEL),
        }
    }
}

/// The game's `.env`, edited line by line so comments and order survive.
#[derive(Clone, Debug, Default)]
pub struct EnvFile {
    path: PathBuf,
    lines: Vec<String>,
    pub exists: bool,
}

impl EnvFile {
    pub fn load(root: &Path) -> Self {
        let path = root.join(".env");
        match fs::read_to_string(&path) {
            Ok(text) => Self {
                path,
                lines: text.lines().map(String::from).collect(),
                exists: true,
            },
            Err(_) => Self {
                path,
                lines: vec![],
                exists: false,
            },
        }
    }

    /// Writes a fresh `.env` from the example, with its own local secret.
    pub fn create_from_example(root: &Path) -> std::io::Result<Self> {
        let example = fs::read_to_string(root.join(".env.example"))?;
        let text = example.replace(PLACEHOLDER_KEY, &crate::sys::random_hex(40));
        fs::write(root.join(".env"), text)?;
        Ok(Self::load(root))
    }

    pub fn get(&self, key: &str) -> Option<String> {
        self.lines.iter().find_map(|line| {
            let (name, value) = line.trim().split_once('=')?;
            (name.trim() == key).then(|| unquote(value.trim()).to_string())
        })
    }

    pub fn has_value(&self, key: &str) -> bool {
        self.get(key).is_some_and(|v| !v.is_empty())
    }

    pub fn number(&self, key: &str, default: u16) -> u16 {
        self.get(key)
            .and_then(|v| v.parse().ok())
            .unwrap_or(default)
    }

    pub fn storyteller(&self) -> Storyteller {
        Storyteller::from_profile(&self.get(PROFILE).unwrap_or_default())
    }

    /// Sets `key`, reusing its line (or its commented-out line) when present.
    pub fn set(&mut self, key: &str, value: &str) {
        let line = format!("{key}={value}");
        if let Some(i) = self.position(key, false) {
            self.lines[i] = line;
        } else if let Some(i) = self.position(key, true) {
            self.lines[i] = line;
        } else {
            self.lines.push(line);
        }
    }

    /// Turns `key` off by commenting it out (its value stays for later).
    pub fn unset(&mut self, key: &str) {
        if let Some(i) = self.position(key, false) {
            self.lines[i] = format!("# {}", self.lines[i].trim());
        }
    }

    fn position(&self, key: &str, commented: bool) -> Option<usize> {
        self.lines.iter().position(|line| {
            let line = line.trim();
            let line = if commented {
                match line.strip_prefix('#') {
                    Some(rest) => rest.trim_start(),
                    None => return false,
                }
            } else {
                line
            };
            line.split_once('=')
                .is_some_and(|(name, _)| name.trim() == key)
        })
    }

    pub fn save(&mut self) -> std::io::Result<()> {
        let mut text = self.lines.join("\n");
        text.push('\n');
        fs::write(&self.path, text)?;
        self.exists = true;
        Ok(())
    }

    /// Brings the backend settings in line with the launcher choices.
    pub fn sync_with(&mut self, prefs: &Prefs) {
        if prefs.smart_memory {
            self.set(LOCAL_MODELS, LOCAL_MODELS_URL);
        } else {
            self.unset(LOCAL_MODELS);
        }
        if self.get(SECURITY_KEY).is_some_and(|k| k == PLACEHOLDER_KEY) {
            self.set(SECURITY_KEY, &crate::sys::random_hex(40));
        }
    }

    pub fn api_port(&self) -> u16 {
        self.number("API_PORT", 8101)
    }

    pub fn db_port(&self) -> u16 {
        self.number("POSTGRES_PORT", 5433)
    }
}

fn unquote(value: &str) -> &str {
    let value = value.split(" #").next().unwrap_or(value).trim();
    value
        .strip_prefix('"')
        .and_then(|v| v.strip_suffix('"'))
        .or_else(|| value.strip_prefix('\'').and_then(|v| v.strip_suffix('\'')))
        .unwrap_or(value)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn env(text: &str) -> EnvFile {
        EnvFile {
            path: PathBuf::new(),
            lines: text.lines().map(String::from).collect(),
            exists: true,
        }
    }

    #[test]
    fn reads_values_and_ignores_comments() {
        let file = env("# WORLDSIM_APP__BACKGROUND_NARRATION=true\nAPI_PORT=\"8200\"\n");
        assert_eq!(file.get(FAST_TURNS), None);
        assert_eq!(file.api_port(), 8200);
        assert_eq!(file.db_port(), 5433);
    }

    #[test]
    fn set_reuses_the_commented_line_and_unset_comments_it_out() {
        let mut file = env("A=1\n# WORLDSIM_LOCAL_MODELS__URL=http://old\nB=2");
        file.sync_with(&Prefs::default());
        assert_eq!(file.lines[1], format!("{LOCAL_MODELS}={LOCAL_MODELS_URL}"));
        file.sync_with(&Prefs {
            smart_memory: false,
            ..Prefs::default()
        });
        assert_eq!(
            file.lines[1],
            format!("# {LOCAL_MODELS}={LOCAL_MODELS_URL}")
        );
        assert_eq!(file.lines.len(), 3);
    }

    #[test]
    fn new_keys_are_appended_and_the_placeholder_secret_is_replaced() {
        let mut file = env("WORLDSIM_SECURITY__API_KEY=change-me-before-run");
        file.set(PROFILE, "openrouter");
        file.sync_with(&Prefs::default());
        assert_eq!(file.storyteller(), Storyteller::OpenRouter);
        assert_ne!(file.get(SECURITY_KEY).as_deref(), Some(PLACEHOLDER_KEY));
    }
}
