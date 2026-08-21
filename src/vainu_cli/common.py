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
# Statuses that say "ask again later", not "your request was wrong". A long
# export routinely draws a 504 from the load balancer in front of the API while
# the job itself keeps running, so a poll loop has to survive them.
RETRYABLE_STATUS_CODES = frozenset(
    {
        http.HTTPStatus.REQUEST_TIMEOUT,
        http.HTTPStatus.TOO_MANY_REQUESTS,
        http.HTTPStatus.INTERNAL_SERVER_ERROR,
        http.HTTPStatus.BAD_GATEWAY,
        http.HTTPStatus.SERVICE_UNAVAILABLE,
        http.HTTPStatus.GATEWAY_TIMEOUT,
    }
)
# Consecutive poll failures back off exponentially from the poll interval, so a
# gateway that is unhappy for a minute does not burn the retry budget in
# seconds. Capped so a long job keeps checking in at a sane rate.
POLL_RETRY_MAX_BACKOFF_SECONDS = 60


def poll_retry_delay(poll_interval: float, consecutive_errors: int) -> float:
    """Seconds to wait before poll retry number `consecutive_errors` (1-based)."""
    delay = poll_interval * 2 ** (consecutive_errors - 1)
    return min(delay, POLL_RETRY_MAX_BACKOFF_SECONDS)


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


# The count endpoint reports progress under its own `status` vocabulary —
# error / process / ready / scheduled — which is unrelated to AsyncJobState above
# (that one belongs to the /async/ job endpoints and is keyed on `state`).
COUNT_PENDING_STATUSES: frozenset[str] = frozenset({"scheduled", "process"})


def count_is_pending(response: object) -> bool:
    """True when re-POSTing the same count payload could still change the answer.

    Anything that is not an explicit pending status counts as final. Erring in
    that direction matters: `_raise_for_status_with_body` hands 400/403/404 bodies
    back to the caller instead of raising, and such a body carries no `status` key
    at all — treating "unknown" as pending would spin until the timeout whenever
    the payload is rejected.
    """
    return isinstance(response, dict) and response.get("status") in COUNT_PENDING_STATUSES


# `order` is rejected outright by the count endpoint — 400 "invalid order by value",
# for any value at all — even though /v3/organizations/ accepts it. Sorting is
# meaningless when only a total comes back, so dropping it is what lets a payload
# written for the search endpoint be counted unchanged.
COUNT_UNSUPPORTED_KEYS: frozenset[str] = frozenset({"order"})


def count_payload(payload: dict, first_request: bool = True) -> dict:
    """Strip the keys the count endpoint cannot accept from a request body.

    `fields`, `limit` and `offset` are left in place: the API documents them as
    ignored for counts and accepts them without complaint, so there is nothing to
    gain by rewriting them out.

    `recount` forces a fresh count, so it may only ride on the first request —
    re-sending it on every poll would restart the count each time and the status
    would never leave "scheduled".
    """
    dropped = COUNT_UNSUPPORTED_KEYS if first_request else COUNT_UNSUPPORTED_KEYS | {"recount"}
    return {key: value for key, value in payload.items() if key not in dropped}
