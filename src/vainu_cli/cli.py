"""Click-based CLI for the Vainu API."""

import asyncio
import json
import logging
import sys
from collections.abc import Callable
from dataclasses import dataclass
from functools import wraps
from time import perf_counter
from typing import Any, TypeVar, cast

import click

from vainu_cli._async_client import (
    VainuAPIBaseClient as AsyncBaseClient,
)
from vainu_cli._async_client import (
    VainuAPIKeyClient,
    VainuJWTAPIClient,
    VainuOAuthAPIClient,
)
from vainu_cli._sync_client import (
    VainuAPIBaseClient as SyncBaseClient,
)
from vainu_cli._sync_client import (
    VainuAPIKeySyncClient,
    VainuJWTSyncClient,
    VainuOAuthSyncClient,
)
from vainu_cli._version import __version__
from vainu_cli.common import RESPONSE_FORMATS, ResponseFormat

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


def _log_task_duration(task_name: str, start_time: float, success: bool) -> None:
    elapsed = perf_counter() - start_time
    status = "completed" if success else "failed"
    logger.debug("Task '%s' %s in %.3fs", task_name, status, elapsed)


def _timed_task(task_name: str) -> Callable[[F], F]:
    """Decorator that logs command execution time at DEBUG level."""

    def _decorator(func: F) -> F:
        @wraps(func)
        def _wrapper(*args: Any, **kwargs: Any) -> Any:
            start_time = perf_counter()
            success = False
            try:
                result = func(*args, **kwargs)
                success = True
                return result
            finally:
                _log_task_duration(task_name, start_time, success)

        return cast(F, _wrapper)

    return _decorator


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


def _make_sync_client(config: Config, language: str | None = None) -> SyncBaseClient:
    if config.auth_method == "apikey":
        if not config.api_key:
            raise click.ClickException("API key required. Use --api-key or set VAINU_API_KEY.")
        return VainuAPIKeySyncClient(
            api_key=config.api_key,
            base_url=config.base_url,
            language=language,
        )
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
            language=language,
        )
    if config.auth_method == "jwt":
        if not config.jwt_token:
            raise click.ClickException(
                "JWT authentication requires --jwt-token (or VAINU_JWT_REFRESH_TOKEN)."
            )
        return VainuJWTSyncClient(
            refresh_token=config.jwt_token,
            base_url=config.base_url,
            language=language,
        )
    raise click.ClickException(f"Unknown auth method: {config.auth_method!r}")


def _make_async_client(config: Config, language: str | None = None) -> AsyncBaseClient:
    if config.auth_method == "apikey":
        if not config.api_key:
            raise click.ClickException("API key required. Use --api-key or set VAINU_API_KEY.")
        return VainuAPIKeyClient(
            api_key=config.api_key,
            base_url=config.base_url,
            language=language,
        )
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
            language=language,
        )
    if config.auth_method == "jwt":
        if not config.jwt_token:
            raise click.ClickException(
                "JWT authentication requires --jwt-token (or VAINU_JWT_REFRESH_TOKEN)."
            )
        return VainuJWTAPIClient(
            refresh_token=config.jwt_token,
            base_url=config.base_url,
            language=language,
        )
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


def _write_output(data: dict | list | str, output: str | None) -> None:
    text = data if isinstance(data, str) else json.dumps(data, indent=2, ensure_ascii=False)
    if output:
        with open(output, "w") as fh:
            fh.write(text)
        click.echo(f"Written to {output}", err=True)
    else:
        click.echo(text)


def _option_query(func: F) -> F:
    return click.option("--query", default=None, help="Query string (e.g. '?country=FI').")(func)


def _option_payload(required: bool) -> Callable[[F], F]:
    kwargs: dict[str, Any] = {
        "required": required,
        "type": click.Path(),
        "help": "JSON payload file path, or '-' to read from stdin.",
    }
    if not required:
        kwargs["default"] = None
    return click.option(
        "--payload",
        "--payload-path",
        "payload_path",
        **kwargs,
    )


def _option_format(func: F) -> F:
    return click.option(
        "--format",
        "fmt",
        type=click.Choice(RESPONSE_FORMATS),
        default="json",
        show_default=True,
        help="Response format.",
    )(func)


def _option_language(func: F) -> F:
    return click.option(
        "--language",
        default=None,
        help="Language for the Accept-Language header.",
    )(func)


def _option_output(required: bool) -> Callable[[F], F]:
    help_text = "Output file (required)." if required else "Write result to file."
    kwargs: dict[str, Any] = {
        "required": required,
        "type": click.Path(),
        "help": help_text,
    }
    if not required:
        kwargs["default"] = None
    return click.option("--output", **kwargs)


def _option_filter_base(func: F) -> F:
    decorated = _option_format(func)
    decorated = _option_language(decorated)
    return decorated


def _option_poll_interval(func: F) -> F:
    return click.option(
        "--poll-interval", default=3, show_default=True, help="Poll interval in seconds."
    )(func)


def _option_timeout(func: F) -> F:
    return click.option(
        "--timeout", default=14400, show_default=True, help="Max seconds to wait for async job."
    )(func)


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
        vainu companies --query "?country=FI&business_id=FI01320292"
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


@main.command("companies")
@_option_query
@_option_payload(required=False)
@_option_filter_base
@_option_output(required=False)
@click.pass_obj
@_timed_task("companies")
def companies_search(
    config: Config,
    query: str | None,
    payload_path: str | None,
    fmt: ResponseFormat,
    language: str | None,
    output: str | None,
) -> None:
    """Fetch company data (synchronous paginated result)."""
    payload = _load_payload(query, payload_path)
    if config.async_mode:

        async def _run() -> dict:
            client = _make_async_client(config, language=language)
            try:
                return await client.companies(payload=payload, format=fmt)
            finally:
                await client.close()

        result = asyncio.run(_run())
    else:
        client = _make_sync_client(config, language=language)
        try:
            result = client.companies(payload=payload, format=fmt)
        finally:
            client.close()
    _write_output(result, output)


@main.command("companies-async")
@_option_query
@_option_payload(required=False)
@_option_filter_base
@_option_output(required=True)
@_option_poll_interval
@_option_timeout
@click.pass_obj
@_timed_task("companies-async")
def companies_export(
    config: Config,
    query: str | None,
    payload_path: str | None,
    fmt: ResponseFormat,
    language: str | None,
    output: str,
    poll_interval: int,
    timeout: int,
) -> None:
    """Export companies via async job — polls until complete and downloads to file."""
    payload = _load_payload(query, payload_path)

    async def _run() -> str | None:
        client = _make_async_client(config, language=language)
        client.ASYNC_POLL_INTERVAL = poll_interval
        try:
            async_result = await client.companies_async(payload=payload, format=fmt)
            downloaded = await async_result.download_to_file(output)
            return async_result.result_url if downloaded is False else None
        finally:
            await client.close()

    result_url = asyncio.run(_run())
    if result_url:
        click.echo(f"Result exists in result_url: {result_url}", err=True)
    else:
        click.echo(f"Export saved to {output}", err=True)


# ── organizations ────────────────────────────────────────────────────────────


@main.command("organizations")
@_option_payload(required=True)
@_option_filter_base
@_option_output(required=False)
@click.pass_obj
@_timed_task("organizations")
def organizations_search(
    config: Config,
    payload_path: str,
    fmt: ResponseFormat,
    language: str | None,
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
            client = _make_async_client(config, language=language)
            try:
                return await client.organizations(payload=payload, format=fmt)
            finally:
                await client.close()

        result = asyncio.run(_run())
    else:
        client = _make_sync_client(config, language=language)
        try:
            result = client.organizations(payload=payload, format=fmt)
        finally:
            client.close()
    _write_output(result, output)


@main.command("organizations-async")
@_option_payload(required=True)
@_option_filter_base
@_option_output(required=True)
@_option_poll_interval
@_option_timeout
@click.pass_obj
@_timed_task("organizations-async")
def organizations_export(
    config: Config,
    payload_path: str,
    fmt: ResponseFormat,
    language: str | None,
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

    async def _run() -> str | None:
        client = _make_async_client(config, language=language)
        client.ASYNC_POLL_INTERVAL = poll_interval
        try:
            async_result = await client.organizations_async(payload=payload, format=fmt)
            downloaded = await async_result.download_to_file(output)
            return async_result.result_url if downloaded is False else None
        finally:
            await client.close()

    result_url = asyncio.run(_run())
    if result_url:
        click.echo(f"Result exists in result_url: {result_url}", err=True)
    else:
        click.echo(f"Export saved to {output}", err=True)
