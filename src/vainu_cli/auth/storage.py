"""Persistent storage for OAuth tokens.

Primary backend is the OS keyring (via the `keyring` package). When keyring is
unavailable (headless, CI, locked) we fall back to a JSON file under
`platformdirs.user_config_path` with 0600 perms.

Set ``VAINU_AUTH_STORE=file`` to force the file backend.
"""

from __future__ import annotations

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
    """Persist `StoredCredentials` via keyring with a platformdirs file fallback."""

    def __init__(self, *, force_file: bool | None = None) -> None:
        if force_file is None:
            force_file = os.environ.get(ENV_FORCE_FILE_STORE, "").lower() == "file"
        self._force_file = force_file
        self._last_backend: Literal["keyring", "file", "none"] = "none"

    @property
    def backend(self) -> Literal["keyring", "file", "none"]:
        return self._last_backend

    def file_path(self) -> Path:
        return (
            user_config_path(appname=CONFIG_APP_NAME, appauthor=CONFIG_APP_AUTHOR)
            / CREDENTIALS_FILENAME
        )

    def save(self, creds: StoredCredentials) -> None:
        payload = creds.to_json()
        if not self._force_file:
            try:
                keyring.set_password(KEYRING_SERVICE, KEYRING_USERNAME, payload)
                self._last_backend = "keyring"
                # If a stale file copy exists from a prior file-backend session,
                # remove it so `load` returns the keyring value.
                self._remove_file_silently()
                return
            except keyring.errors.KeyringError as exc:
                logger.warning("Keyring unavailable, falling back to file: %s", exc)
        self._write_file(payload)
        self._last_backend = "file"

    def load(self) -> StoredCredentials | None:
        if not self._force_file:
            try:
                raw = keyring.get_password(KEYRING_SERVICE, KEYRING_USERNAME)
                if raw:
                    self._last_backend = "keyring"
                    return StoredCredentials.from_json(raw)
            except keyring.errors.KeyringError as exc:
                logger.debug("Keyring read failed: %s", exc)
        path = self.file_path()
        if path.exists():
            try:
                raw = path.read_text()
            except OSError as exc:
                logger.warning("Failed reading credentials file %s: %s", path, exc)
                return None
            self._last_backend = "file"
            return StoredCredentials.from_json(raw)
        self._last_backend = "none"
        return None

    def clear(self) -> None:
        if not self._force_file:
            try:
                keyring.delete_password(KEYRING_SERVICE, KEYRING_USERNAME)
            except keyring.errors.PasswordDeleteError:
                pass
            except keyring.errors.KeyringError as exc:
                logger.debug("Keyring delete failed: %s", exc)
        self._remove_file_silently()
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
