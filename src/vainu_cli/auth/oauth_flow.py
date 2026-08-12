"""OAuth 2.0 Authorization Code + PKCE loopback flow.

Opens the system browser to the Vainu authorize endpoint, runs a one-shot
HTTP server on 127.0.0.1 to receive the redirect, and exchanges the code
for a JWT access + refresh token pair.
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import http.server
import json
import logging
import secrets
import socket
import socketserver
import threading
import time
import webbrowser
from dataclasses import dataclass
from urllib.parse import parse_qs, urlencode, urlparse

import click
import requests

from vainu_cli.auth.storage import StoredCredentials
from vainu_cli.common import (
    OAUTH_AUTHORIZE_ENDPOINT,
    OAUTH_TOKEN_ENDPOINT,
)

logger = logging.getLogger(__name__)

DEFAULT_LOGIN_TIMEOUT_SECONDS = 300
SUCCESS_HTML = (
    "<!doctype html>"
    "<html><head><title>Vainu CLI — Logged in</title>"
    "<style>body{font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;"
    "text-align:center;margin-top:80px;color:#111}</style></head>"
    "<body><h1>You are signed in.</h1>"
    "<p>You can close this tab and return to the terminal.</p></body></html>"
).encode()
ERROR_HTML_TEMPLATE = (
    "<!doctype html>"
    "<html><head><title>Vainu CLI — Login failed</title>"
    "<style>body{font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;"
    "text-align:center;margin-top:80px;color:#111}</style></head>"
    "<body><h1>Login failed.</h1><pre>{detail}</pre></body></html>"
)


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _pkce_pair() -> tuple[str, str]:
    verifier = _b64url(secrets.token_bytes(64))
    challenge = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
    return verifier, challenge


@dataclass
class _CallbackResult:
    code: str | None = None
    state: str | None = None
    error: str | None = None
    error_description: str | None = None


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    server: _CallbackServer  # type: ignore[assignment]

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path not in ("/callback", "/"):
            self.send_response(404)
            self.end_headers()
            return
        params = {k: v[0] for k, v in parse_qs(parsed.query).items()}
        result = _CallbackResult(
            code=params.get("code"),
            state=params.get("state"),
            error=params.get("error"),
            error_description=params.get("error_description"),
        )
        self.server.result = result
        if result.error:
            detail = result.error_description or result.error
            body = ERROR_HTML_TEMPLATE.format(detail=detail).encode("utf-8")
            self.send_response(400)
        else:
            body = SUCCESS_HTML
            self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        logger.debug("loopback: " + format, *args)


class _CallbackServer(socketserver.TCPServer):
    allow_reuse_address = False
    result: _CallbackResult | None = None


def _bind_server(preferred_port: int) -> _CallbackServer:
    if preferred_port:
        return _CallbackServer(("127.0.0.1", preferred_port), _CallbackHandler)
    # port=0: let the kernel pick
    return _CallbackServer(("127.0.0.1", 0), _CallbackHandler)


@dataclass
class LoginResult:
    credentials: StoredCredentials


def _decode_jwt_unverified(token: str) -> dict:
    try:
        _, payload, _ = token.split(".")
        padding = "=" * (-len(payload) % 4)
        decoded = base64.urlsafe_b64decode(payload + padding)
        return json.loads(decoded)
    except (ValueError, json.JSONDecodeError):
        return {}


def _exchange_code(
    *,
    base_url: str,
    client_id: str,
    code: str,
    redirect_uri: str,
    code_verifier: str,
    timeout: int = 30,
) -> dict:
    response = requests.post(
        f"{base_url.rstrip('/')}{OAUTH_TOKEN_ENDPOINT}",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": client_id,
            "code_verifier": code_verifier,
        },
        timeout=timeout,
    )
    if response.status_code != 200:
        raise click.ClickException(
            f"Token exchange failed ({response.status_code}): {response.text}"
        )
    return response.json()


def run_login(
    *,
    base_url: str,
    client_id: str,
    scope: str,
    authorize_base_url: str | None = None,
    redirect_path: str = "/callback",
    port: int = 0,
    open_browser: bool = True,
    timeout: int = DEFAULT_LOGIN_TIMEOUT_SECONDS,
    echo: callable = click.echo,
) -> StoredCredentials:
    """Run the browser OAuth flow and return new `StoredCredentials`.

    Raises ``click.ClickException`` on any failure (timeout, state mismatch,
    server-side error, exchange failure).
    """
    verifier, challenge = _pkce_pair()
    state = secrets.token_urlsafe(32)

    try:
        server = _bind_server(port)
    except OSError as exc:
        if port:
            raise click.ClickException(
                f"Could not bind 127.0.0.1:{port} for OAuth callback: {exc}"
            ) from exc
        raise click.ClickException(f"Could not bind a local port: {exc}") from exc

    chosen_port = server.server_address[1]
    redirect_uri = f"http://127.0.0.1:{chosen_port}{redirect_path}"

    authorize_host = (authorize_base_url or base_url).rstrip("/")
    authorize_url = f"{authorize_host}{OAUTH_AUTHORIZE_ENDPOINT}?" + urlencode(
        {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": scope,
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
    )

    opened = False
    if open_browser:
        with contextlib.suppress(webbrowser.Error):
            opened = webbrowser.open(authorize_url, new=1, autoraise=True)
    if not opened:
        echo(
            f"Open this URL in your browser to continue logging in:\n  {authorize_url}",
            err=True,
        )
    else:
        echo(f"Opened browser to {authorize_host} for login.", err=True)

    server.timeout = timeout
    server.result = None
    stop_event = threading.Event()

    def _serve() -> None:
        while not stop_event.is_set() and server.result is None:
            server.handle_request()

    serve_thread = threading.Thread(target=_serve, daemon=True)
    serve_thread.start()
    deadline = time.monotonic() + timeout
    try:
        while server.result is None:
            if time.monotonic() > deadline:
                raise click.ClickException(
                    "Timed out waiting for the browser callback. Try `vainu login` again."
                )
            time.sleep(0.1)
    except KeyboardInterrupt as exc:
        raise click.Abort() from exc
    finally:
        stop_event.set()
        # Unblock the handler thread by issuing a dummy request if it's still waiting.
        if serve_thread.is_alive():
            with contextlib.suppress(OSError):
                with socket.create_connection(("127.0.0.1", chosen_port), timeout=1):
                    pass
        with contextlib.suppress(Exception):
            server.server_close()
        serve_thread.join(timeout=2)

    result = server.result
    if result is None:
        raise click.ClickException("OAuth callback did not arrive.")
    if result.error:
        raise click.ClickException(
            f"OAuth error: {result.error}"
            + (f" — {result.error_description}" if result.error_description else "")
        )
    if not result.code or result.state != state:
        raise click.ClickException("OAuth state mismatch — possible CSRF; aborting.")

    token_data = _exchange_code(
        base_url=base_url,
        client_id=client_id,
        code=result.code,
        redirect_uri=redirect_uri,
        code_verifier=verifier,
    )

    obtained_at = time.time()
    expires_at = obtained_at + int(token_data.get("expires_in", 3600))
    access_token = token_data["access_token"]
    refresh_token = token_data.get("refresh_token", "")
    claims = _decode_jwt_unverified(access_token)
    account = claims.get("email") or claims.get("sub") or claims.get("preferred_username")

    return StoredCredentials(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_at=expires_at,
        scope=token_data.get("scope", scope),
        client_id=client_id,
        base_url=base_url,
        account=account,
        obtained_at=obtained_at,
        token_type=token_data.get("token_type", "Bearer"),
    )
