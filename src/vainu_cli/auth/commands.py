"""`vainu login`, `vainu logout`, `vainu auth status` commands."""

from __future__ import annotations

import datetime as dt
import json
import logging

import click
import requests

from vainu_cli.auth.oauth_flow import run_login
from vainu_cli.auth.storage import TokenStore
from vainu_cli.common import (
    DEFAULT_AUTHORIZE_BASE_URL,
    DEFAULT_BASE_URL,
    DEFAULT_SCOPES,
    OAUTH_REVOKE_ENDPOINT,
    PUBLIC_CLIENT_ID,
)

logger = logging.getLogger(__name__)


def _base_url_from_config(ctx: click.Context) -> str:
    config = ctx.obj
    if config is not None and getattr(config, "base_url", None):
        return config.base_url
    return DEFAULT_BASE_URL


@click.command("login")
@click.option(
    "--scope",
    default=DEFAULT_SCOPES,
    show_default=True,
    help="OAuth scopes to request (space-separated).",
)
@click.option(
    "--no-browser",
    is_flag=True,
    help="Don't try to open a browser; print the authorize URL instead.",
)
@click.option(
    "--port",
    type=int,
    default=0,
    help="Bind a specific loopback port for the callback (0 = random).",
)
@click.option(
    "--force",
    is_flag=True,
    help="Overwrite an existing stored login without confirmation.",
)
@click.option(
    "--client-id",
    default=PUBLIC_CLIENT_ID,
    show_default=True,
    help="OAuth client ID to use for the browser flow.",
)
@click.option(
    "--authorize-url",
    envvar="VAINU_AUTHORIZE_BASE_URL",
    default=DEFAULT_AUTHORIZE_BASE_URL,
    show_default=True,
    help=(
        "Base URL for the browser authorize endpoint. Defaults to app.vainu.io "
        "(where the login UI lives) while token exchange still hits --base-url."
    ),
)
@click.pass_context
def login_command(
    ctx: click.Context,
    scope: str,
    no_browser: bool,
    port: int,
    force: bool,
    client_id: str,
    authorize_url: str,
) -> None:
    """Sign in via the browser and store tokens locally."""
    base_url = _base_url_from_config(ctx)
    store = TokenStore()
    existing = store.load()
    if existing and not force:
        account = existing.account or existing.client_id
        click.echo(
            f"Already logged in as {account} (via {store.backend}). "
            "Re-run with --force to replace the existing session.",
            err=True,
        )
        ctx.exit(0)
    creds = run_login(
        base_url=base_url,
        authorize_base_url=authorize_url,
        client_id=client_id,
        scope=scope,
        port=port,
        open_browser=not no_browser,
    )
    store.save(creds)
    who = creds.account or creds.client_id
    click.echo(f"Logged in as {who}. Credentials saved via {store.backend}.", err=True)


@click.command("logout")
@click.option(
    "--all",
    "revoke_all",
    is_flag=True,
    help="Also revoke the refresh token server-side.",
)
@click.pass_context
def logout_command(ctx: click.Context, revoke_all: bool) -> None:
    """Forget locally stored login. Optionally revoke server-side."""
    store = TokenStore()
    creds = store.load()
    if creds is None:
        click.echo("Not logged in.", err=True)
        ctx.exit(0)
    if revoke_all and creds.refresh_token:
        try:
            response = requests.post(
                f"{creds.base_url.rstrip('/')}{OAUTH_REVOKE_ENDPOINT}",
                data={
                    "token": creds.refresh_token,
                    "client_id": creds.client_id,
                    # OAuth RFC 7009 standard parameter value, not a credential.
                    "token_type_hint": "refresh_token",  # nosec B105
                },
                timeout=30,
            )
            if response.status_code >= 400:
                click.echo(
                    f"Server-side revoke failed ({response.status_code}): {response.text}",
                    err=True,
                )
        except requests.RequestException as exc:
            click.echo(f"Could not reach revoke endpoint: {exc}", err=True)
    store.clear()
    click.echo("Logged out.", err=True)


@click.command("status")
@click.option("--json", "as_json", is_flag=True, help="Emit JSON instead of human text.")
@click.pass_context
def status_command(ctx: click.Context, as_json: bool) -> None:
    """Show whether the CLI is logged in and basic session info."""
    store = TokenStore()
    creds = store.load()
    if creds is None:
        if as_json:
            click.echo(json.dumps({"logged_in": False}))
        else:
            click.echo("Not logged in.")
        ctx.exit(1)

    expires_iso = dt.datetime.fromtimestamp(creds.expires_at, tz=dt.UTC).isoformat()
    obtained_iso = dt.datetime.fromtimestamp(creds.obtained_at, tz=dt.UTC).isoformat()
    payload = {
        "logged_in": True,
        "account": creds.account,
        "client_id": creds.client_id,
        "base_url": creds.base_url,
        "scope": creds.scope,
        "access_token_expires_at": expires_iso,
        "obtained_at": obtained_iso,
        "access_token_expired": creds.is_expired(),
        "storage_backend": store.backend,
    }
    if as_json:
        click.echo(json.dumps(payload, indent=2))
        return
    click.echo(f"Logged in as: {creds.account or '<unknown>'}")
    click.echo(f"Client:       {creds.client_id}")
    click.echo(f"Base URL:     {creds.base_url}")
    click.echo(f"Scopes:       {creds.scope}")
    click.echo(f"Expires at:   {expires_iso}" + (" (EXPIRED)" if creds.is_expired() else ""))
    click.echo(f"Obtained at:  {obtained_iso}")
    click.echo(f"Storage:      {store.backend}")


@click.group("auth")
def auth_group() -> None:
    """Manage CLI authentication."""


auth_group.add_command(login_command, name="login")
auth_group.add_command(logout_command, name="logout")
auth_group.add_command(status_command, name="status")
