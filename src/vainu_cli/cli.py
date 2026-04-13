"""Click-based CLI for the Vainu API."""

import asyncio
import json
import logging
import sys
from dataclasses import dataclass

import click

from vainu_cli._async_client import (
    VainuAPIBaseClient as AsyncBaseClient,
)
from vainu_cli._async_client import (
    VainuAPIKeyClient,
    VainuOAuthAPIClient,
)
from vainu_cli._sync_client import (
    VainuAPIBaseClient as SyncBaseClient,
)
from vainu_cli._sync_client import (
    VainuAPIKeySyncClient,
    VainuOAuthSyncClient,
)
from vainu_cli._version import __version__

logger = logging.getLogger(__name__)


@dataclass
class Config:
    auth_method: str
    api_key: str | None
    client_id: str | None
    client_secret: str | None
    jwt_token: str | None
    base_url: str
    async_mode: bool
    verbose: bool


def _make_sync_client(config: Config) -> SyncBaseClient:
    if config.auth_method == "apikey":
        if not config.api_key:
            raise click.ClickException("API key required. Use --api-key or set VAINU_API_KEY.")
        return VainuAPIKeySyncClient(api_key=config.api_key, base_url=config.base_url)
    if config.auth_method == "oauth":
        if not config.client_id or not config.client_secret:
            raise click.ClickException(
                "OAuth requires --client-id and --client-secret "
                "(or VAINU_CLIENT_ID / VAINU_CLIENT_SECRET)."
            )
        return VainuOAuthSyncClient(
            client_id=config.client_id,
            client_secret=config.client_secret,
            base_url=config.base_url,
        )
    if config.auth_method == "jwt":
        raise click.ClickException("JWT authentication is not yet implemented.")
    raise click.ClickException(f"Unknown auth method: {config.auth_method!r}")


def _make_async_client(config: Config) -> AsyncBaseClient:
    if config.auth_method == "apikey":
        if not config.api_key:
            raise click.ClickException("API key required. Use --api-key or set VAINU_API_KEY.")
        return VainuAPIKeyClient(api_key=config.api_key, base_url=config.base_url)
    if config.auth_method == "oauth":
        if not config.client_id or not config.client_secret:
            raise click.ClickException(
                "OAuth requires --client-id and --client-secret "
                "(or VAINU_CLIENT_ID / VAINU_CLIENT_SECRET)."
            )
        return VainuOAuthAPIClient(
            client_id=config.client_id,
            client_secret=config.client_secret,
            base_url=config.base_url,
        )
    if config.auth_method == "jwt":
        raise click.ClickException("JWT authentication is not yet implemented.")
    raise click.ClickException(f"Unknown auth method: {config.auth_method!r}")


def _load_payload(query: str | None, payload_path: str | None) -> str | dict:
    """Resolve query string or JSON payload file/stdin into a payload value."""
    if query and payload_path:
        raise click.UsageError("--query and --payload are mutually exclusive.")
    if not query and not payload_path:
        raise click.UsageError("Provide either --query or --payload.")
    if query:
        return query
    raw = sys.stdin.read() if payload_path == "-" else open(payload_path).read()  # noqa: SIM115
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise click.UsageError(f"--payload is not valid JSON: {exc}") from exc


def _write_output(data: dict | list, output: str | None) -> None:
    text = json.dumps(data, indent=2, ensure_ascii=False)
    if output:
        with open(output, "w") as fh:
            fh.write(text)
        click.echo(f"Written to {output}", err=True)
    else:
        click.echo(text)


# ── Root group ──────────────────────────────────────────────────────────────


@click.group()
@click.option(
    "--auth-method",
    default="apikey",
    type=click.Choice(["apikey", "oauth", "jwt"]),
    show_default=True,
    help="Authentication method.",
)
@click.option(
    "--api-key",
    envvar="VAINU_API_KEY",
    default=None,
    hide_input=True,
    help="Static API key (or set VAINU_API_KEY).",
)
@click.option(
    "--client-id",
    envvar="VAINU_CLIENT_ID",
    default=None,
    help="OAuth client ID (or set VAINU_CLIENT_ID).",
)
@click.option(
    "--client-secret",
    envvar="VAINU_CLIENT_SECRET",
    default=None,
    hide_input=True,
    help="OAuth client secret (or set VAINU_CLIENT_SECRET).",
)
@click.option(
    "--jwt-token",
    envvar="VAINU_JWT_REFRESH_TOKEN",
    default=None,
    hide_input=True,
    help="JWT refresh token (or set VAINU_JWT_REFRESH_TOKEN).",
)
@click.option(
    "--base-url",
    envvar="VAINU_BASE_URL",
    default="https://api.vainu.io/api",
    show_default=True,
    help="API base URL override.",
)
@click.option("--async-mode/--no-async-mode", default=False, help="Use async client for search.")
@click.option("-v", "--verbose", is_flag=True, help="Enable DEBUG logging.")
@click.version_option(__version__, prog_name="vainu")
@click.pass_context
def main(
    ctx: click.Context,
    auth_method: str,
    api_key: str | None,
    client_id: str | None,
    client_secret: str | None,
    jwt_token: str | None,
    base_url: str,
    async_mode: bool,
    verbose: bool,
) -> None:
    """Vainu company data API — command-line interface.

    Authenticate via API key (default), OAuth 2.0 client credentials, or JWT.
    Credentials are read from CLI flags or environment variables.

    \b
    Quick start:
        export VAINU_API_KEY=your-key
        vainu companies search --query "?country=FI&business_id=FI01320292"
    """
    if verbose:
        logging.basicConfig(level=logging.DEBUG)
    ctx.ensure_object(dict)
    ctx.obj = Config(
        auth_method=auth_method,
        api_key=api_key,
        client_id=client_id,
        client_secret=client_secret,
        jwt_token=jwt_token,
        base_url=base_url,
        async_mode=async_mode,
        verbose=verbose,
    )


# ── companies ────────────────────────────────────────────────────────────────


@main.group()
def companies() -> None:
    """Search and export company data."""


@companies.command("search")
@click.option("--query", default=None, help="Query string (e.g. '?country=FI').")
@click.option(
    "--payload",
    "payload_path",
    default=None,
    type=click.Path(),
    help="JSON payload file path, or '-' to read from stdin.",
)
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["json", "csv", "jsonl"]),
    default="json",
    show_default=True,
    help="Response format.",
)
@click.option("--output", default=None, type=click.Path(), help="Write result to file.")
@click.pass_obj
def companies_search(
    config: Config,
    query: str | None,
    payload_path: str | None,
    fmt: str,
    output: str | None,
) -> None:
    """Fetch company data (synchronous paginated result)."""
    payload = _load_payload(query, payload_path)
    if config.async_mode:

        async def _run() -> dict:
            client = _make_async_client(config)
            try:
                return await client.companies(payload=payload, format=fmt)
            finally:
                await client.close()

        result = asyncio.run(_run())
    else:
        client = _make_sync_client(config)
        try:
            result = client.companies(payload=payload, format=fmt)
        finally:
            client.close()
    _write_output(result, output)


@companies.command("export")
@click.option("--query", default=None, help="Query string (e.g. '?country=FI').")
@click.option(
    "--payload",
    "payload_path",
    default=None,
    type=click.Path(),
    help="JSON payload file path, or '-' to read from stdin.",
)
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["json", "csv", "jsonl"]),
    default="json",
    show_default=True,
    help="Export format.",
)
@click.option("--output", required=True, type=click.Path(), help="Output file (required).")
@click.option("--poll-interval", default=3, show_default=True, help="Poll interval in seconds.")
@click.option(
    "--timeout", default=14400, show_default=True, help="Max seconds to wait for async job."
)
@click.pass_obj
def companies_export(
    config: Config,
    query: str | None,
    payload_path: str | None,
    fmt: str,
    output: str,
    poll_interval: int,
    timeout: int,
) -> None:
    """Export companies via async job — polls until complete and downloads to file."""
    payload = _load_payload(query, payload_path)

    async def _run() -> None:
        client = _make_async_client(config)
        client.ASYNC_POLL_INTERVAL = poll_interval
        try:
            async_result = await client.companies_async(payload=payload, format=fmt)
            await async_result.download_to_file(output)
        finally:
            await client.close()

    asyncio.run(_run())
    click.echo(f"Export saved to {output}", err=True)


# ── organizations ────────────────────────────────────────────────────────────


@main.group()
def organizations() -> None:
    """Search and export organization data."""


@organizations.command("search")
@click.option(
    "--payload",
    "payload_path",
    required=True,
    type=click.Path(),
    help="JSON payload file path, or '-' to read from stdin.",
)
@click.option("--output", default=None, type=click.Path(), help="Write result to file.")
@click.pass_obj
def organizations_search(
    config: Config,
    payload_path: str,
    output: str | None,
) -> None:
    """Fetch organization data (POST with JSON payload)."""
    raw = sys.stdin.read() if payload_path == "-" else open(payload_path).read()  # noqa: SIM115
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise click.UsageError(f"--payload is not valid JSON: {exc}") from exc

    if config.async_mode:

        async def _run() -> dict:
            client = _make_async_client(config)
            try:
                return await client.organizations(payload=payload)
            finally:
                await client.close()

        result = asyncio.run(_run())
    else:
        client = _make_sync_client(config)
        try:
            result = client.organizations(payload=payload)
        finally:
            client.close()
    _write_output(result, output)


@organizations.command("export")
@click.option(
    "--payload",
    "payload_path",
    required=True,
    type=click.Path(),
    help="JSON payload file path, or '-' to read from stdin.",
)
@click.option("--output", required=True, type=click.Path(), help="Output file (required).")
@click.option("--poll-interval", default=3, show_default=True, help="Poll interval in seconds.")
@click.option(
    "--timeout", default=14400, show_default=True, help="Max seconds to wait for async job."
)
@click.pass_obj
def organizations_export(
    config: Config,
    payload_path: str,
    output: str,
    poll_interval: int,
    timeout: int,
) -> None:
    """Export organizations via async job — polls until complete and downloads to file."""
    raw = sys.stdin.read() if payload_path == "-" else open(payload_path).read()  # noqa: SIM115
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise click.UsageError(f"--payload is not valid JSON: {exc}") from exc

    async def _run() -> None:
        client = _make_async_client(config)
        client.ASYNC_POLL_INTERVAL = poll_interval
        try:
            async_result = await client.organizations_async(payload=payload)
            await async_result.download_to_file(output)
        finally:
            await client.close()

    asyncio.run(_run())
    click.echo(f"Export saved to {output}", err=True)
