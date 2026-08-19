# Install or upgrade vainu-cli on Windows using uv (bootstraps Python if needed).
param(
    [switch]$Local,
    [switch]$Upgrade,
    [switch]$NoUpgrade,
    [switch]$Help
)

$ErrorActionPreference = "Stop"

$GitUrl = "git+https://github.com/vainu-app/vainu-cli.git"
$PyPiJsonUrl = "https://pypi.org/pypi/vainu-cli/json"

function Show-Usage {
    Write-Host "Usage: .\install.ps1 [-Local] [-Upgrade] [-NoUpgrade]"
    Write-Host ""
    Write-Host "Install or upgrade vainu-cli with uv."
    Write-Host "  -Local       install from the git checkout containing this script"
    Write-Host "  -Upgrade     upgrade an existing install without asking"
    Write-Host "  -NoUpgrade   keep an existing install as-is"
    Write-Host ""
    Write-Host "With no flags, an existing install prompts before upgrading when the"
    Write-Host "session is interactive, and upgrades automatically when it is not."
    exit 0
}

if ($Help -or $args -contains "-h" -or $args -contains "--help") {
    Show-Usage
}

# Version of vainu-cli currently installed as a uv tool ($null if not installed).
function Get-InstalledVersion {
    try {
        $lines = uv tool list 2>$null
    } catch {
        return $null
    }
    if ($LASTEXITCODE -ne 0) {
        return $null
    }
    foreach ($line in @($lines)) {
        if ("$line" -match '^vainu-cli\s+v(\S+)') {
            return $Matches[1]
        }
    }
    return $null
}

# Latest version published to PyPI ($null if the lookup fails).
function Get-LatestVersion {
    try {
        $info = Invoke-RestMethod -Uri $PyPiJsonUrl -TimeoutSec 15
        if ($info.info.version) {
            return "$($info.info.version)"
        }
    } catch {
        return $null
    }
    return $null
}

# $true / $false for the answer, $null when there is nobody to ask.
function Confirm-Upgrade {
    param([string]$Message)

    if ($env:CI -or -not [Environment]::UserInteractive -or [Console]::IsInputRedirected) {
        return $null
    }
    $reply = Read-Host "$Message [Y/n]"
    if ([string]::IsNullOrWhiteSpace($reply) -or $reply -match '^\s*(y|yes)\s*$') {
        return $true
    }
    return $false
}

function Show-NextSteps {
    Write-Host ""
    Write-Host "Next steps:"
    Write-Host "  vainu login          # sign in via browser"
    Write-Host "  vainu doctor         # verify everything works"
    Write-Host "  vainu examples list  # bundled example payloads"
}

$uv = Get-Command uv -ErrorAction SilentlyContinue
if (-not $uv) {
    Write-Host "Installing uv..."
    irm https://astral.sh/uv/install.ps1 | iex
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "User") + ";" + $env:Path
    $uv = Get-Command uv -ErrorAction SilentlyContinue
}

if (-not $uv) {
    Write-Host "uv was installed but is not on PATH. Close and reopen PowerShell, then retry." -ForegroundColor Red
    exit 1
}

if ($Local) {
    $ScriptPath = $MyInvocation.MyCommand.Path
    if (-not $ScriptPath) {
        Write-Host "-Local needs the script on disk; clone the repo and run .\scripts\install.ps1 -Local." -ForegroundColor Red
        exit 1
    }
    $RepoRoot = Split-Path -Parent (Split-Path -Parent $ScriptPath)
    Write-Host "Installing vainu-cli from $RepoRoot..."
    uv tool install --force --editable $RepoRoot
} else {
    $current = Get-InstalledVersion

    if ($current) {
        $latest = Get-LatestVersion

        if ($latest -and $current -eq $latest) {
            Write-Host "vainu-cli $current is already the latest version."
            Show-NextSteps
            exit 0
        }

        if ($latest) {
            Write-Host "vainu-cli $current is installed; PyPI has $latest."
        } else {
            Write-Host "vainu-cli $current is installed; could not reach PyPI to check for a newer version."
        }

        if ($NoUpgrade) {
            Write-Host "Keeping vainu-cli $current (-NoUpgrade)."
            Show-NextSteps
            exit 0
        }

        if (-not $Upgrade) {
            $answer = Confirm-Upgrade "Upgrade now?"
            if ($answer -eq $false) {
                Write-Host "Keeping vainu-cli $current. Re-run with -Upgrade to upgrade later."
                Show-NextSteps
                exit 0
            }
            if ($null -eq $answer) {
                Write-Host "Non-interactive session - upgrading automatically (pass -NoUpgrade to skip)."
            }
        }

        Write-Host "Upgrading vainu-cli..."
        uv tool upgrade vainu-cli
        if ($LASTEXITCODE -ne 0) {
            uv tool install --force vainu-cli
        }
        # An install pinned to a git ref stays on that ref through `upgrade`;
        # reinstall from PyPI when it did not land on the published version.
        if ($latest -and (Get-InstalledVersion) -ne $latest) {
            Write-Host "Reinstalling vainu-cli $latest from PyPI..."
            uv tool install --force vainu-cli
        }
    } else {
        Write-Host "Installing vainu-cli from PyPI..."
        uv tool install vainu-cli
        if ($LASTEXITCODE -ne 0) {
            Write-Host ""
            Write-Host "PyPI install failed - falling back to GitHub ($GitUrl)..."
            uv tool install $GitUrl
        }
    }
}

Write-Host ""
try {
    $version = vainu --version 2>$null
    Write-Host "Installed: $version"
} catch {
    Write-Host "Installed: vainu-cli (restart PowerShell if 'vainu' is not recognized)"
}

Show-NextSteps
