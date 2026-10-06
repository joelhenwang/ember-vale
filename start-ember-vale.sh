#!/bin/sh
# Starts Ember Vale. The first start builds the launcher (a minute or two).
cd "$(dirname "$0")" || exit 1
if ! command -v cargo >/dev/null 2>&1; then
  echo "The launcher needs Rust to build the first time: https://rustup.rs"
  exit 1
fi
exec cargo run --release --quiet --manifest-path launcher/Cargo.toml
