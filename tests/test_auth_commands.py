"""Tests for `vainu login` / `vainu logout` / `vainu auth status` commands."""

from __future__ import annotations

import json
import time

import pytest
import responses as resp
from click.testing import CliRunner
from conftest import BASE_URL, COMPANIES_RESPONSE, OAUTH_REVOKE_URL, OAUTH_TOKEN_URL

from vainu_cli.auth.storage import StoredCredentials, TokenStore
from vainu_cli.cli import main
from vainu_cli.common import PUBLIC_CLIENT_ID


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _stored(**overrides) -> StoredCredentials:
    defaults = dict(
        access_token="acc-stored",
        refresh_token="ref-stored",
        expires_at=time.time() + 3600,
        scope="vainu:api offline_access",
        client_id="vainu-cli",
        base_url=BASE_URL,
        account="user@example.com",
        obtained_at=time.time(),
    )
    defaults.update(overrides)
    return StoredCredentials(**defaults)


class TestLogin:
    def test_login_persists_credentials(self, runner, monkeypatch):
        captured: dict[str, object] = {}

        def _fake_run_login(**kwargs):
            captured.update(kwargs)
            return _stored(account="newuser@example.com")

        monkeypatch.setattr("vainu_cli.auth.commands.run_login", _fake_run_login)

        result = runner.invoke(main, ["login"], catch_exceptions=False)

        assert result.exit_code == 0
        if hasattr(result, "stderr"):
            assert "Logged in as newuser@example.com" in result.stderr
        loaded = TokenStore().load()
        assert loaded is not None
        assert loaded.account == "newuser@example.com"
        assert captured["client_id"] == PUBLIC_CLIENT_ID

    def test_login_refuses_to_overwrite_without_force(self, runner, monkeypatch):
        TokenStore().save(_stored(account="existing@example.com"))

        called = []

        def _fake_run_login(**_kw):
            called.append(True)
            return _stored()

        monkeypatch.setattr("vainu_cli.auth.commands.run_login", _fake_run_login)

        result = runner.invoke(main, ["login"], catch_exceptions=False)
        assert result.exit_code == 0
        assert called == []
        assert "Already logged in" in result.output

    def test_login_force_overwrites(self, runner, monkeypatch):
        TokenStore().save(_stored(account="old@example.com"))

        def _fake_run_login(**_kw):
            return _stored(account="new@example.com")

        monkeypatch.setattr("vainu_cli.auth.commands.run_login", _fake_run_login)

        result = runner.invoke(main, ["login", "--force"], catch_exceptions=False)
        assert result.exit_code == 0
        loaded = TokenStore().load()
        assert loaded.account == "new@example.com"


class TestLogout:
    def test_logout_when_not_logged_in(self, runner):
        result = runner.invoke(main, ["logout"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "Not logged in" in result.output

    def test_logout_clears_local_creds(self, runner):
        TokenStore().save(_stored())
        result = runner.invoke(main, ["logout"], catch_exceptions=False)
        assert result.exit_code == 0
        assert TokenStore().load() is None

    @resp.activate
    def test_logout_all_revokes_server_side(self, runner):
        TokenStore().save(_stored(refresh_token="ref-to-revoke"))
        resp.add(resp.POST, OAUTH_REVOKE_URL, status=200, body="")

        result = runner.invoke(main, ["logout", "--all"], catch_exceptions=False)

        assert result.exit_code == 0
        assert TokenStore().load() is None
        revoke_call = resp.calls[0].request
        raw_body = revoke_call.body
        body = raw_body.decode() if isinstance(raw_body, bytes) else raw_body
        assert "token=ref-to-revoke" in body
        assert "client_id=vainu-cli" in body


class TestAuthStatus:
    def test_status_when_logged_out_exits_nonzero(self, runner):
        result = runner.invoke(main, ["auth", "status"])
        assert result.exit_code == 1
        assert "Not logged in" in result.output

    def test_status_json_when_logged_in(self, runner):
        TokenStore().save(_stored(account="status@example.com"))
        result = runner.invoke(main, ["auth", "status", "--json"], catch_exceptions=False)
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["logged_in"] is True
        assert data["account"] == "status@example.com"
        assert data["storage_backend"] == "file"


class TestAutoDetect:
    @resp.activate
    def test_stored_creds_drive_companies_request(self, runner):
        TokenStore().save(_stored())
        # Existing access token is still valid (expires_at > now+leeway), so no refresh.
        resp.add(resp.GET, f"{BASE_URL}/v2/companies/", json=COMPANIES_RESPONSE)

        result = runner.invoke(
            main,
            ["companies", "--query", "?country=FI"],
            catch_exceptions=False,
        )

        assert result.exit_code == 0
        # Verify the call carried the Bearer header from stored creds.
        auth_header = resp.calls[0].request.headers.get("Authorization")
        assert auth_header == "Bearer acc-stored"

    @resp.activate
    def test_explicit_api_key_flag_overrides_stored_creds(self, runner):
        TokenStore().save(_stored(access_token="must-not-be-used"))
        resp.add(resp.GET, f"{BASE_URL}/v2/companies/", json=COMPANIES_RESPONSE)

        result = runner.invoke(
            main,
            ["--api-key", "explicit-key", "companies", "--query", "?country=FI"],
            catch_exceptions=False,
        )

        assert result.exit_code == 0
        assert resp.calls[0].request.headers.get("API-Key") == "explicit-key"
        assert "Authorization" not in resp.calls[0].request.headers

    @resp.activate
    def test_env_var_api_key_overrides_stored_creds(self, runner, monkeypatch):
        TokenStore().save(_stored(access_token="must-not-be-used"))
        monkeypatch.setenv("VAINU_API_KEY", "from-env")
        resp.add(resp.GET, f"{BASE_URL}/v2/companies/", json=COMPANIES_RESPONSE)

        result = runner.invoke(
            main,
            ["companies", "--query", "?country=FI"],
            catch_exceptions=False,
        )

        assert result.exit_code == 0
        assert resp.calls[0].request.headers.get("API-Key") == "from-env"

    @resp.activate
    def test_vainu_access_token_env_uses_browser_client(self, runner, monkeypatch):
        # No stored creds on disk; only env vars.
        monkeypatch.setenv("VAINU_ACCESS_TOKEN", "env-access")
        monkeypatch.setenv("VAINU_REFRESH_TOKEN", "env-refresh")
        monkeypatch.setenv("VAINU_TOKEN_EXPIRES_AT", str(time.time() + 3600))
        resp.add(resp.GET, f"{BASE_URL}/v2/companies/", json=COMPANIES_RESPONSE)

        result = runner.invoke(
            main,
            ["companies", "--query", "?country=FI"],
            catch_exceptions=False,
        )

        assert result.exit_code == 0
        assert resp.calls[0].request.headers.get("Authorization") == "Bearer env-access"
        # Env-var path must NOT persist credentials to disk.
        assert TokenStore().load() is None

    @resp.activate
    def test_refresh_writes_back_rotated_tokens(self, runner):
        # Access token already expired -> refresh fires before companies call.
        TokenStore().save(
            _stored(
                access_token="stale",
                refresh_token="ref-1",
                expires_at=time.time() - 10,
            )
        )
        resp.add(
            resp.POST,
            OAUTH_TOKEN_URL,
            json={
                "access_token": "fresh",
                "refresh_token": "ref-2",
                "expires_in": 3600,
                "token_type": "Bearer",
            },
        )
        resp.add(resp.GET, f"{BASE_URL}/v2/companies/", json=COMPANIES_RESPONSE)

        result = runner.invoke(
            main,
            ["companies", "--query", "?country=FI"],
            catch_exceptions=False,
        )

        assert result.exit_code == 0
        # Second call (after refresh) carries new bearer.
        assert resp.calls[-1].request.headers.get("Authorization") == "Bearer fresh"
        # Rotated refresh token persisted.
        loaded = TokenStore().load()
        assert loaded.refresh_token == "ref-2"
        assert loaded.access_token == "fresh"
