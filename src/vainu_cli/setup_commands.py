"""`vainu doctor` and `vainu update` — install checks and self-upgrade."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys

import click

from vainu_cli._version import __version__
from vainu_cli.auth.storage import TokenStore, cached_token_usernames
from vainu_cli.examples import examples_dir


def _path_hint() -> str:
    system = platform.system()
    bin_dir = os.path.join(os.path.expanduser("~"), ".local", "bin")
    if system == "Windows":
        return (
            f"Add {bin_dir} to your PATH, then close and reopen PowerShell.\n"
            "See SETUP.md for step-by-step Windows instructions."
        )
    if system == "Darwin":
        return (
            f"Add this line to ~/.zprofile, then open a new Terminal window:\n"
            f'  export PATH="{bin_dir}:$PATH"'
        )
    return f'Add this line to ~/.bashrc, then open a new terminal:\n  export PATH="{bin_dir}:$PATH"'


def _auth_summary() -> tuple[bool, list[str]]:
    lines: list[str] = []
    store = TokenStore()
    creds = store.load()
    if creds is not None:
        who = creds.account or creds.client_id
        status = "expired — run `vainu login`" if creds.is_expired() else "OK"
        lines.append(f"Browser login: {who} ({status})")
    if os.environ.get("VAINU_API_KEY"):
        lines.append("API key: set via VAINU_API_KEY")
    if os.environ.get("VAINU_CLIENT_ID") and os.environ.get("VAINU_CLIENT_SECRET"):
        lines.append("OAuth: client ID + secret set in environment")
    if os.environ.get("VAINU_JWT_REFRESH_TOKEN"):
        lines.append("JWT: refresh token set in environment")
    cached = cached_token_usernames()
    if cached:
        lines.append(f"Cached OAuth tokens: {len(cached)}")
    return bool(lines), lines


@click.command("doctor")
def doctor_command() -> None:
    """Check install, authentication, and bundled examples."""
    ok = True
    click.echo(f"vainu-cli {__version__}")
    click.echo(f"Python {sys.version.split()[0]} on {platform.system()}")
    click.echo("")

    exe = shutil.which("vainu")
    if exe:
        click.echo(f"Install: OK ({exe})")
    else:
        click.echo("Install: vainu not found on PATH")
        click.echo(_path_hint())
        ok = False

    has_auth, auth_lines = _auth_summary()
    if has_auth:
        click.echo("Auth:")
        for line in auth_lines:
            click.echo(f"  - {line}")
    else:
        click.echo("Auth: not configured — run `vainu login`")
        ok = False

    try:
        root = examples_dir()
        count = sum(1 for _ in root.rglob("*.json"))
        click.echo(f"Examples: OK ({count} bundled payloads in {root})")
    except FileNotFoundError as exc:
        click.echo(f"Examples: missing ({exc})")
        ok = False

    click.echo("")
    if ok:
        click.echo("All checks passed. Try:")
        click.echo('  vainu organizations --payload "$(vainu examples path 08-simple-filtering)"')
    else:
        click.echo("Some checks failed. See SETUP.md or run:")
        click.echo("  vainu login")
        ctx = click.get_current_context(silent=True)
        if ctx is not None:
            ctx.exit(1)


PACKAGE_NAME = "vainu-cli"


def _upgrade_argv() -> list[str]:
    if shutil.which("uv"):
        return ["uv", "tool", "upgrade", PACKAGE_NAME]
    return [sys.executable, "-m", "pip", "install", "--upgrade", PACKAGE_NAME]


def _run_update() -> None:
    click.echo(f"Updating vainu-cli {__version__}...")
    cmd = _upgrade_argv()
    result = subprocess.run(cmd, check=False)
    if result.returncode != 0:
        raise click.ClickException(
            "Update failed. Re-run the installer in SETUP.md, or install uv and retry."
        )
    click.echo("Update complete. Run `vainu --version` to confirm.")


@click.command("update")
def update_command() -> None:
    """Upgrade vainu-cli to the latest version from PyPI."""
    _run_update()


@click.command("upgrade")
def upgrade_command() -> None:
    """Upgrade vainu-cli to the latest version from PyPI. Alias for `update`."""
    _run_update()
