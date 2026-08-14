"""Tests for the OAuth token storage layer."""

from __future__ import annotations

import stat
import time

import keyring.errors
import pytest

from vainu_cli.auth.storage import (
    ClientCredentialsCache,
    StoredCredentials,
    TokenStore,
    cached_token_usernames,
    clear_all_cached_tokens,
    client_credentials_username,
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


@pytest.fixture
def fake_keyring(monkeypatch) -> dict[tuple[str, str], str]:
    """An in-memory keyring backend, so tests never touch the real keychain."""
    secret_bag: dict[tuple[str, str], str] = {}

    def _set(service: str, username: str, value: str) -> None:
        secret_bag[(service, username)] = value

    def _get(service: str, username: str) -> str | None:
        return secret_bag.get((service, username))

    def _delete(service: str, username: str) -> None:
        if secret_bag.pop((service, username), None) is None:
            raise keyring.errors.PasswordDeleteError("not found")

    monkeypatch.setattr("vainu_cli.auth.storage.keyring.set_password", _set)
    monkeypatch.setattr("vainu_cli.auth.storage.keyring.get_password", _get)
    monkeypatch.setattr("vainu_cli.auth.storage.keyring.delete_password", _delete)
    monkeypatch.delenv("VAINU_AUTH_STORE", raising=False)
    monkeypatch.delenv("VAINU_TOKEN_CACHE", raising=False)
    return secret_bag


def _cache(**overrides) -> ClientCredentialsCache:
    defaults = dict(
        base_url="https://api.vainu.io/api",
        client_id="client-1",
        scope="vainu:api",
    )
    defaults.update(overrides)
    return ClientCredentialsCache(**defaults)


class TestTokenStoreLoadIsTolerant:
    def test_corrupt_file_reads_as_a_miss(self):
        store = TokenStore(force_file=True)
        store.save(_creds())
        store.file_path().write_text("{not json")
        assert store.load() is None
        assert store.backend == "none"

    def test_unknown_field_reads_as_a_miss(self):
        store = TokenStore(force_file=True)
        store.save(_creds())
        store.file_path().write_text('{"access_token": "a", "from_the_future": 1}')
        assert store.load() is None


class TestClientCredentialsCache:
    def test_token_goes_to_the_keyring_under_a_derived_username(self, fake_keyring):
        _cache().save("access-1", time.time() + 3600)

        assert len(fake_keyring) == 1
        (service, username), _payload = next(iter(fake_keyring.items()))
        assert service == KEYRING_SERVICE
        assert username.startswith("cc-")
        # The client_id must not be recoverable from the entry's label.
        assert "client-1" not in username

    def test_round_trip_returns_token_and_expiry(self, fake_keyring):
        expires_at = time.time() + 3600
        _cache().save("access-1", expires_at)

        loaded = _cache().load()
        assert loaded == ("access-1", expires_at)

    def test_does_not_disturb_the_login_session(self, fake_keyring):
        TokenStore().save(_creds(account="alice"))
        _cache().save("access-1", time.time() + 3600)

        session = TokenStore().load()
        assert session is not None
        assert session.account == "alice"

    def test_expired_token_is_a_miss(self, fake_keyring):
        _cache().save("access-1", time.time() + 30)  # inside the 60s leeway
        assert _cache().load() is None

    def test_different_client_id_does_not_share_a_token(self, fake_keyring):
        _cache().save("access-1", time.time() + 3600)
        assert _cache(client_id="client-2").load() is None

    def test_different_scope_does_not_share_a_token(self, fake_keyring):
        _cache().save("access-1", time.time() + 3600)
        assert _cache(scope="other").load() is None

    def test_different_base_url_does_not_share_a_token(self, fake_keyring):
        _cache().save("access-1", time.time() + 3600)
        assert _cache(base_url="https://staging.vainu.io/api").load() is None

    def test_mismatched_payload_is_ignored(self, fake_keyring):
        """Belt and braces: a matching username but a foreign body is a miss."""
        cache = _cache()
        username = client_credentials_username(
            base_url="https://api.vainu.io/api", client_id="client-1", scope="vainu:api"
        )
        TokenStore(username=username).save(_creds(client_id="someone-else"))
        assert cache.load() is None

    def test_env_var_disables_the_cache(self, fake_keyring, monkeypatch):
        monkeypatch.setenv("VAINU_TOKEN_CACHE", "0")
        cache = _cache()
        assert cache.enabled is False
        cache.save("access-1", time.time() + 3600)
        assert fake_keyring == {}
        assert cache.load() is None

    def test_explicit_flag_beats_the_env_var(self, fake_keyring, monkeypatch):
        monkeypatch.setenv("VAINU_TOKEN_CACHE", "0")
        assert _cache(enabled=True).enabled is True

    def test_clear_all_removes_cached_tokens_but_keeps_the_login(self, fake_keyring):
        TokenStore().save(_creds(account="alice"))
        _cache().save("access-1", time.time() + 3600)
        _cache(client_id="client-2").save("access-2", time.time() + 3600)

        assert clear_all_cached_tokens() == 2
        assert _cache().load() is None
        assert _cache(client_id="client-2").load() is None
        assert TokenStore().load() is not None
        assert cached_token_usernames() == []

    def test_clear_all_is_a_no_op_without_cached_tokens(self, fake_keyring):
        assert clear_all_cached_tokens() == 0

    def test_index_survives_the_file_backend(self, monkeypatch):
        monkeypatch.setenv("VAINU_AUTH_STORE", "file")
        monkeypatch.delenv("VAINU_TOKEN_CACHE", raising=False)
        _cache().save("access-1", time.time() + 3600)
        assert len(cached_token_usernames()) == 1
        assert clear_all_cached_tokens() == 1
        assert _cache().load() is None
