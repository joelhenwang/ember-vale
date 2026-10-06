# Starts the Ember Vale launcher on Windows (called by "Start Ember Vale.cmd").
#
# Uses launcher\bin\ember-vale-launcher.exe; the first time (or with
# "update") it downloads the newest release from GitHub and checks it
# against the release's SHA256SUMS. Without a download it falls back to
# building from source with Rust, when Rust is installed.
param([string]$Mode = "")

$ErrorActionPreference = "Stop"
$Repo = if ($env:EMBER_VALE_REPO) { $env:EMBER_VALE_REPO } else { "joelhenwang/ember-vale" }
$Root = Split-Path -Parent $PSScriptRoot
$BinDir = Join-Path $Root "launcher\bin"
$Bin = Join-Path $BinDir "ember-vale-launcher.exe"
$Asset = "ember-vale-launcher-windows-x64.exe"

function Get-Launcher {
    $base = "https://github.com/$Repo/releases/latest/download"
    $tmp = Join-Path ([IO.Path]::GetTempPath()) ("ember-vale-" + [Guid]::NewGuid())
    New-Item -ItemType Directory -Path $tmp | Out-Null
    try {
        Write-Host "Downloading the Ember Vale launcher..."
        $ProgressPreference = "SilentlyContinue"
        Invoke-WebRequest -UseBasicParsing "$base/$Asset" -OutFile (Join-Path $tmp $Asset)
        Invoke-WebRequest -UseBasicParsing "$base/SHA256SUMS" -OutFile (Join-Path $tmp "SHA256SUMS")
        $line = Get-Content (Join-Path $tmp "SHA256SUMS") | Where-Object { $_ -match [regex]::Escape($Asset) + '$' }
        if (-not $line) { throw "the release has no checksum for $Asset" }
        $expected = ($line -split '\s+')[0].ToLower()
        $actual = (Get-FileHash -Algorithm SHA256 (Join-Path $tmp $Asset)).Hash.ToLower()
        if ($expected -ne $actual) { throw "the download is damaged (checksum mismatch); try again" }
        New-Item -ItemType Directory -Force -Path $BinDir | Out-Null
        Move-Item -Force (Join-Path $tmp $Asset) $Bin
        Write-Host "Launcher ready."
        return $true
    } catch {
        Write-Host "Could not download the launcher: $($_.Exception.Message)"
        return $false
    } finally {
        Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
    }
}

if ($Mode -eq "update" -or -not (Test-Path $Bin)) {
    [void](Get-Launcher)
}

Set-Location $Root
if (Test-Path $Bin) {
    & $Bin
    exit $LASTEXITCODE
}
if (Get-Command cargo -ErrorAction SilentlyContinue) {
    Write-Host "Building the launcher from source (a minute or two, once)..."
    cargo run --release --quiet --manifest-path (Join-Path $Root "launcher\Cargo.toml")
    exit $LASTEXITCODE
}
Write-Host ""
Write-Host "The launcher could not be downloaded, and Rust is not installed to build it."
Write-Host "Check your internet connection and try again, or download it by hand from"
Write-Host "https://github.com/$Repo/releases/latest and put it in launcher\bin\"
Write-Host "as ember-vale-launcher.exe."
exit 1
