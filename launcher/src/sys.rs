//! Small cross-platform helpers: commands with timeouts, ports, HTTP probes.

use std::io::{BufRead, BufReader, Read, Write};
use std::net::{SocketAddr, TcpStream};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::mpsc::Sender;
use std::thread;
use std::time::{Duration, Instant};

#[cfg(windows)]
use std::os::windows::process::CommandExt;

/// Keeps helper processes from flashing a console window on Windows.
#[cfg(windows)]
const CREATE_NO_WINDOW: u32 = 0x0800_0000;

/// A command that never opens a window of its own and never reads stdin.
pub fn command(program: &str) -> Command {
    let mut cmd = Command::new(program);
    cmd.stdin(Stdio::null());
    #[cfg(windows)]
    cmd.creation_flags(CREATE_NO_WINDOW);
    cmd
}

/// npm is a script on Windows, so it needs its .cmd name.
pub fn npm() -> &'static str {
    if cfg!(windows) { "npm.cmd" } else { "npm" }
}

/// Runs a command and returns (success, stdout + stderr), giving up after `timeout`.
pub fn run(cmd: &mut Command, timeout: Duration) -> (bool, String) {
    cmd.stdout(Stdio::piped()).stderr(Stdio::piped());
    let mut child = match cmd.spawn() {
        Ok(child) => child,
        Err(err) => return (false, err.to_string()),
    };
    let out = drain(child.stdout.take());
    let err = drain(child.stderr.take());
    let started = Instant::now();
    let ok = loop {
        match child.try_wait() {
            Ok(Some(status)) => break status.success(),
            Ok(None) if started.elapsed() > timeout => {
                kill_tree(&mut child);
                return (false, "took too long to answer".into());
            }
            Ok(None) => thread::sleep(Duration::from_millis(50)),
            Err(_) => break false,
        }
    };
    let mut text = out.join().unwrap_or_default();
    text.push_str(&err.join().unwrap_or_default());
    (ok, text)
}

fn drain<R: Read + Send + 'static>(pipe: Option<R>) -> thread::JoinHandle<String> {
    thread::spawn(move || {
        let mut text = String::new();
        if let Some(mut pipe) = pipe {
            let _ = pipe.read_to_string(&mut text);
        }
        text
    })
}

/// Sends every output line of `child` to `sink`, tagged with `source`.
pub fn pipe_lines<T, F>(child: &mut Child, sink: &Sender<T>, wrap: F)
where
    T: Send + 'static,
    F: Fn(String) -> T + Clone + Send + 'static,
{
    if let Some(out) = child.stdout.take() {
        forward(out, sink.clone(), wrap.clone());
    }
    if let Some(err) = child.stderr.take() {
        forward(err, sink.clone(), wrap);
    }
}

fn forward<R, T, F>(pipe: R, sink: Sender<T>, wrap: F)
where
    R: Read + Send + 'static,
    T: Send + 'static,
    F: Fn(String) -> T + Send + 'static,
{
    thread::spawn(move || {
        for line in BufReader::new(pipe).lines().map_while(Result::ok) {
            let line = strip_ansi(&line);
            if !line.trim().is_empty() && sink.send(wrap(line)).is_err() {
                break;
            }
        }
    });
}

/// Removes terminal colour codes so tool output reads cleanly in our panels.
pub fn strip_ansi(text: &str) -> String {
    let mut out = String::with_capacity(text.len());
    let mut chars = text.chars().peekable();
    while let Some(c) = chars.next() {
        if c == '\u{1b}' {
            if chars.peek() == Some(&'[') {
                chars.next();
                for c in chars.by_ref() {
                    if c.is_ascii_alphabetic() {
                        break;
                    }
                }
            }
        } else if c == '\r' {
            continue;
        } else {
            out.push(c);
        }
    }
    out
}

/// Stops a process and everything it started.
pub fn kill_tree(child: &mut Child) {
    #[cfg(windows)]
    {
        let _ = command("taskkill")
            .args(["/PID", &child.id().to_string(), "/T", "/F"])
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status();
    }
    let _ = child.kill();
    let _ = child.wait();
}

/// True when something on this machine is listening on `port`.
pub fn port_in_use(port: u16) -> bool {
    let addr = SocketAddr::from(([127, 0, 0, 1], port));
    TcpStream::connect_timeout(&addr, Duration::from_millis(300)).is_ok()
}

/// A tiny HTTP GET against localhost: (status code, body).
pub fn http_get(port: u16, path: &str) -> Option<(u16, String)> {
    let addr = SocketAddr::from(([127, 0, 0, 1], port));
    let mut stream = TcpStream::connect_timeout(&addr, Duration::from_millis(800)).ok()?;
    stream.set_read_timeout(Some(Duration::from_secs(3))).ok()?;
    let request =
        format!("GET {path} HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nConnection: close\r\n\r\n");
    stream.write_all(request.as_bytes()).ok()?;
    let mut reply = String::new();
    let _ = stream.read_to_string(&mut reply);
    let code = reply.split_whitespace().nth(1)?.parse().ok()?;
    let body = reply
        .split_once("\r\n\r\n")
        .map(|(_, b)| b.to_string())
        .unwrap_or_default();
    Some((code, body))
}

/// Opens a web page in the player's default browser.
pub fn open_url(url: &str) {
    let mut cmd = if cfg!(windows) {
        let mut c = command("cmd");
        c.args(["/C", "start", "", url]);
        c
    } else if cfg!(target_os = "macos") {
        let mut c = command("open");
        c.arg(url);
        c
    } else {
        let mut c = command("xdg-open");
        c.arg(url);
        c
    };
    let _ = cmd.stdout(Stdio::null()).stderr(Stdio::null()).spawn();
}

/// Where Docker Desktop lives, when it is installed in the usual place.
pub fn docker_desktop() -> Option<PathBuf> {
    let candidates: &[&str] = if cfg!(windows) {
        &[r"C:\Program Files\Docker\Docker\Docker Desktop.exe"]
    } else if cfg!(target_os = "macos") {
        &["/Applications/Docker.app"]
    } else {
        &[]
    };
    candidates.iter().map(PathBuf::from).find(|p| p.exists())
}

/// Asks the OS to start Docker Desktop.
pub fn start_docker_desktop(app: &Path) -> bool {
    let mut cmd = if cfg!(windows) {
        let mut c = command("cmd");
        c.arg("/C").arg("start").arg("").arg(app);
        c
    } else {
        let mut c = command("open");
        c.arg("-a").arg("Docker");
        c
    };
    cmd.stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .is_ok()
}

/// The python inside the local-models virtual environment.
pub fn venv_python(root: &Path) -> PathBuf {
    let venv = root.join("local-models").join(".venv");
    if cfg!(windows) {
        venv.join("Scripts").join("python.exe")
    } else {
        venv.join("bin").join("python")
    }
}

/// Finds the Ember Vale folder: the one holding compose.yaml and package.json.
pub fn find_root() -> Option<PathBuf> {
    let looks_right = |p: &Path| p.join("compose.yaml").exists() && p.join("package.json").exists();
    let mut starts = vec![];
    if let Ok(cwd) = std::env::current_dir() {
        starts.push(cwd);
    }
    if let Ok(exe) = std::env::current_exe() {
        starts.push(exe);
    }
    starts
        .into_iter()
        .flat_map(|start| start.ancestors().map(Path::to_path_buf).collect::<Vec<_>>())
        .find(|p| looks_right(p))
}

/// A random hex string for locally generated secrets.
pub fn random_hex(len: usize) -> String {
    (0..len)
        .map(|_| char::from_digit(fastrand::u32(0..16), 16).unwrap_or('0'))
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn colour_codes_are_removed() {
        assert_eq!(
            strip_ansi("\u{1b}[32mready\u{1b}[0m in 300ms\r"),
            "ready in 300ms"
        );
    }

    #[test]
    fn secrets_are_hex_of_the_asked_length() {
        let key = random_hex(32);
        assert_eq!(key.len(), 32);
        assert!(key.chars().all(|c| c.is_ascii_hexdigit()));
    }
}
