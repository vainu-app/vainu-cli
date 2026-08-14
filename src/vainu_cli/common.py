"""Shared constants and types used by both sync and async clients."""

import enum
import http
from collections.abc import Iterator
from typing import Literal, Protocol, TypeAlias

DEFAULT_BASE_URL = "https://api.vainu.io/api"
JWT_REFRESH_ENDPOINT_PATH = "/token_authentication/refresh/"
ResponseFormat: TypeAlias = Literal["json", "csv", "jsonl"]
DEFAULT_RESPONSE_FORMAT: ResponseFormat = "json"
RESPONSE_FORMATS: tuple[ResponseFormat, ...] = ("json", "csv", "jsonl")
# The Signals API renders json and jsonl only, so csv is not offered there.
SIGNALS_RESPONSE_FORMATS: tuple[ResponseFormat, ...] = ("json", "jsonl")
# The Enrichment Agent API renders json and jsonl only.
ENRICHMENT_RESPONSE_FORMATS: tuple[ResponseFormat, ...] = ("json", "jsonl")
# List Management APIs render json and jsonl only.
LISTS_RESPONSE_FORMATS: tuple[ResponseFormat, ...] = ("json", "jsonl")
# Line-oriented formats, the only ones a response body can be split on newlines.
STREAMABLE_FORMATS: tuple[ResponseFormat, ...] = ("csv", "jsonl")
DEFAULT_STREAM_FORMAT: ResponseFormat = "jsonl"
# Per-request HTTP timeout (connect + read) for every client. Slow synchronous
# searches stream their body for well over a minute, so keep this above the
# API's own 120s ceiling rather than racing it.
DEFAULT_TIMEOUT_SECONDS = 121

# OAuth / login
OAUTH_AUTHORIZE_ENDPOINT = "/oauth/authorize/"
OAUTH_TOKEN_ENDPOINT = "/oauth/token/"  # noqa: S105  # nosec B105  — URL path, not a credential
OAUTH_REVOKE_ENDPOINT = "/oauth/revoke_token/"
# This client_id is intentionally checked into source. The CLI is a "public"
# OAuth client (no client_secret) per RFC 8252 — the id is a public identifier,
# not a credential. Security comes from PKCE (S256), the loopback redirect-URI
# allowlist registered on the Vainu OAuth Application, and the user consent
# screen. Compare: `gh`, `gcloud`, `aws sso` all ship hardcoded public ids.
PUBLIC_CLIENT_ID = "cli.vainu.com-UxPOeToRRg39bHoDfom6wgdVGIaAygwhx9TXja4l"
PUBLIC_REDIRECT_URI = "http://127.0.0.1/callback"
DEFAULT_SCOPES = "vainu:api offline_access"
# The browser-facing authorize URL has to live on app.vainu.io because the
# login UI is only mounted there; api.vainu.io has only API paths. Token
# exchange (server-to-server POST) goes to the CLI's base_url as usual.
DEFAULT_AUTHORIZE_BASE_URL = "https://app.vainu.io/api"
KEYRING_SERVICE = "vainu-cli"
KEYRING_USERNAME = "default"
CONFIG_APP_NAME = "vainu"
CONFIG_APP_AUTHOR = "vainu"


class ResponseLike(Protocol):
    text: str

    def json(self) -> dict: ...


def parse_response(response: ResponseLike, format: ResponseFormat) -> dict | list | str:
    if format == "json":
        return response.json()
    return response.text


def ensure_streamable(format: ResponseFormat) -> None:
    """Reject formats that cannot be consumed one line at a time.

    A `json` response is a single document — the array or page object is only
    valid once the last byte lands, so there is nothing to hand over early.
    """
    if format not in STREAMABLE_FORMATS:
        raise ValueError(
            f"format={format!r} cannot be streamed. Choose one of {', '.join(STREAMABLE_FORMATS)}."
        )


def lines_from_text(text: str) -> Iterator[str]:
    """Split an already-read body into non-empty lines."""
    for line in text.splitlines():
        if line:
            yield line


def companies_request(
    payload: dict | str,
    format: ResponseFormat,
) -> tuple[http.HTTPMethod, str, dict | None]:
    """Resolve the companies endpoint call for a dict (POST) or query-string (GET) payload.

    Shared so the buffered and streaming paths cannot drift apart.
    """
    path = "/v2/companies/"
    if isinstance(payload, dict):
        return http.HTTPMethod.POST, f"{path}?format={format}", payload
    if isinstance(payload, str):
        return http.HTTPMethod.GET, f"{path}{payload}&format={format}", None
    raise ValueError("payload must be str or dict")


class AsyncJobState(enum.StrEnum):
    ACCEPTED = "accepted"
    COMPLETED = "completed"
    FAILURE = "failure"
    PARTIAL_FAILURE_COMPLETE = "partial_failure_complete"
    PARTIAL_FAILURE_INCOMPLETE = "partial_failure_incomplete"
    PROCESS = "process"
    STOPPED = "stopped"
