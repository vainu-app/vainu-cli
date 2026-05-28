"""Shared constants and types used by both sync and async clients."""

import enum
from typing import Literal, Protocol, TypeAlias

DEFAULT_BASE_URL = "https://api.vainu.io/api"
JWT_REFRESH_ENDPOINT_PATH = "/token_authentication/refresh/"
ResponseFormat: TypeAlias = Literal["json", "csv", "jsonl"]
DEFAULT_RESPONSE_FORMAT: ResponseFormat = "json"
RESPONSE_FORMATS: tuple[ResponseFormat, ...] = ("json", "csv", "jsonl")

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


def parse_response(response: ResponseLike, format: ResponseFormat) -> dict | str:
    if format == "json":
        return response.json()
    return response.text


class AsyncJobState(enum.StrEnum):
    ACCEPTED = "accepted"
    COMPLETED = "completed"
    FAILURE = "failure"
    PARTIAL_FAILURE_COMPLETE = "partial_failure_complete"
    PARTIAL_FAILURE_INCOMPLETE = "partial_failure_incomplete"
    PROCESS = "process"
    STOPPED = "stopped"
