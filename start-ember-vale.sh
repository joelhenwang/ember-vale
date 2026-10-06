#!/bin/sh
# Starts Ember Vale on macOS and Linux. The first start downloads the
# launcher for this computer from GitHub and checks it against the
# release's SHA256SUMS; `./start-ember-vale.sh update` fetches the newest
# one again. Without a download it builds from source when Rust is installed.
set -u
cd "$(dirname "$0")" || exit 1
ROOT=$(pwd)
REPO=${EMBER_VALE_REPO:-joelhenwang/ember-vale}
BIN="$ROOT/launcher/bin/ember-vale-launcher"

case "$(uname -s)" in
  Darwin) os=macos ;;
  Linux) os=linux ;;
  *) os="" ;;
esac
case "$(uname -m)" in
  x86_64 | amd64) arch=x64 ;;
  arm64 | aarch64) arch=arm64 ;;
  *) arch="" ;;
esac
ASSET="ember-vale-launcher-$os-$arch"

fetch() { # url file
  if command -v curl >/dev/null 2>&1; then curl -fsSL "$1" -o "$2"
  elif command -v wget >/dev/null 2>&1; then wget -q "$1" -O "$2"
  else return 1; fi
}

sha256() {
  if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | cut -d' ' -f1
  else shasum -a 256 "$1" | cut -d' ' -f1; fi
}

download() {
  [ -n "$os" ] && [ -n "$arch" ] || { echo "No ready-made launcher for this computer."; return 1; }
  base="https://github.com/$REPO/releases/latest/download"
  tmp=$(mktemp -d) || return 1
  echo "Downloading the Ember Vale launcher..."
  if fetch "$base/$ASSET" "$tmp/$ASSET" && fetch "$base/SHA256SUMS" "$tmp/SHA256SUMS"; then
    expected=$(grep " $ASSET\$" "$tmp/SHA256SUMS" | cut -d' ' -f1)
    if [ -n "$expected" ] && [ "$expected" = "$(sha256 "$tmp/$ASSET")" ]; then
      mkdir -p "$ROOT/launcher/bin"
      mv "$tmp/$ASSET" "$BIN" && chmod +x "$BIN"
      rm -rf "$tmp"
      echo "Launcher ready."
      return 0
    fi
    echo "The download is damaged (checksum mismatch); try again."
  else
    echo "Could not download the launcher."
  fi
  rm -rf "$tmp"
  return 1
}

if [ "${1:-}" = "update" ] || [ ! -x "$BIN" ]; then
  download || true
fi

if [ -x "$BIN" ]; then
  exec "$BIN"
fi
if command -v cargo >/dev/null 2>&1; then
  echo "Building the launcher from source (a minute or two, once)..."
  exec cargo run --release --quiet --manifest-path launcher/Cargo.toml
fi
echo
echo "The launcher could not be downloaded, and Rust is not installed to build it."
echo "Check your internet connection, or download $ASSET by hand from"
echo "https://github.com/$REPO/releases/latest into launcher/bin/ as ember-vale-launcher."
exit 1
