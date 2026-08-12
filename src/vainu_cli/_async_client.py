"""Async Vainu API client (httpx-based)."""

import asyncio
import http
import logging
import time
from dataclasses import dataclass
from urllib.parse import urljoin

import httpx

from vainu_cli.auth.storage import ClientCredentialsCache
from vainu_cli.common import (
    DEFAULT_BASE_URL,
    DEFAULT_RESPONSE_FORMAT,
    DEFAULT_TIMEOUT_SECONDS,
    JWT_REFRESH_ENDPOINT_PATH,
    AsyncJobState,
    ResponseFormat,
    parse_response,
)

logger = logging.getLogger(__name__)


@dataclass
class AsyncResult:
    download_url: str | None
    duration: int
    result_url: str | None = None

    async def json(self) -> dict:
        if not self.download_url:
            if self.result_url:
                raise RuntimeError(f"Result exists in result_url: {self.result_url}")
            raise RuntimeError("Async result is missing both download_url and result_url")
        async with httpx.AsyncClient() as client:
            logger.info("Downloading and parsing JSON from: %s", self.download_url)
            response = await client.get(self.download_url)
            response.raise_for_status()
            return response.json()

    async def download_to_file(self, output_path: str) -> bool:
        """Download large file using curl (follows redirects, handles compression)."""
        if self.result_url and not self.download_url:
            logger.info("Result exists in result_url: %s", self.result_url)
            return False
        if not self.download_url:
            raise RuntimeError("Async result is missing both download_url and result_url")
        try:
            logger.info("Downloading file to %s", output_path)
            process = await asyncio.create_subprocess_exec(
                "curl",
                "-L",
                "-s",
                "-f",
                "-o",
                output_path,
                "--compressed",
                self.download_url,
            )
            await process.wait()
            if process.returncode != 0:
                raise RuntimeError(f"curl exited with code {process.returncode}")
            logger.info("Downloaded file: %s", output_path)
            return True
        except FileNotFoundError as exc:
            raise RuntimeError(
                "curl is not installed. Install curl or use .json() / .download_url directly."
            ) from exc


def _raise_for_status_with_body(response: httpx.Response) -> httpx.Response:
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as err:
        logger.error(
            "HTTP error %s: %s — body: %s",
            response.status_code,
            err,
            response.text,
        )
        if response.status_code not in (
            http.HTTPStatus.BAD_REQUEST,
            http.HTTPStatus.FORBIDDEN,
            http.HTTPStatus.NOT_FOUND,
        ):
            raise
    return response


class VainuAPIBaseClient:
    ASYNC_POLL_INTERVAL = 3  # seconds
    ASYNC_POLL_MAX_RETRIES = 5

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        timeout: int = DEFAULT_TIMEOUT_SECONDS,
        language: str | None = None,
    ) -> None:
        self._base_url = base_url
        self._language = language
        self._http = httpx.AsyncClient(base_url=base_url, timeout=timeout)

    async def request(self, method: http.HTTPMethod, path: str, **kwargs) -> httpx.Response:
        """Make an authenticated request."""
        logger.debug("Vainu API %s %s", method, path)
        response = await self._send(method, path, **kwargs)
        if response.status_code == http.HTTPStatus.UNAUTHORIZED and (
            await self._invalidate_credentials()
        ):
            logger.debug("Access token rejected — retrying once with a fresh token")
            response = await self._send(method, path, **kwargs)
        _raise_for_status_with_body(response)
        return response

    async def _send(self, method: http.HTTPMethod, path: str, **kwargs) -> httpx.Response:
        headers = await self.get_headers()
        if self._language:
            headers["Accept-Language"] = self._language
        return await self._http.request(
            method,
            path,
            headers=headers,
            **kwargs,
        )

    async def _invalidate_credentials(self) -> bool:
        """Discard credentials the server just rejected with a 401.

        Returns True when something was dropped and the request is worth
        retrying — only clients that reuse a persisted token override this.
        """
        return False

    async def request_api_async(
        self,
        method: http.HTTPMethod,
        path: str,
        payload: dict | str,
        format: ResponseFormat = DEFAULT_RESPONSE_FORMAT,
    ) -> AsyncResult:
        """Submit an async job and poll until complete."""
        separator = "&" if "?" in path else "?"
        get_async_job = await self.request(
            method=method,
            path=f"{path}{separator}async_format={format}",
            json=payload if isinstance(payload, dict) else None,
        )
        link_to_poll = get_async_job.json().get("link")
        consecutive_errors = 0
        while True:
            try:
                poll_response = await self.request(method=http.HTTPMethod.GET, path=link_to_poll)
                consecutive_errors = 0
            except (
                httpx.RemoteProtocolError,
                httpx.ConnectError,
                httpx.ReadError,
                httpx.TimeoutException,
            ) as exc:
                consecutive_errors += 1
                if consecutive_errors > self.ASYNC_POLL_MAX_RETRIES:
                    raise
                logger.warning(
                    "Poll request failed (%s/%s): %s — retrying in %ss",
                    consecutive_errors,
                    self.ASYNC_POLL_MAX_RETRIES,
                    exc,
                    self.ASYNC_POLL_INTERVAL,
                )
                await asyncio.sleep(self.ASYNC_POLL_INTERVAL)
                continue
            poll_data = poll_response.json()
            status = AsyncJobState(poll_data.get("state"))
            progress = poll_data.get("progress", 0)
            if status == AsyncJobState.COMPLETED:
                return AsyncResult(
                    download_url=poll_data.get("download_link"),
                    duration=poll_data.get("duration"),
                    result_url=payload.get("result_url") if isinstance(payload, dict) else None,
                )
            if status not in {AsyncJobState.ACCEPTED, AsyncJobState.PROCESS}:
                raise RuntimeError(f"Async job failed with state {status!r}: {poll_data}")
            logger.debug(
                "Async job %s — polling again in %ss (progress: %s)",
                status,
                self.ASYNC_POLL_INTERVAL,
                progress,
            )
            await asyncio.sleep(self.ASYNC_POLL_INTERVAL)

    async def companies_async(
        self,
        payload: dict | str,
        format: ResponseFormat = DEFAULT_RESPONSE_FORMAT,
    ) -> AsyncResult:
        path = "/v2/companies/async/"
        if isinstance(payload, dict):
            return await self.request_api_async(
                path=path, method=http.HTTPMethod.POST, payload=payload, format=format
            )
        if isinstance(payload, str):
            return await self.request_api_async(
                method=http.HTTPMethod.GET,
                path=f"{path}{payload}",
                format=format,
                payload={},
            )
        raise ValueError("payload must be str or dict")

    async def companies(
        self,
        payload: dict | str,
        format: ResponseFormat = DEFAULT_RESPONSE_FORMAT,
    ) -> dict | str:
        path = "/v2/companies/"
        if isinstance(payload, dict):
            return parse_response(
                await self.request(
                    method=http.HTTPMethod.POST,
                    path=f"{path}?format={format}",
                    json=payload,
                ),
                format,
            )
        if isinstance(payload, str):
            return parse_response(
                await self.request(
                    method=http.HTTPMethod.GET,
                    path=f"{path}{payload}&format={format}",
                ),
                format,
            )
        raise ValueError("payload must be str or dict")

    async def organizations(
        self,
        payload: dict,
        format: ResponseFormat = DEFAULT_RESPONSE_FORMAT,
    ) -> dict | str:
        return parse_response(
            await self.request(
                method=http.HTTPMethod.POST,
                path=f"/v3/organizations/?format={format}",
                json=payload,
            ),
            format,
        )

    async def organizations_async(
        self,
        payload: dict,
        format: ResponseFormat = DEFAULT_RESPONSE_FORMAT,
    ) -> AsyncResult:
        return await self.request_api_async(
            method=http.HTTPMethod.POST,
            path="/v3/organizations/async/",
            payload=payload,
            format=format,
        )

    async def signals_news(
        self,
        payload: dict,
        format: ResponseFormat = DEFAULT_RESPONSE_FORMAT,
    ) -> list | str:
        return parse_response(
            await self.request(
                method=http.HTTPMethod.POST,
                path=f"/v3/signals/news/?format={format}",
                json=payload,
            ),
            format,
        )

    async def signals_data_changes(
        self,
        payload: dict,
        format: ResponseFormat = DEFAULT_RESPONSE_FORMAT,
    ) -> list | str:
        return parse_response(
            await self.request(
                method=http.HTTPMethod.POST,
                path=f"/v3/signals/data-changes/?format={format}",
                json=payload,
            ),
            format,
        )

    async def close(self) -> None:
        await self._http.aclose()

    async def get_headers(self) -> dict:
        raise NotImplementedError


class VainuAPIKeyClient(VainuAPIBaseClient):
    """Async client using a static API key."""

    def __init__(
        self,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        language: str | None = None,
    ) -> None:
        super().__init__(base_url=base_url, language=language)
        if not api_key:
            raise ValueError("api_key must not be empty. Set VAINU_API_KEY or pass api_key=...")
        self.api_key = api_key

    async def get_headers(self) -> dict:
        return {"API-Key": self.api_key}


class VainuJWTAPIClient(VainuAPIBaseClient):
    """Async client with automatic JWT refresh token exchange."""

    def __init__(
        self,
        refresh_token: str,
        base_url: str = DEFAULT_BASE_URL,
        language: str | None = None,
    ) -> None:
        super().__init__(base_url=base_url, language=language)
        if not refresh_token:
            raise ValueError("refresh_token must not be empty.")
        self.jwt_token = refresh_token
        self._access_token: str | None = None
        self._token_expires_at: float = 0

    async def get_headers(self) -> dict:
        await self._ensure_access_token()
        return {"Authorization": f"Bearer {self._access_token}"}

    async def _ensure_access_token(self) -> None:
        """Fetch a new access token if missing or expiring within 60 seconds."""
        if self._access_token and time.time() < self._token_expires_at - 60:
            return
        refresh_url = urljoin(
            f"{self._base_url.rstrip('/')}/",
            JWT_REFRESH_ENDPOINT_PATH.lstrip("/"),
        )
        response = await self._http.post(
            refresh_url,
            json={"refresh": self.jwt_token},
        )
        _raise_for_status_with_body(response)
        response.raise_for_status()
        data = response.json()
        self._access_token = data["access"]
        self._token_expires_at = time.time() + int(data.get("expires_in", 3600))


class VainuOAuthAPIClient(VainuAPIBaseClient):
    """Async client with automatic OAuth 2.0 client credentials token management."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        scope: str = "vainu:api",
        base_url: str = DEFAULT_BASE_URL,
        language: str | None = None,
        token_cache: bool | None = None,
    ) -> None:
        super().__init__(base_url=base_url, language=language)
        if not client_id or not client_secret:
            raise ValueError(
                "client_id and client_secret are required. "
                "Set VAINU_CLIENT_ID / VAINU_CLIENT_SECRET or pass them directly."
            )
        self.client_id = client_id
        self.client_secret = client_secret
        self.scope = scope
        self._access_token: str | None = None
        self._token_expires_at: float = 0
        self._token_from_cache = False
        self._cache = ClientCredentialsCache(
            base_url=base_url,
            client_id=client_id,
            scope=scope,
            enabled=token_cache,
        )

    async def get_headers(self) -> dict:
        await self._ensure_token()
        return {"Authorization": f"Bearer {self._access_token}"}

    async def _ensure_token(self) -> None:
        """Reuse a live token — in memory, then from the store — else mint one."""
        if self._access_token and time.time() < self._token_expires_at - 60:
            return
        # keyring talks to the OS over D-Bus / Security.framework and blocks.
        cached = await asyncio.to_thread(self._cache.load)
        if cached is not None:
            self._access_token, self._token_expires_at = cached
            self._token_from_cache = True
            return
        response = await self._http.post(
            "/oauth/token/",
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "scope": self.scope,
            },
        )
        response.raise_for_status()
        data = response.json()
        self._access_token = data["access_token"]
        self._token_expires_at = time.time() + data["expires_in"]
        self._token_from_cache = False
        await asyncio.to_thread(self._cache.save, self._access_token, self._token_expires_at)

    async def _invalidate_credentials(self) -> bool:
        """Drop a rejected token, and retry only if it came from the store.

        A cached token can be revoked server-side while it still looks live to
        us; one that was minted moments ago and still draws a 401 means the
        credentials are wrong, so retrying would just burn another round-trip.
        """
        if not self._token_from_cache:
            return False
        self._access_token = None
        self._token_expires_at = 0
        self._token_from_cache = False
        await asyncio.to_thread(self._cache.clear)
        return True
