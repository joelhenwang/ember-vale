@echo off
rem Double-click to start Ember Vale. The first start builds the launcher (a minute or two).
cd /d "%~dp0"
where cargo >nul 2>nul
if errorlevel 1 (
  echo The launcher needs Rust to build the first time: https://rustup.rs
  echo Install it, then double-click this file again.
  pause
  exit /b 1
)
cargo run --release --quiet --manifest-path launcher\Cargo.toml
if errorlevel 1 pause
