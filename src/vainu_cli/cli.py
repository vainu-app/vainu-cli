"""Click-based CLI for the Vainu API."""

import asyncio
import json
import logging
import os
import sys
import time
from collections.abc import AsyncIterable, Callable, Iterable
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
from vainu_cli.auth.browser_client import (
    VainuBrowserAuthAPIClient,
    VainuBrowserAuthSyncClient,
)
from vainu_cli.auth.commands import (
    auth_group,
    login_command,
    logout_command,
)
from vainu_cli.auth.storage import StoredCredentials, TokenStore
from vainu_cli.common import (
    DEFAULT_TIMEOUT_SECONDS,
    ENRICHMENT_RESPONSE_FORMATS,
    PUBLIC_CLIENT_ID,
    RESPONSE_FORMATS,
    SIGNALS_RESPONSE_FORMATS,
    STREAMABLE_FORMATS,
    ResponseFormat,
)

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
    stored: StoredCredentials | None = None
    store: TokenStore | None = None


def _make_sync_client(
    config: Config,
    language: str | None = None,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> SyncBaseClient:
    if config.auth_method == "apikey":
        if not config.api_key:
            raise click.ClickException(
                "API key required. Use --api-key, set VAINU_API_KEY, or run `vainu login`."
            )
        return VainuAPIKeySyncClient(
            api_key=config.api_key,
            base_url=config.base_url,
            language=language,
            timeout=timeout,
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
            timeout=timeout,
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
            timeout=timeout,
        )
    if config.auth_method == "browser":
        if config.stored is None:
            raise click.ClickException("No stored credentials. Run `vainu login` first.")
        return VainuBrowserAuthSyncClient(
            stored=config.stored,
            store=config.store,
            base_url=config.base_url,
            language=language,
            timeout=timeout,
        )
    raise click.ClickException(f"Unknown auth method: {config.auth_method!r}")


def _make_async_client(
    config: Config,
    language: str | None = None,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> AsyncBaseClient:
    if config.auth_method == "apikey":
        if not config.api_key:
            raise click.ClickException(
                "API key required. Use --api-key, set VAINU_API_KEY, or run `vainu login`."
            )
        return VainuAPIKeyClient(
            api_key=config.api_key,
            base_url=config.base_url,
            language=language,
            timeout=timeout,
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
            timeout=timeout,
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
            timeout=timeout,
        )
    if config.auth_method == "browser":
        if config.stored is None:
            raise click.ClickException("No stored credentials. Run `vainu login` first.")
        return VainuBrowserAuthAPIClient(
            stored=config.stored,
            store=config.store,
            base_url=config.base_url,
            language=language,
            timeout=timeout,
        )
    raise click.ClickException(f"Unknown auth method: {config.auth_method!r}")


def _resolve_credentials(
    *,
    auth_method: str | None,
    api_key: str | None,
    client_id: str | None,
    client_secret: str | None,
    jwt_token: str | None,
    base_url: str,
) -> tuple[str, StoredCredentials | None, TokenStore | None]:
    """Resolve the effective auth method and (optionally) stored credentials.

    Precedence: explicit flag/env → existing env vars → stored-cred env vars →
    persisted credentials → "apikey" default.
    """
    if auth_method:
        return auth_method, None, None
    if api_key:
        return "apikey", None, None
    if client_id and client_secret:
        return "oauth", None, None
    if jwt_token:
        return "jwt", None, None

    env_access = os.environ.get("VAINU_ACCESS_TOKEN")
    env_refresh = os.environ.get("VAINU_REFRESH_TOKEN")
    if env_access:
        try:
            expires_at = float(os.environ.get("VAINU_TOKEN_EXPIRES_AT", "0") or 0)
        except ValueError:
            expires_at = 0.0
        if expires_at <= 0:
            # Assume a short remaining lifetime; refresh path will fire on use.
            expires_at = time.time() + 300
        stored = StoredCredentials(
            access_token=env_access,
            refresh_token=env_refresh or "",
            expires_at=expires_at,
            scope=os.environ.get("VAINU_SCOPE", ""),
            client_id=os.environ.get("VAINU_CLIENT_ID") or PUBLIC_CLIENT_ID,
            base_url=base_url,
            account=None,
            obtained_at=time.time(),
        )
        return "browser", stored, None  # no on-disk store — env-driven session

    store = TokenStore()
    stored = store.load()
    if stored is not None:
        return "browser", stored, store

    return "apikey", None, None


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


def _load_payload_file(payload_path: str) -> dict:
    """Read a required JSON payload from a file path, or '-' for stdin."""
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


def _write_output_stream(lines: Iterable[str], output: str | None) -> None:
    """Write lines as they arrive, so a slow export reports progress as it runs."""
    if output:
        with open(output, "w") as fh:
            for line in lines:
                fh.write(f"{line}\n")
        click.echo(f"Written to {output}", err=True)
    else:
        for line in lines:
            click.echo(line)


async def _write_output_stream_async(lines: AsyncIterable[str], output: str | None) -> None:
    if output:
        with open(output, "w") as fh:
            async for line in lines:
                fh.write(f"{line}\n")
        click.echo(f"Written to {output}", err=True)
    else:
        async for line in lines:
            click.echo(line)


def _streamable(formats: tuple[ResponseFormat, ...]) -> tuple[ResponseFormat, ...]:
    """The line-oriented subset of a command's formats — signals offer no csv."""
    return tuple(fmt for fmt in formats if fmt in STREAMABLE_FORMATS)


def _resolve_stream(
    stream: bool | None,
    fmt: ResponseFormat,
    formats: tuple[ResponseFormat, ...] = RESPONSE_FORMATS,
) -> bool:
    """Decide whether to stream: on by default for line-oriented formats.

    `stream` is None when neither --stream nor --no-stream was passed.
    """
    streamable = _streamable(formats)
    if stream is None:
        return fmt in streamable
    if stream and fmt not in streamable:
        raise click.UsageError(
            f"--stream requires --format {' or '.join(streamable)} — "
            f"a {fmt} response is a single document and cannot be split into lines."
        )
    return stream


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


def _option_enrichment_format(func: F) -> F:
    return click.option(
        "--format",
        "fmt",
        type=click.Choice(ENRICHMENT_RESPONSE_FORMATS),
        default="json",
        show_default=True,
        help="Response format.",
    )(func)


def _option_signals_format(func: F) -> F:
    return click.option(
        "--format",
        "fmt",
        type=click.Choice(SIGNALS_RESPONSE_FORMATS),
        default="json",
        show_default=True,
        help="Response format.",
    )(func)


def _option_stream(
    formats: tuple[ResponseFormat, ...] = RESPONSE_FORMATS,
) -> Callable[[F], F]:
    streamable = " or ".join(_streamable(formats))
    return click.option(
        "--stream/--no-stream",
        default=None,
        help=f"Emit each line as it arrives instead of buffering the whole body. On by default "
        f"for --format {streamable}; pass --no-stream to buffer instead.",
    )


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


def _option_signals_base(func: F) -> F:
    decorated = _option_signals_format(func)
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
    envvar="VAINU_AUTH_METHOD",
    default=None,
    type=click.Choice(["apikey", "oauth", "jwt", "browser"]),
    help=(
        "Authentication method. Defaults to auto-detect: explicit flags > env vars > "
        "credentials saved by `vainu login` > API key."
    ),
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
    auth_method: str | None,
    api_key: str | None,
    client_id: str | None,
    client_secret: str | None,
    jwt_token: str | None,
    base_url: str,
    async_mode: bool,
    verbose: bool,
) -> None:
    """Vainu company data API — command-line interface.

    Run `vainu login` to sign in via the browser, or pass an API key /
    OAuth client / JWT token via flags or environment variables.

    \b
    Quick start:
        vainu login
        vainu companies --query "?country=FI&business_id=FI01320292"

    \b
    Or with an API key:
        export VAINU_API_KEY=your-key
        vainu companies --query "?country=FI"
    """
    if verbose:
        logging.basicConfig(level=logging.DEBUG)
    resolved_method, stored, store = _resolve_credentials(
        auth_method=auth_method,
        api_key=api_key,
        client_id=client_id,
        client_secret=client_secret,
        jwt_token=jwt_token,
        base_url=base_url,
    )
    ctx.ensure_object(dict)
    ctx.obj = Config(
        auth_method=resolved_method,
        api_key=api_key,
        client_id=client_id,
        client_secret=client_secret,
        jwt_token=jwt_token,
        base_url=base_url,
        async_mode=async_mode,
        verbose=verbose,
        stored=stored,
        store=store,
    )


# ── companies ────────────────────────────────────────────────────────────────


@main.command("companies")
@_option_query
@_option_payload(required=False)
@_option_filter_base
@_option_stream()
@_option_output(required=False)
@click.pass_obj
@_timed_task("companies")
def companies_search(
    config: Config,
    query: str | None,
    payload_path: str | None,
    fmt: ResponseFormat,
    language: str | None,
    stream: bool | None,
    output: str | None,
) -> None:
    """Fetch company data (synchronous paginated result)."""
    stream = _resolve_stream(stream, fmt)
    payload = _load_payload(query, payload_path)

    if stream:
        if config.async_mode:

            async def _run_stream() -> None:
                client = _make_async_client(config, language=language)
                try:
                    async with client.stream_companies(payload=payload, format=fmt) as lines:
                        await _write_output_stream_async(lines, output)
                finally:
                    await client.close()

            asyncio.run(_run_stream())
        else:
            client = _make_sync_client(config, language=language)
            try:
                with client.stream_companies(payload=payload, format=fmt) as lines:
                    _write_output_stream(lines, output)
            finally:
                client.close()
        return

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
@_option_stream()
@_option_output(required=False)
@click.pass_obj
@_timed_task("organizations")
def organizations_search(
    config: Config,
    payload_path: str,
    fmt: ResponseFormat,
    language: str | None,
    stream: bool | None,
    output: str | None,
) -> None:
    """Fetch organization data (POST with JSON payload)."""
    stream = _resolve_stream(stream, fmt)
    payload = _load_payload_file(payload_path)

    if stream:
        if config.async_mode:

            async def _run_stream() -> None:
                client = _make_async_client(config, language=language)
                try:
                    async with client.stream_organizations(payload=payload, format=fmt) as lines:
                        await _write_output_stream_async(lines, output)
                finally:
                    await client.close()

            asyncio.run(_run_stream())
        else:
            client = _make_sync_client(config, language=language)
            try:
                with client.stream_organizations(payload=payload, format=fmt) as lines:
                    _write_output_stream(lines, output)
            finally:
                client.close()
        return

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
    payload = _load_payload_file(payload_path)

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


# ── enrichment agent ─────────────────────────────────────────────────────────

ENRICHMENT_AGENT_REQUIRED_KEYS = ("prompt", "database", "business_id")


def _enrichment_agent_payload(
    payload_path: str | None,
    prompt: str | None,
    database: str | None,
    business_id: str | None,
    refresh: bool | None,
) -> dict:
    """Build the request body from a payload file, with explicit flags layered on top.

    That order is what makes a saved payload reusable: keep the prompt id and
    database in a file and vary only `--business-id` per run.
    """
    payload = _load_payload_file(payload_path) if payload_path else {}
    if not isinstance(payload, dict):
        raise click.UsageError("--payload must contain a JSON object for enrichment-agent.")
    overrides = {
        "prompt": prompt,
        "database": database,
        "business_id": business_id,
        "refresh": refresh,
    }
    payload.update({key: value for key, value in overrides.items() if value is not None})
    missing = [key for key in ENRICHMENT_AGENT_REQUIRED_KEYS if not payload.get(key)]
    if missing:
        flags = ", ".join(f"--{key.replace('_', '-')}" for key in missing)
        raise click.UsageError(
            f"enrichment-agent needs {flags} — pass the flag(s) or set the same keys in --payload."
        )
    return payload


@main.command("enrichment-agent")
@click.option(
    "--prompt",
    default=None,
    help="Enrichment agent prompt id, as created in the Vainu UI.",
)
@click.option("--business-id", default=None, help="Company business id, e.g. FI23365096.")
@click.option("--database", default=None, help="Country database, e.g. FI, SE, NO or DK.")
@click.option(
    "--refresh/--no-refresh",
    default=None,
    help="Re-run the prompt instead of reusing a cached answer. Re-running spends "
    "Vainu agent credits and is much slower, so the API reuses the cache by default.",
)
@_option_payload(required=False)
@_option_enrichment_format
@_option_language
@click.option(
    "--request-timeout",
    default=DEFAULT_TIMEOUT_SECONDS,
    show_default=True,
    type=int,
    help="HTTP timeout in seconds. Raise it for an uncached run — the agent researches "
    "the company on the spot, which can take minutes.",
)
@_option_output(required=False)
@click.pass_obj
@_timed_task("enrichment-agent")
def enrichment_agent_run(
    config: Config,
    prompt: str | None,
    business_id: str | None,
    database: str | None,
    refresh: bool | None,
    payload_path: str | None,
    fmt: ResponseFormat,
    language: str | None,
    request_timeout: int,
    output: str | None,
) -> None:
    """Run an enrichment agent prompt against one company.

    The prompt is built in the Vainu UI; this sends its id together with a
    company and returns the prompt's own fields under `response`.

    \b
    Example:
        vainu enrichment-agent --prompt 12345 --database FI --business-id FI23365096
    """
    payload = _enrichment_agent_payload(payload_path, prompt, database, business_id, refresh)

    if config.async_mode:

        async def _run() -> dict | str:
            client = _make_async_client(config, language=language, timeout=request_timeout)
            try:
                return await client.enrichment_agent(payload=payload, format=fmt)
            finally:
                await client.close()

        result = asyncio.run(_run())
    else:
        client = _make_sync_client(config, language=language, timeout=request_timeout)
        try:
            result = client.enrichment_agent(payload=payload, format=fmt)
        finally:
            client.close()
    _write_output(result, output)


# ── signals ──────────────────────────────────────────────────────────────────


@main.command("signals-news")
@_option_payload(required=True)
@_option_signals_base
@_option_stream(SIGNALS_RESPONSE_FORMATS)
@_option_output(required=False)
@click.pass_obj
@_timed_task("signals-news")
def signals_news_search(
    config: Config,
    payload_path: str,
    fmt: ResponseFormat,
    language: str | None,
    stream: bool | None,
    output: str | None,
) -> None:
    """Fetch news signals (POST with JSON payload)."""
    stream = _resolve_stream(stream, fmt, SIGNALS_RESPONSE_FORMATS)
    payload = _load_payload_file(payload_path)

    if stream:
        if config.async_mode:

            async def _run_stream() -> None:
                client = _make_async_client(config, language=language)
                try:
                    async with client.stream_signals_news(payload=payload, format=fmt) as lines:
                        await _write_output_stream_async(lines, output)
                finally:
                    await client.close()

            asyncio.run(_run_stream())
        else:
            client = _make_sync_client(config, language=language)
            try:
                with client.stream_signals_news(payload=payload, format=fmt) as lines:
                    _write_output_stream(lines, output)
            finally:
                client.close()
        return

    if config.async_mode:

        async def _run() -> list | str:
            client = _make_async_client(config, language=language)
            try:
                return await client.signals_news(payload=payload, format=fmt)
            finally:
                await client.close()

        result = asyncio.run(_run())
    else:
        client = _make_sync_client(config, language=language)
        try:
            result = client.signals_news(payload=payload, format=fmt)
        finally:
            client.close()
    _write_output(result, output)


@main.command("signals-data-changes")
@_option_payload(required=True)
@_option_signals_base
@_option_stream(SIGNALS_RESPONSE_FORMATS)
@_option_output(required=False)
@click.pass_obj
@_timed_task("signals-data-changes")
def signals_data_changes_search(
    config: Config,
    payload_path: str,
    fmt: ResponseFormat,
    language: str | None,
    stream: bool | None,
    output: str | None,
) -> None:
    """Fetch data-change signals (POST with JSON payload)."""
    stream = _resolve_stream(stream, fmt, SIGNALS_RESPONSE_FORMATS)
    payload = _load_payload_file(payload_path)

    if stream:
        if config.async_mode:

            async def _run_stream() -> None:
                client = _make_async_client(config, language=language)
                try:
                    async with client.stream_signals_data_changes(
                        payload=payload, format=fmt
                    ) as lines:
                        await _write_output_stream_async(lines, output)
                finally:
                    await client.close()

            asyncio.run(_run_stream())
        else:
            client = _make_sync_client(config, language=language)
            try:
                with client.stream_signals_data_changes(payload=payload, format=fmt) as lines:
                    _write_output_stream(lines, output)
            finally:
                client.close()
        return

    if config.async_mode:

        async def _run() -> list | str:
            client = _make_async_client(config, language=language)
            try:
                return await client.signals_data_changes(payload=payload, format=fmt)
            finally:
                await client.close()

        result = asyncio.run(_run())
    else:
        client = _make_sync_client(config, language=language)
        try:
            result = client.signals_data_changes(payload=payload, format=fmt)
        finally:
            client.close()
    _write_output(result, output)


# ── auth (login / logout / status) ───────────────────────────────────────────

main.add_command(auth_group, name="auth")
main.add_command(login_command, name="login")
main.add_command(logout_command, name="logout")
