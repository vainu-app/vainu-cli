"""Shared constants and types used by both sync and async clients."""

import enum
import http
import logging
import re
from collections.abc import Iterator
from typing import Literal, Protocol, TypeAlias
from urllib.parse import parse_qs

logger = logging.getLogger(__name__)

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
# How long a poll loop keeps asking after an async job before giving up. A large
# export can legitimately run for hours; a job wedged in `process` must not keep
# a CLI run alive forever.
DEFAULT_ASYNC_MAX_WAIT_SECONDS = 21600  # 6 hours
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


# The CSV renderer still defaults to a legacy single-byte encoding: ask for
# `format=csv` without saying more and a Finnish name comes back as ISO-8859-1
# bytes — while the response header claims `charset=utf-8`. Nothing downstream
# can paper over that mismatch: the streaming path dies with a
# UnicodeDecodeError partway through the export, and the buffered path silently
# substitutes U+FFFD. So every CSV request names its encoding. The API hands the
# value to a Python codec, so a caller who wants the legacy bytes (or anything
# else) can still set `encoding` in the payload and keep it.
ENCODING_KEY = "encoding"
DEFAULT_ENCODING = "utf-8"
# What to fall back to when the body is not the encoding we asked for. The
# legacy CSV output is ISO-8859-1, and cp1252 decodes that byte range
# identically while also covering the Windows punctuation ISO-8859-1 leaves as
# control characters.
FALLBACK_ENCODING = "cp1252"


def requested_encoding(payload: dict | str) -> str | None:
    """The `encoding` this payload asks for, if it asks at all."""
    if isinstance(payload, dict):
        value = payload.get(ENCODING_KEY)
    else:
        values = parse_qs(payload.lstrip("?")).get(ENCODING_KEY) or []
        value = values[-1] if values else None
    return value if isinstance(value, str) and value else None


# Matches the `encoding` parameter of a query-string payload, value included.
_ENCODING_PARAM_RE = re.compile(rf"(?<=[?&]){ENCODING_KEY}=[^&]*")


def with_encoding(
    payload: dict | str,
    format: ResponseFormat,
    encoding: str | None = None,
) -> dict | str:
    """Name the codec a CSV response should be rendered in.

    An explicit `encoding` wins over one the payload carries — that is what lets
    a CLI flag override a saved payload. Without one, a payload that names its
    own codec is left alone and everything else is pinned to UTF-8. Only `csv`
    needs any of this: `json` and `jsonl` are UTF-8 either way and ignore the key.
    """
    if format != "csv":
        return payload
    chosen = encoding or requested_encoding(payload) or DEFAULT_ENCODING
    if isinstance(payload, dict):
        if payload.get(ENCODING_KEY) == chosen:
            return payload
        return {**payload, ENCODING_KEY: chosen}
    # A query-string payload rides on a GET, where `encoding` is just another
    # parameter. It cannot go in the query string of a POST: the API rejects
    # every parameter but `format` there with "Include the parameters only in
    # either the GET request or the POST payload, not both".
    replaced, count = _ENCODING_PARAM_RE.subn(f"{ENCODING_KEY}={chosen}", payload)
    if count:
        return replaced
    separator = "" if payload.endswith(("?", "&")) else "&"
    return f"{payload}{separator}{ENCODING_KEY}={chosen}"


def is_line_safe(encoding: str) -> bool:
    """Whether a codec survives a body that is split on newline bytes.

    Both clients hand rows over one at a time, splitting on b"\n" before
    decoding. A codec that spells ASCII in more than one byte — utf-16 and
    friends — wraps its own nulls around that delimiter, so every row but the
    first would decode to nonsense. A per-line BOM is fine: the API emits one
    for `utf-8-sig` on every row, and the decoder strips it from each line.
    """
    try:
        parts = "a\nb".encode(encoding).split(b"\n")
        return [part.decode(encoding) for part in parts] == ["a", "b"]
    except (LookupError, UnicodeError, ValueError):
        return False


def response_encoding(payload: dict | str, format: ResponseFormat) -> str:
    """The codec the response body will arrive in, for decoding it.

    Only `csv` follows the payload's `encoding` — the JSON renderers ignore the
    key and always answer in UTF-8, and one payload is routinely sent under
    several formats, so honouring it there would mangle a `jsonl` body.
    """
    if format == "csv":
        return requested_encoding(payload) or DEFAULT_ENCODING
    return DEFAULT_ENCODING


class LineDecoder:
    """Decodes body lines, tolerating a body that ignored the asked-for codec.

    A strict decode is not survivable here: it aborts an export mid-row, after
    the rows before it have already been handed to the caller. One decoder per
    response, so the warning is logged once per body rather than once per row.
    """

    def __init__(self, encoding: str = DEFAULT_ENCODING) -> None:
        self._encoding = encoding
        self._warned = False

    def __call__(self, line: bytes) -> str:
        try:
            return line.decode(self._encoding)
        except UnicodeDecodeError:
            if not self._warned:
                self._warned = True
                logger.warning(
                    "Response body is not %s as requested — decoding it as %s instead; "
                    "non-ASCII characters may be wrong.",
                    self._encoding,
                    FALLBACK_ENCODING,
                )
            return line.decode(FALLBACK_ENCODING, errors="replace")


def companies_request(
    payload: dict | str,
    format: ResponseFormat,
    encoding: str | None = None,
) -> tuple[http.HTTPMethod, str, dict | None]:
    """Resolve the companies endpoint call for a dict (POST) or query-string (GET) payload.

    Shared so the buffered and streaming paths cannot drift apart.
    """
    path = "/v2/companies/"
    if isinstance(payload, dict):
        body = with_encoding(payload, format, encoding)
        return http.HTTPMethod.POST, f"{path}?format={format}", body
    if isinstance(payload, str):
        query = with_encoding(payload, format, encoding)
        return http.HTTPMethod.GET, f"{path}{query}&format={format}", None
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
