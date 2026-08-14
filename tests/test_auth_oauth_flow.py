"""Tests for the browser OAuth login flow."""

from __future__ import annotations

import threading
import time
import urllib.error
import urllib.request
from urllib.parse import parse_qs, urlparse

import click
import pytest
import responses as resp
from conftest import BASE_URL, OAUTH_TOKEN_URL

from vainu_cli.auth import oauth_flow


def _hit_loopback(url: str) -> None:
    """Hit the loopback callback using urllib so `responses` doesn't intercept it."""
    deadline = time.monotonic() + 5
    last_exc: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2):  # noqa: S310
                return
        except urllib.error.HTTPError:
            # 4xx from the loopback handler (e.g. the error= redirect) — that's
            # still a successful "callback delivered" from our POV.
            return
        except (urllib.error.URLError, ConnectionError, OSError) as exc:
            last_exc = exc
            time.sleep(0.05)
    raise RuntimeError(f"Could not hit loopback callback: {last_exc}")


def _drive_callback(authorize_url: str, *, error: str | None = None) -> None:
    qs = parse_qs(urlparse(authorize_url).query)
    redirect_uri = qs["redirect_uri"][0]
    state = qs["state"][0]
    suffix = (
        f"?error={error}&error_description=denied&state={state}"
        if error
        else f"?code=fake-code&state={state}"
    )
    _hit_loopback(redirect_uri + suffix)


def _drive_callback_with_state(redirect_uri: str, state: str) -> None:
    _hit_loopback(f"{redirect_uri}?code=fake-code&state={state}")


class TestRunLogin:
    @resp.activate
    def test_happy_path_exchanges_code_for_tokens(self, monkeypatch):
        resp.add(
            resp.POST,
            OAUTH_TOKEN_URL,
            json={
                "access_token": "acc-1",
                "refresh_token": "ref-1",
                "expires_in": 3600,
                "scope": "vainu:api offline_access",
                "token_type": "Bearer",
            },
        )
        captured_url: list[str] = []

        def _fake_open(url: str, *_a, **_kw) -> bool:
            captured_url.append(url)
            threading.Thread(target=_drive_callback, args=(url,), daemon=True).start()
            return True

        monkeypatch.setattr(oauth_flow.webbrowser, "open", _fake_open)

        creds = oauth_flow.run_login(
            base_url=BASE_URL,
            client_id="vainu-cli",
            scope="vainu:api offline_access",
            port=0,
            open_browser=True,
            timeout=10,
        )

        assert creds.access_token == "acc-1"
        assert creds.refresh_token == "ref-1"
        assert creds.scope == "vainu:api offline_access"
        assert captured_url, "browser.open should have been called"
        # Verify the request to the token endpoint used PKCE + the right grant.
        token_call = resp.calls[0].request
        body = token_call.body.decode() if isinstance(token_call.body, bytes) else token_call.body
        params = parse_qs(body)
        assert params["grant_type"] == ["authorization_code"]
        assert params["client_id"] == ["vainu-cli"]
        assert params["code"] == ["fake-code"]
        assert "code_verifier" in params

    def test_state_mismatch_raises(self, monkeypatch):
        captured: dict[str, str] = {}

        def _fake_open(url: str, *_a, **_kw) -> bool:
            qs = parse_qs(urlparse(url).query)
            captured["redirect_uri"] = qs["redirect_uri"][0]
            # Fire wrong state in background
            threading.Thread(
                target=_drive_callback_with_state,
                args=(captured["redirect_uri"], "WRONG-STATE"),
                daemon=True,
            ).start()
            return True

        monkeypatch.setattr(oauth_flow.webbrowser, "open", _fake_open)

        with pytest.raises(click.ClickException) as exc_info:
            oauth_flow.run_login(
                base_url=BASE_URL,
                client_id="vainu-cli",
                scope="vainu:api",
                port=0,
                open_browser=True,
                timeout=5,
            )
        assert "state mismatch" in str(exc_info.value).lower()

    def test_redirect_error_is_surfaced(self, monkeypatch):
        def _fake_open(url: str, *_a, **_kw) -> bool:
            threading.Thread(
                target=_drive_callback,
                args=(url,),
                kwargs={"error": "access_denied"},
                daemon=True,
            ).start()
            return True

        monkeypatch.setattr(oauth_flow.webbrowser, "open", _fake_open)

        with pytest.raises(click.ClickException) as exc_info:
            oauth_flow.run_login(
                base_url=BASE_URL,
                client_id="vainu-cli",
                scope="vainu:api",
                port=0,
                open_browser=True,
                timeout=5,
            )
        assert "access_denied" in str(exc_info.value)
