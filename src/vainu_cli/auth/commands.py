"""`vainu login`, `vainu logout`, `vainu auth status` commands."""

from __future__ import annotations

import datetime as dt
import json
import logging
from urllib.parse import urlparse

import click
import requests

from vainu_cli.auth.oauth_flow import run_login
from vainu_cli.auth.storage import TokenStore, cached_token_usernames, clear_all_cached_tokens
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


def _resolve_authorize_url(authorize_url: str | None, base_url: str) -> str:
    """Pick the host for the browser authorize leg.

    An explicit `--authorize-url` (or `VAINU_AUTHORIZE_BASE_URL`) always wins.
    Otherwise an overridden `--base-url` — a dev server, a staging host — is
    assumed to serve the login UI too; only the production default falls back
    to app.vainu.io.
    """
    if authorize_url:
        return authorize_url
    if base_url.rstrip("/") != DEFAULT_BASE_URL.rstrip("/"):
        return base_url
    return DEFAULT_AUTHORIZE_BASE_URL


def _warn_on_split_hosts(authorize_url: str, base_url: str) -> None:
    """Warn when the code is issued by one host and redeemed at another."""
    authorize_host = urlparse(authorize_url).netloc
    token_host = urlparse(base_url).netloc
    if authorize_host == token_host:
        return
    is_default_pair = authorize_url.rstrip("/") == DEFAULT_AUTHORIZE_BASE_URL.rstrip(
        "/"
    ) and base_url.rstrip("/") == DEFAULT_BASE_URL.rstrip("/")
    if is_default_pair:
        return
    click.echo(
        f"Warning: authorizing at {authorize_host} but exchanging the code at "
        f"{token_host}. Unless those hosts share an OAuth database the exchange "
        "will fail with invalid_grant — pass --base-url to match.",
        err=True,
    )


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
    default=None,
    help=(
        "Base URL for the browser authorize endpoint. Defaults to app.vainu.io "
        f"(where the login UI lives) when --base-url is the default {DEFAULT_BASE_URL}, "
        "and to --base-url otherwise."
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
    authorize_url: str | None,
) -> None:
    """Sign in via the browser and store tokens locally."""
    base_url = _base_url_from_config(ctx)
    authorize_url = _resolve_authorize_url(authorize_url, base_url)
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
    _warn_on_split_hosts(authorize_url, base_url)
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
    # Cached client-credentials tokens are a separate credential set from the
    # browser login, so they go whether or not anyone is logged in.
    cached = clear_all_cached_tokens()
    if cached:
        click.echo(f"Discarded {cached} cached access token(s).", err=True)
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
    cached_tokens = len(cached_token_usernames())
    if creds is None:
        if as_json:
            click.echo(json.dumps({"logged_in": False, "cached_access_tokens": cached_tokens}))
        else:
            click.echo("Not logged in.")
            if cached_tokens:
                click.echo(f"Cached access tokens: {cached_tokens} (client credentials)")
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
        "cached_access_tokens": cached_tokens,
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
    if cached_tokens:
        click.echo(f"Cached tokens: {cached_tokens} (client credentials)")


@click.group("auth")
def auth_group() -> None:
    """Manage CLI authentication."""


auth_group.add_command(login_command, name="login")
auth_group.add_command(logout_command, name="logout")
auth_group.add_command(status_command, name="status")
