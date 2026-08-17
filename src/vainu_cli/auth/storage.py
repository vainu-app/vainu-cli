"""Persistent storage for OAuth tokens.

Primary backend is the OS keyring (via the `keyring` package). When keyring is
unavailable (headless, CI, locked) we fall back to a JSON file under
`platformdirs.user_config_path` with 0600 perms.

Set ``VAINU_AUTH_STORE=file`` to force the file backend.

Two kinds of credentials share this store, separated by keyring username:

* the `vainu login` browser session, under ``KEYRING_USERNAME``
* client-credentials access tokens, under a hash of base_url/client_id/scope,
  so several API clients (and several environments) can cache side by side
  without clobbering each other or the login session
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

import keyring
import keyring.errors
from platformdirs import user_config_path

from vainu_cli.common import (
    CONFIG_APP_AUTHOR,
    CONFIG_APP_NAME,
    KEYRING_SERVICE,
    KEYRING_USERNAME,
)

logger = logging.getLogger(__name__)

CREDENTIALS_FILENAME = "credentials.json"
ENV_FORCE_FILE_STORE = "VAINU_AUTH_STORE"
# Names of the extra store entries written by the client-credentials cache.
# Holds no secrets — only derived cache keys — so it is a plain file even when
# the tokens themselves live in the keyring, which has no enumeration API.
CACHE_INDEX_FILENAME = "cache-index.json"
CLIENT_CREDENTIALS_PREFIX = "cc-"
# Keyring backends do not reliably wrap their platform errors in a KeyringError.
# The Windows Credential Locker backend calls win32cred.CredWrite without a
# try/except, so a refused write (e.g. a payload over the 2560-byte
# CRED_MAX_CREDENTIAL_BLOB_SIZE, which a real token pair exceeds) surfaces as a
# raw win32ctypes.pywin32.pywintypes.error, which derives straight from Exception
# — not from OSError, and not from KeyringError — so no narrower tuple catches
# it. The keyring is best-effort here: any failure to reach it must land on the
# file backend instead of aborting the command, hence the deliberately broad
# catch.
_KEYRING_FAILURES = Exception
ENV_TOKEN_CACHE = "VAINU_TOKEN_CACHE"  # noqa: S105  # nosec B105 — env var name, not a credential
_CACHE_DISABLED_VALUES = frozenset({"0", "false", "no", "off"})


@dataclass
class StoredCredentials:
    access_token: str
    refresh_token: str
    expires_at: float
    scope: str
    client_id: str
    base_url: str
    account: str | None
    obtained_at: float
    token_type: str = "Bearer"  # noqa: S105 — OAuth token-type label, not a credential

    def is_expired(self, *, leeway: int = 60) -> bool:
        return time.time() >= (self.expires_at - leeway)

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True)

    @classmethod
    def from_json(cls, raw: str) -> StoredCredentials:
        data = json.loads(raw)
        return cls(**data)


class TokenStore:
    """Persist `StoredCredentials` via keyring with a platformdirs file fallback.

    `username` selects which credential set this store instance addresses; the
    default is the `vainu login` session. Non-default usernames are recorded in
    a small index file so `clear_all` can find them again — keyring exposes no
    way to enumerate the entries under a service.
    """

    def __init__(self, *, username: str = KEYRING_USERNAME, force_file: bool | None = None) -> None:
        if force_file is None:
            force_file = os.environ.get(ENV_FORCE_FILE_STORE, "").lower() == "file"
        self._force_file = force_file
        self._username = username
        self._last_backend: Literal["keyring", "file", "none"] = "none"

    @property
    def backend(self) -> Literal["keyring", "file", "none"]:
        return self._last_backend

    @property
    def username(self) -> str:
        return self._username

    def file_path(self) -> Path:
        filename = CREDENTIALS_FILENAME
        if self._username != KEYRING_USERNAME:
            filename = f"credentials-{self._username}.json"
        return user_config_path(appname=CONFIG_APP_NAME, appauthor=CONFIG_APP_AUTHOR) / filename

    def save(self, creds: StoredCredentials) -> None:
        payload = creds.to_json()
        if self._username != KEYRING_USERNAME:
            _register_in_index(self._username)
        if not self._force_file:
            try:
                keyring.set_password(KEYRING_SERVICE, self._username, payload)
                self._last_backend = "keyring"
                # If a stale file copy exists from a prior file-backend session,
                # remove it so `load` returns the keyring value.
                self._remove_file_silently()
                return
            except _KEYRING_FAILURES as exc:
                logger.warning("Keyring unavailable, falling back to file: %s", exc)
        self._write_file(payload)
        self._last_backend = "file"

    def load(self) -> StoredCredentials | None:
        if not self._force_file:
            try:
                raw = keyring.get_password(KEYRING_SERVICE, self._username)
            except _KEYRING_FAILURES as exc:
                logger.debug("Keyring read failed: %s", exc)
            else:
                if raw:
                    creds = _parse_or_none(raw, source="keyring")
                    if creds is not None:
                        self._last_backend = "keyring"
                        return creds
        path = self.file_path()
        if path.exists():
            try:
                raw = path.read_text()
            except OSError as exc:
                logger.warning("Failed reading credentials file %s: %s", path, exc)
                return None
            creds = _parse_or_none(raw, source=str(path))
            if creds is not None:
                self._last_backend = "file"
                return creds
        self._last_backend = "none"
        return None

    def clear(self) -> None:
        if not self._force_file:
            try:
                keyring.delete_password(KEYRING_SERVICE, self._username)
            except keyring.errors.PasswordDeleteError:
                pass
            except _KEYRING_FAILURES as exc:
                logger.debug("Keyring delete failed: %s", exc)
        self._remove_file_silently()
        if self._username != KEYRING_USERNAME:
            _deregister_from_index(self._username)
        self._last_backend = "none"

    def _write_file(self, payload: str) -> None:
        path = self.file_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        # Atomic write with 0600 perms.
        fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=".credentials.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as fh:
                fh.write(payload)
            os.chmod(tmp_name, 0o600)
            os.replace(tmp_name, path)
        except Exception:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise

    def _remove_file_silently(self) -> None:
        try:
            self.file_path().unlink()
        except FileNotFoundError:
            pass
        except OSError as exc:
            logger.debug("Failed removing credentials file: %s", exc)


def _parse_or_none(raw: str, *, source: str) -> StoredCredentials | None:
    """Decode a stored payload, treating anything unreadable as absent.

    A hand-edited file or an entry written by an older schema must read as a
    cache miss — re-authenticating is always cheaper than a traceback.
    """
    try:
        return StoredCredentials.from_json(raw)
    except (ValueError, TypeError) as exc:
        logger.debug("Ignoring unreadable credentials from %s: %s", source, exc)
        return None


def _index_path() -> Path:
    config_dir = user_config_path(appname=CONFIG_APP_NAME, appauthor=CONFIG_APP_AUTHOR)
    return config_dir / CACHE_INDEX_FILENAME


def cached_token_usernames() -> list[str]:
    """Store usernames written by the client-credentials cache, if any."""
    path = _index_path()
    try:
        data = json.loads(path.read_text())
    except FileNotFoundError:
        return []
    except (OSError, ValueError) as exc:
        logger.debug("Ignoring unreadable cache index %s: %s", path, exc)
        return []
    if not isinstance(data, list):
        return []
    return [name for name in data if isinstance(name, str)]


def _write_index(names: list[str]) -> None:
    path = _index_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(sorted(set(names))))
    except OSError as exc:
        logger.debug("Failed writing cache index %s: %s", path, exc)


def _register_in_index(username: str) -> None:
    names = cached_token_usernames()
    if username in names:
        return
    _write_index([*names, username])


def _deregister_from_index(username: str) -> None:
    names = cached_token_usernames()
    if username not in names:
        return
    remaining = [name for name in names if name != username]
    if remaining:
        _write_index(remaining)
        return
    try:
        _index_path().unlink()
    except FileNotFoundError:
        pass
    except OSError as exc:
        logger.debug("Failed removing cache index: %s", exc)


def clear_all_cached_tokens() -> int:
    """Drop every cached client-credentials token. Returns how many were removed."""
    names = cached_token_usernames()
    for username in names:
        TokenStore(username=username).clear()
    return len(names)


def client_credentials_username(*, base_url: str, client_id: str, scope: str) -> str:
    """Derive the store username for one (host, client, scope) triple.

    Hashed rather than spelled out so the client_id — which may identify a
    customer — never lands in a keyring label or a filename.
    """
    digest = hashlib.sha256(f"{base_url}|{client_id}|{scope}".encode()).hexdigest()
    return f"{CLIENT_CREDENTIALS_PREFIX}{digest[:16]}"


def token_cache_enabled() -> bool:
    return os.environ.get(ENV_TOKEN_CACHE, "").lower() not in _CACHE_DISABLED_VALUES


class ClientCredentialsCache:
    """Reuse a client-credentials access token across CLI invocations.

    The access token is short-lived and derived from a client_secret that the
    caller already holds in the clear, so this trades no meaningful secrecy for
    dropping one token round-trip per process.
    """

    def __init__(
        self,
        *,
        base_url: str,
        client_id: str,
        scope: str,
        enabled: bool | None = None,
    ) -> None:
        self._base_url = base_url
        self._client_id = client_id
        self._scope = scope
        self._enabled = token_cache_enabled() if enabled is None else enabled
        self._store = (
            TokenStore(
                username=client_credentials_username(
                    base_url=base_url, client_id=client_id, scope=scope
                )
            )
            if self._enabled
            else None
        )

    @property
    def enabled(self) -> bool:
        return self._enabled

    def load(self) -> tuple[str, float] | None:
        """Return `(access_token, expires_at)` when a live token is cached."""
        if self._store is None:
            return None
        creds = self._store.load()
        if creds is None:
            return None
        # A token minted for another host, client or scope must never be
        # reused, even though the derived username makes that near-impossible.
        if (
            creds.client_id != self._client_id
            or creds.base_url != self._base_url
            or creds.scope != self._scope
        ):
            logger.debug("Cached token does not match this client — ignoring")
            return None
        if creds.is_expired():
            logger.debug("Cached token expired at %s — refreshing", creds.expires_at)
            return None
        logger.debug("Reusing cached access token from %s", self._store.backend)
        return creds.access_token, creds.expires_at

    def save(self, access_token: str, expires_at: float) -> None:
        if self._store is None:
            return
        self._store.save(
            StoredCredentials(
                access_token=access_token,
                # The client_credentials grant issues no refresh token; the
                # client_secret plays that role and is never stored here.
                refresh_token="",  # nosec B106 — deliberately empty, not a secret
                expires_at=expires_at,
                scope=self._scope,
                client_id=self._client_id,
                base_url=self._base_url,
                account=None,
                obtained_at=time.time(),
            )
        )

    def clear(self) -> None:
        if self._store is not None:
            self._store.clear()
