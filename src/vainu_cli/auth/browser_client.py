"""HTTP clients that use stored browser-OAuth credentials with refresh."""

from __future__ import annotations

import logging
import time

from vainu_cli._async_client import VainuJWTAPIClient
from vainu_cli._sync_client import VainuJWTSyncClient
from vainu_cli.auth.storage import StoredCredentials, TokenStore
from vainu_cli.common import DEFAULT_BASE_URL, OAUTH_TOKEN_ENDPOINT

logger = logging.getLogger(__name__)


def _apply_refreshed_tokens(
    stored: StoredCredentials, data: dict, *, fallback_refresh: str
) -> None:
    """Update `stored` in place from a `/oauth/token/` refresh response."""
    stored.access_token = data["access_token"]
    # DOT rotates refresh tokens by default; tolerate missing field for safety.
    stored.refresh_token = data.get("refresh_token") or fallback_refresh
    stored.expires_at = time.time() + int(data.get("expires_in", 3600))
    stored.obtained_at = time.time()
    if "scope" in data:
        stored.scope = data["scope"]
    if "token_type" in data:
        stored.token_type = data["token_type"]


class VainuBrowserAuthSyncClient(VainuJWTSyncClient):
    """Sync client that uses `StoredCredentials` and refreshes via OAuth."""

    def __init__(
        self,
        *,
        stored: StoredCredentials,
        store: TokenStore | None,
        base_url: str | None = None,
        language: str | None = None,
    ) -> None:
        # Bypass VainuJWTSyncClient.__init__'s empty-token check by passing a
        # placeholder; we never use self.jwt_token in this subclass.
        super().__init__(
            refresh_token=stored.refresh_token or "<browser>",
            base_url=base_url or stored.base_url or DEFAULT_BASE_URL,
            language=language,
        )
        self._stored = stored
        self._store = store
        self._access_token = stored.access_token
        self._token_expires_at = stored.expires_at

    def _ensure_access_token(self) -> None:
        if self._access_token and time.time() < self._token_expires_at - 60:
            return
        if not self._stored.refresh_token:
            raise RuntimeError(
                "Access token expired and no refresh token is available. Run `vainu login` again."
            )
        response = self._http.post(
            f"{self._base_url.rstrip('/')}{OAUTH_TOKEN_ENDPOINT}",
            data={
                "grant_type": "refresh_token",
                "refresh_token": self._stored.refresh_token,
                "client_id": self._stored.client_id,
                "scope": self._stored.scope,
            },
            timeout=self._timeout,
        )
        response.raise_for_status()
        data = response.json()
        _apply_refreshed_tokens(self._stored, data, fallback_refresh=self._stored.refresh_token)
        self._access_token = self._stored.access_token
        self._token_expires_at = self._stored.expires_at
        if self._store is not None:
            try:
                self._store.save(self._stored)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to persist refreshed credentials: %s", exc)


class VainuBrowserAuthAPIClient(VainuJWTAPIClient):
    """Async client that uses `StoredCredentials` and refreshes via OAuth."""

    def __init__(
        self,
        *,
        stored: StoredCredentials,
        store: TokenStore | None,
        base_url: str | None = None,
        language: str | None = None,
    ) -> None:
        super().__init__(
            refresh_token=stored.refresh_token or "<browser>",
            base_url=base_url or stored.base_url or DEFAULT_BASE_URL,
            language=language,
        )
        self._stored = stored
        self._store = store
        self._access_token = stored.access_token
        self._token_expires_at = stored.expires_at

    async def _ensure_access_token(self) -> None:
        if self._access_token and time.time() < self._token_expires_at - 60:
            return
        if not self._stored.refresh_token:
            raise RuntimeError(
                "Access token expired and no refresh token is available. Run `vainu login` again."
            )
        response = await self._http.post(
            OAUTH_TOKEN_ENDPOINT,
            data={
                "grant_type": "refresh_token",
                "refresh_token": self._stored.refresh_token,
                "client_id": self._stored.client_id,
                "scope": self._stored.scope,
            },
        )
        response.raise_for_status()
        data = response.json()
        _apply_refreshed_tokens(self._stored, data, fallback_refresh=self._stored.refresh_token)
        self._access_token = self._stored.access_token
        self._token_expires_at = self._stored.expires_at
        if self._store is not None:
            try:
                self._store.save(self._stored)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to persist refreshed credentials: %s", exc)
