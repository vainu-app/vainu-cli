# Install vainu-cli on Windows using uv (bootstraps Python if needed).
param(
    [switch]$Local
)

$ErrorActionPreference = "Stop"

function Show-Usage {
    Write-Host "Usage: .\install.ps1 [-Local]"
    Write-Host ""
    Write-Host "Install vainu-cli with uv."
    Write-Host "  -Local   install from the git checkout containing this script"
    exit 0
}

if ($args -contains "-h" -or $args -contains "--help") {
    Show-Usage
}

$uv = Get-Command uv -ErrorAction SilentlyContinue
if (-not $uv) {
    Write-Host "Installing uv..."
    irm https://astral.sh/uv/install.ps1 | iex
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "User") + ";" + $env:Path
    $uv = Get-Command uv -ErrorAction SilentlyContinue
}

if (-not $uv) {
    Write-Error "uv was installed but is not on PATH. Close and reopen PowerShell, then retry."
}

if ($Local) {
    $RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
    Write-Host "Installing vainu-cli from $RepoRoot..."
    uv tool install --editable $RepoRoot
} else {
    Write-Host "Installing vainu-cli from PyPI..."
    uv tool install vainu-cli
}

Write-Host ""
try {
    $version = vainu --version 2>$null
    Write-Host "Installed: $version"
} catch {
    Write-Host "Installed: vainu-cli (restart PowerShell if 'vainu' is not recognized)"
}

Write-Host ""
Write-Host "Next steps:"
Write-Host "  vainu login          # sign in via browser"
Write-Host "  vainu doctor         # verify everything works"
Write-Host "  vainu examples list  # bundled example payloads"
