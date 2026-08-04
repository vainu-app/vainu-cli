"""Tests for the OAuth token storage layer."""

from __future__ import annotations

import stat
import time

import keyring.errors

from vainu_cli.auth.storage import (
    StoredCredentials,
    TokenStore,
)
from vainu_cli.common import KEYRING_SERVICE, KEYRING_USERNAME


def _creds(**overrides) -> StoredCredentials:
    defaults = dict(
        access_token="access-1",
        refresh_token="refresh-1",
        expires_at=time.time() + 3600,
        scope="vainu:api offline_access",
        client_id="vainu-cli",
        base_url="https://api.vainu.io/api",
        account="user@example.com",
        obtained_at=time.time(),
    )
    defaults.update(overrides)
    return StoredCredentials(**defaults)


class TestStoredCredentials:
    def test_round_trip_through_json(self):
        creds = _creds()
        restored = StoredCredentials.from_json(creds.to_json())
        assert restored == creds

    def test_is_expired_respects_leeway(self):
        creds = _creds(expires_at=time.time() + 30)
        assert creds.is_expired(leeway=60) is True
        assert creds.is_expired(leeway=0) is False

    def test_is_expired_past(self):
        creds = _creds(expires_at=time.time() - 1)
        assert creds.is_expired() is True


class TestTokenStoreFile:
    def test_save_and_load_file_round_trip(self, monkeypatch):
        store = TokenStore(force_file=True)
        store.save(_creds(account="alice"))
        assert store.backend == "file"
        loaded = store.load()
        assert loaded is not None
        assert loaded.account == "alice"
        assert store.backend == "file"

    def test_file_is_chmod_0600(self):
        store = TokenStore(force_file=True)
        store.save(_creds())
        path = store.file_path()
        assert path.exists()
        mode = stat.S_IMODE(path.stat().st_mode)
        assert mode == 0o600

    def test_clear_removes_file(self):
        store = TokenStore(force_file=True)
        store.save(_creds())
        assert store.file_path().exists()
        store.clear()
        assert not store.file_path().exists()
        assert store.load() is None

    def test_load_returns_none_when_no_file(self):
        store = TokenStore(force_file=True)
        assert store.load() is None
        assert store.backend == "none"


class TestTokenStoreKeyringFallback:
    def test_falls_back_to_file_when_keyring_raises(self, monkeypatch):
        def _raise_set(*_a, **_kw):
            raise keyring.errors.KeyringError("no backend")

        monkeypatch.setattr("vainu_cli.auth.storage.keyring.set_password", _raise_set)
        monkeypatch.setattr(
            "vainu_cli.auth.storage.keyring.get_password",
            lambda *_a, **_kw: None,
        )
        store = TokenStore(force_file=False)
        store.save(_creds(account="bob"))
        assert store.backend == "file"
        loaded = store.load()
        assert loaded is not None
        assert loaded.account == "bob"

    def test_keyring_path_is_preferred_when_available(self, monkeypatch):
        secret_bag: dict[tuple[str, str], str] = {}

        def _set(service: str, username: str, value: str) -> None:
            secret_bag[(service, username)] = value

        def _get(service: str, username: str) -> str | None:
            return secret_bag.get((service, username))

        monkeypatch.setattr("vainu_cli.auth.storage.keyring.set_password", _set)
        monkeypatch.setattr("vainu_cli.auth.storage.keyring.get_password", _get)
        store = TokenStore(force_file=False)
        store.save(_creds(account="carol"))
        assert store.backend == "keyring"
        assert (KEYRING_SERVICE, KEYRING_USERNAME) in secret_bag

        loaded = store.load()
        assert loaded is not None
        assert loaded.account == "carol"

    def test_vainu_auth_store_env_forces_file(self, monkeypatch):
        # Even with a fully-working keyring, env override must win.
        kept: list[str] = []

        def _set(service: str, username: str, value: str) -> None:
            kept.append(value)

        monkeypatch.setattr("vainu_cli.auth.storage.keyring.set_password", _set)
        monkeypatch.setenv("VAINU_AUTH_STORE", "file")

        store = TokenStore()
        store.save(_creds())
        assert store.backend == "file"
        assert kept == []
