//! Backups of the player's stories, through the compose `backup` service
//! (backend/docker/backup/backup.sh): see them, take one now, put one back.
//!
//! Parsing, wording and the docker command lines are plain functions so they
//! can be tested without Docker; the runners below only execute them.

use std::path::{Path, PathBuf};
use std::process::Stdio;
use std::sync::mpsc::Sender;
use std::thread;
use std::time::{Duration, Instant};

use chrono::{Local, NaiveDateTime, TimeZone};

use crate::services::{Msg, Source};
use crate::sys;

/// One backup folder, as `backup.sh list` reports it.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Backup {
    /// The folder name: a UTC time, `YYYYMMDD-HHMMSS`.
    pub stamp: String,
    pub taken_utc: NaiveDateTime,
    pub stories: u32,
    /// `du -sh` style, e.g. `1.9M`.
    pub size: String,
}

impl Backup {
    /// When it was taken, in this computer's time: "Fri 9 Oct, 09:18".
    pub fn when(&self) -> String {
        when(self.taken_utc, &Local)
    }

    /// "Fri 9 Oct, 09:18 · 3 stories · 1.9 MB"
    pub fn summary(&self) -> String {
        format!(
            "{} · {} · {}",
            self.when(),
            stories_label(self.stories),
            size_label(&self.size)
        )
    }
}

/// Reads a backup folder name (`20261009-091800`, UTC).
pub fn parse_stamp(text: &str) -> Option<NaiveDateTime> {
    let ok = text.len() == 15
        && text
            .char_indices()
            .all(|(i, c)| if i == 8 { c == '-' } else { c.is_ascii_digit() });
    ok.then(|| NaiveDateTime::parse_from_str(text, "%Y%m%d-%H%M%S").ok())
        .flatten()
}

/// Reads the output of `backup.sh list` ("<stamp>  <N> stories  <size>" per
/// line). Anything else Docker prints along the way is skipped. Newest first.
pub fn parse_list(output: &str) -> Vec<Backup> {
    let mut found: Vec<Backup> = output
        .lines()
        .filter_map(|line| {
            let words: Vec<&str> = line.split_whitespace().collect();
            let (&stamp, rest) = words.split_first()?;
            let taken_utc = parse_stamp(stamp)?;
            let at = rest
                .iter()
                .position(|w| w.eq_ignore_ascii_case("stories") || w.eq_ignore_ascii_case("story"));
            let stories = at
                .and_then(|i| i.checked_sub(1))
                .and_then(|i| rest[i].parse().ok())
                .unwrap_or(0);
            let size = at
                .and_then(|i| rest.get(i + 1))
                .map(|s| s.to_string())
                .unwrap_or_default();
            Some(Backup {
                stamp: stamp.to_string(),
                taken_utc,
                stories,
                size,
            })
        })
        .collect();
    found.sort_by(|a, b| b.stamp.cmp(&a.stamp));
    found.dedup_by(|a, b| a.stamp == b.stamp);
    found
}

/// A UTC time shown in `zone`, e.g. "Fri 9 Oct, 09:18".
pub fn when<Z: TimeZone>(utc: NaiveDateTime, zone: &Z) -> String
where
    Z::Offset: std::fmt::Display,
{
    zone.from_utc_datetime(&utc)
        .format("%a %-d %b, %H:%M")
        .to_string()
}

pub fn stories_label(n: u32) -> String {
    match n {
        0 => "no stories".into(),
        1 => "1 story".into(),
        n => format!("{n} stories"),
    }
}

/// `du -sh` sizes in words a player knows: `1.9M` → `1.9 MB`.
pub fn size_label(size: &str) -> String {
    let Some(last) = size.chars().last() else {
        return "size unknown".into();
    };
    let number = &size[..size.len() - last.len_utf8()];
    let unit = match last.to_ascii_uppercase() {
        'K' => "KB",
        'M' => "MB",
        'G' => "GB",
        'T' => "TB",
        _ if last.is_ascii_digit() => return format!("{size} bytes"),
        _ => return size.to_string(),
    };
    format!("{number} {unit}")
}

// ---- the docker command lines -----------------------------------------------

fn backup_service(action: &[&str]) -> Vec<String> {
    ["compose", "--ansi", "never", "run", "--rm", "-T", "backup"]
        .iter()
        .chain(action)
        .map(|s| s.to_string())
        .collect()
}

pub fn docker_awake_args() -> Vec<String> {
    ["info", "--format", "{{.ServerVersion}}"]
        .map(String::from)
        .to_vec()
}

pub fn list_args() -> Vec<String> {
    backup_service(&["list"])
}

pub fn now_args() -> Vec<String> {
    backup_service(&["now"])
}

pub fn restore_args(stamp: &str) -> Vec<String> {
    backup_service(&["restore", stamp])
}

/// One step of a restore, with what to say while it runs.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Task {
    pub says: String,
    pub args: Vec<String>,
    /// Tried when `args` fails (the worker service is opt-in, so stopping it
    /// can fail where stopping the api alone works).
    pub fallback: Option<Vec<String>>,
    pub timeout: Duration,
}

/// The restore, in the order of scripts/restore-backup.sh.
pub fn restore_tasks(stamp: &str, when: &str) -> Vec<Task> {
    let compose = |args: &[&str]| args.iter().map(|s| s.to_string()).collect::<Vec<_>>();
    vec![
        Task {
            says: "Backing up your game as it is now".into(),
            args: now_args(),
            fallback: None,
            timeout: Duration::from_secs(15 * 60),
        },
        Task {
            says: "Stopping the game server".into(),
            args: compose(&["compose", "stop", "api", "worker"]),
            fallback: Some(compose(&["compose", "stop", "api"])),
            timeout: Duration::from_secs(120),
        },
        Task {
            says: format!("Putting back the backup from {when}"),
            args: restore_args(stamp),
            fallback: None,
            timeout: Duration::from_secs(30 * 60),
        },
        Task {
            says: "Starting the game server again".into(),
            args: start_server_args(),
            fallback: None,
            timeout: Duration::from_secs(120),
        },
    ]
}

pub fn start_server_args() -> Vec<String> {
    ["compose", "start", "api"].map(String::from).to_vec()
}

// ---- running them -------------------------------------------------------------

const LIST_TIMEOUT: Duration = Duration::from_secs(90);
const NOW_TIMEOUT: Duration = Duration::from_secs(15 * 60);
const SERVER_ANSWER: Duration = Duration::from_secs(240);

fn say(tx: &Sender<Msg>, text: impl Into<String>) {
    let _ = tx.send(Msg::Log(Source::Backups, text.into()));
}

fn minutes(d: Duration) -> String {
    match d.as_secs().div_ceil(60) {
        1 => "a minute".into(),
        n => format!("{n} minutes"),
    }
}

/// Runs docker, streaming its lines into the log. Err says what went wrong.
fn docker(root: &Path, args: &[String], timeout: Duration, tx: &Sender<Msg>) -> Result<(), String> {
    let mut child = sys::command("docker")
        .current_dir(root)
        .args(args)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|err| format!("Docker couldn't be run ({err})"))?;
    sys::pipe_lines(&mut child, tx, |line| Msg::Log(Source::Backups, line));
    let started = Instant::now();
    loop {
        match child.try_wait() {
            Ok(Some(status)) if status.success() => return Ok(()),
            Ok(Some(_)) => return Err("Docker reported a problem; the log says why".into()),
            Ok(None) if started.elapsed() > timeout => {
                sys::kill_tree(&mut child);
                return Err(format!(
                    "Docker didn't finish within {}, so the launcher stopped waiting",
                    minutes(timeout)
                ));
            }
            Ok(None) => thread::sleep(Duration::from_millis(200)),
            Err(err) => return Err(err.to_string()),
        }
    }
}

/// Docker Desktop must be awake for any of this.
fn docker_awake(tx: &Sender<Msg>) -> Result<(), String> {
    let (ok, _) = sys::run(
        sys::command("docker").args(docker_awake_args()),
        Duration::from_secs(15),
    );
    if ok {
        Ok(())
    } else {
        let why = "Docker Desktop isn't running, so the backups can't be reached. \
                   Start Docker Desktop and try again.";
        say(tx, why);
        Err(why.into())
    }
}

/// Reads the list of backups.
pub fn refresh(root: PathBuf, tx: Sender<Msg>) {
    thread::spawn(move || {
        let _ = tx.send(Msg::BackupList(read_list(&root, &tx)));
    });
}

fn read_list(root: &Path, tx: &Sender<Msg>) -> Result<Vec<Backup>, String> {
    docker_awake(tx)?;
    let (ok, out) = sys::run(
        sys::command("docker").current_dir(root).args(list_args()),
        LIST_TIMEOUT,
    );
    if !ok {
        for line in out.lines().filter(|l| !l.trim().is_empty()) {
            say(tx, sys::strip_ansi(line));
        }
        return Err("Couldn't read the list of backups. The log below says why.".into());
    }
    Ok(parse_list(&sys::strip_ansi(&out)))
}

/// Takes a backup now.
pub fn back_up_now(root: PathBuf, tx: Sender<Msg>) {
    thread::spawn(move || {
        let result = docker_awake(&tx).and_then(|()| {
            let _ = tx.send(Msg::BackupBusy("Backing up your game…".into()));
            say(&tx, "Backing up your game…");
            docker(&root, &now_args(), NOW_TIMEOUT, &tx)
                .map(|()| "Backed up. Your game as it is now is in the list.".to_string())
                .map_err(|why| format!("The backup didn't finish: {why}."))
        });
        say(&tx, result.clone().unwrap_or_else(|e| e));
        let _ = tx.send(Msg::BackupDone(result));
        let _ = tx.send(Msg::BackupList(read_list(&root, &tx)));
    });
}

/// Puts a backup back: backs up the current game first, stops the server,
/// restores, starts the server and waits until it answers.
pub fn restore(root: PathBuf, api_port: u16, backup: Backup, tx: Sender<Msg>) {
    thread::spawn(move || {
        let result = run_restore(&root, api_port, &backup, &tx);
        say(&tx, result.clone().unwrap_or_else(|e| e));
        let _ = tx.send(Msg::BackupDone(result));
        let _ = tx.send(Msg::BackupList(read_list(&root, &tx)));
    });
}

fn run_restore(
    root: &Path,
    api_port: u16,
    backup: &Backup,
    tx: &Sender<Msg>,
) -> Result<String, String> {
    docker_awake(tx)?;
    let when = backup.when();
    let tasks = restore_tasks(&backup.stamp, &when);
    let total = tasks.len();
    for (i, task) in tasks.iter().enumerate() {
        let head = format!("Step {} of {total}: {}", i + 1, task.says);
        let _ = tx.send(Msg::BackupBusy(format!("{head}…")));
        say(tx, format!("{head}…"));
        let mut done = docker(root, &task.args, task.timeout, tx);
        if done.is_err()
            && let Some(other) = &task.fallback
        {
            done = docker(root, other, task.timeout, tx);
        }
        let Err(why) = done else { continue };
        let failed = format!("{head} failed: {why}.");
        return Err(match i {
            0 => format!("{failed} Nothing was changed."),
            1 => {
                let _ = docker(root, &start_server_args(), Duration::from_secs(120), tx);
                format!("{failed} Nothing was changed.")
            }
            2 => {
                let _ = docker(root, &start_server_args(), Duration::from_secs(120), tx);
                format!(
                    "{failed} Your game may be incomplete now. The backup taken just \
                     before is at the top of the list; put it back to return to where you were."
                )
            }
            _ => format!("{failed} Your stories are back, but the game server isn't running."),
        });
    }
    let _ = tx.send(Msg::BackupBusy(
        "Waiting for the game server to answer…".into(),
    ));
    say(tx, "Waiting for the game server to answer…");
    let started = Instant::now();
    while started.elapsed() < SERVER_ANSWER {
        if sys::http_get(api_port, "/api/v1/health/live").is_some_and(|(c, _)| c == 200) {
            return Ok(format!(
                "Done. Your game is back to {when} ({}). Reload the game page to see it.",
                stories_label(backup.stories)
            ));
        }
        thread::sleep(Duration::from_secs(1));
    }
    Err(format!(
        "Your stories from {when} are back, but the game server didn't answer within {}. \
         Press R on the main screen to restart it.",
        minutes(SERVER_ANSWER)
    ))
}

#[cfg(test)]
mod tests {
    use chrono::FixedOffset;

    use super::*;

    fn at(stamp: &str) -> NaiveDateTime {
        parse_stamp(stamp).expect("a stamp")
    }

    #[test]
    fn stamps_are_read_strictly() {
        assert!(parse_stamp("20261009-091800").is_some());
        for bad in [
            "20261009091800",
            "2026-10-09",
            ".20261009-091800.partial",
            "20261399-091800",
            "20261009-091800x",
            "",
        ] {
            assert_eq!(parse_stamp(bad), None, "{bad}");
        }
    }

    #[test]
    fn the_list_is_read_past_docker_chatter() {
        let out = "\
 Container ember-vale-db-1  Running\r
20261008-030000  0 stories  4.0K
\u{1b}[32m20261009-081800  3 stories  1.9M\u{1b}[0m
 something else entirely
20261007-030000  1 stories  812K
20261009-081800  3 stories  1.9M
20261006-030000
";
        let list = parse_list(&sys::strip_ansi(out));
        let stamps: Vec<&str> = list.iter().map(|b| b.stamp.as_str()).collect();
        assert_eq!(
            stamps,
            [
                "20261009-081800",
                "20261008-030000",
                "20261007-030000",
                "20261006-030000"
            ]
        );
        assert_eq!(list[0].stories, 3);
        assert_eq!(list[0].size, "1.9M");
        assert_eq!(list[1].stories, 0);
        assert_eq!(list[2].stories, 1);
        assert_eq!(list[3].stories, 0);
        assert_eq!(list[3].size, "");
    }

    #[test]
    fn an_empty_list_is_empty() {
        assert!(parse_list("").is_empty());
        assert!(parse_list("no backups here\n").is_empty());
    }

    #[test]
    fn times_show_in_the_players_zone() {
        let utc = at("20261009-081800");
        let lisbon = FixedOffset::east_opt(3600).unwrap();
        assert_eq!(when(utc, &lisbon), "Fri 9 Oct, 09:18");
        assert_eq!(when(utc, &chrono::Utc), "Fri 9 Oct, 08:18");
        // Late at night in UTC is already tomorrow further east.
        let tokyo = FixedOffset::east_opt(9 * 3600).unwrap();
        assert_eq!(when(at("20261009-230500"), &tokyo), "Sat 10 Oct, 08:05");
        let new_york = FixedOffset::west_opt(4 * 3600).unwrap();
        assert_eq!(when(at("20261009-020000"), &new_york), "Thu 8 Oct, 22:00");
    }

    #[test]
    fn counts_and_sizes_read_plainly() {
        assert_eq!(stories_label(0), "no stories");
        assert_eq!(stories_label(1), "1 story");
        assert_eq!(stories_label(12), "12 stories");
        assert_eq!(size_label("1.9M"), "1.9 MB");
        assert_eq!(size_label("812K"), "812 KB");
        assert_eq!(size_label("2.1G"), "2.1 GB");
        assert_eq!(size_label("512"), "512 bytes");
        assert_eq!(size_label(""), "size unknown");
    }

    #[test]
    fn docker_command_lines() {
        let run = ["compose", "--ansi", "never", "run", "--rm", "-T", "backup"];
        let with = |extra: &[&str]| -> Vec<String> {
            run.iter().chain(extra).map(|s| s.to_string()).collect()
        };
        assert_eq!(list_args(), with(&["list"]));
        assert_eq!(now_args(), with(&["now"]));
        assert_eq!(
            restore_args("20261009-081800"),
            with(&["restore", "20261009-081800"])
        );
        assert_eq!(
            docker_awake_args(),
            ["info", "--format", "{{.ServerVersion}}"]
        );
        assert_eq!(start_server_args(), ["compose", "start", "api"]);
    }

    #[test]
    fn a_restore_backs_up_first_and_brings_the_server_back() {
        let tasks = restore_tasks("20261009-081800", "Fri 9 Oct, 09:18");
        let args: Vec<Vec<String>> = tasks.iter().map(|t| t.args.clone()).collect();
        assert_eq!(
            args,
            [
                now_args(),
                ["compose", "stop", "api", "worker"]
                    .map(String::from)
                    .to_vec(),
                restore_args("20261009-081800"),
                start_server_args(),
            ]
        );
        assert_eq!(
            tasks[1].fallback,
            Some(["compose", "stop", "api"].map(String::from).to_vec())
        );
        assert!(
            tasks
                .iter()
                .enumerate()
                .all(|(i, t)| (i == 1) == t.fallback.is_some())
        );
        assert_eq!(
            tasks[2].says,
            "Putting back the backup from Fri 9 Oct, 09:18"
        );
    }

    #[test]
    fn a_summary_reads_like_a_sentence() {
        let backup = Backup {
            stamp: "20261009-081800".into(),
            taken_utc: at("20261009-081800"),
            stories: 3,
            size: "1.9M".into(),
        };
        assert!(backup.summary().ends_with(" · 3 stories · 1.9 MB"));
        assert_eq!(minutes(Duration::from_secs(120)), "2 minutes");
        assert_eq!(minutes(Duration::from_secs(30)), "a minute");
    }
}
