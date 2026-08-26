"""Async Vainu API client (httpx-based)."""

import asyncio
import http
import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from urllib.parse import urljoin

import httpx

from vainu_cli.auth.storage import ClientCredentialsCache
from vainu_cli.common import (
    DEFAULT_ASYNC_MAX_WAIT_SECONDS,
    DEFAULT_BASE_URL,
    DEFAULT_RESPONSE_FORMAT,
    DEFAULT_STREAM_FORMAT,
    DEFAULT_TIMEOUT_SECONDS,
    JWT_REFRESH_ENDPOINT_PATH,
    RETRYABLE_STATUS_CODES,
    AsyncJobState,
    ResponseFormat,
    companies_request,
    count_is_pending,
    count_payload,
    ensure_streamable,
    lines_from_text,
    parse_response,
    poll_retry_delay,
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


async def _aiter_nonempty_lines(response: httpx.Response) -> AsyncIterator[str]:
    async for line in response.aiter_lines():
        if line:
            yield line


async def _aiter_lines_from_text(text: str) -> AsyncIterator[str]:
    for line in lines_from_text(text):
        yield line


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


# Failures a poll loop should sit out rather than surface. Transport errors
# always qualify; an HTTP status only when it is one of RETRYABLE_STATUS_CODES.
POLL_RETRY_ERRORS = (
    httpx.RemoteProtocolError,
    httpx.ConnectError,
    httpx.ReadError,
    httpx.TimeoutException,
    httpx.HTTPStatusError,
)


def _is_retryable_poll_error(exc: Exception) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in RETRYABLE_STATUS_CODES
    return True


class VainuAPIBaseClient:
    ASYNC_POLL_INTERVAL = 3  # seconds
    ASYNC_MAX_WAIT_SECONDS = DEFAULT_ASYNC_MAX_WAIT_SECONDS
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
        self._async_max_wait_seconds = self.ASYNC_MAX_WAIT_SECONDS

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

    async def _send_stream(self, method: http.HTTPMethod, path: str, **kwargs) -> httpx.Response:
        """Send a request but leave the body unread, so it can be consumed lazily."""
        headers = await self.get_headers()
        if self._language:
            headers["Accept-Language"] = self._language
        request = self._http.build_request(str(method), path, headers=headers, **kwargs)
        return await self._http.send(request, stream=True)

    @asynccontextmanager
    async def stream(
        self, method: http.HTTPMethod, path: str, **kwargs
    ) -> AsyncIterator[AsyncIterator[str]]:
        """Yield the response body one line at a time, as it arrives.

        Same auth-retry contract as `request`, but the body is never buffered in
        full — so a slow export can be written out while the server is still
        producing it. The response is released when the context manager exits,
        even if the caller stops iterating early.
        """
        logger.debug("Vainu API %s %s (streaming)", method, path)
        response = await self._send_stream(method, path, **kwargs)
        if response.status_code == http.HTTPStatus.UNAUTHORIZED and (
            await self._invalidate_credentials()
        ):
            logger.debug("Access token rejected — retrying once with a fresh token")
            await response.aclose()
            response = await self._send_stream(method, path, **kwargs)
        try:
            if response.status_code >= http.HTTPStatus.BAD_REQUEST:
                # .text is only available once the stream has been drained, and
                # the body is an error payload rather than rows either way.
                await response.aread()
                _raise_for_status_with_body(response)
                yield _aiter_lines_from_text(response.text)
            else:
                yield _aiter_nonempty_lines(response)
        finally:
            await response.aclose()

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
        started_at = time.monotonic()
        consecutive_errors = 0
        while True:
            if time.monotonic() - started_at > self._async_max_wait_seconds:
                raise TimeoutError(
                    f"Async job polling exceeded {self._async_max_wait_seconds}s "
                    f"for link {link_to_poll}"
                )
            try:
                poll_response = await self.request(method=http.HTTPMethod.GET, path=link_to_poll)
                consecutive_errors = 0
            except POLL_RETRY_ERRORS as exc:
                if not _is_retryable_poll_error(exc):
                    raise
                consecutive_errors += 1
                if consecutive_errors > self.ASYNC_POLL_MAX_RETRIES:
                    raise
                retry_in = poll_retry_delay(self.ASYNC_POLL_INTERVAL, consecutive_errors)
                logger.warning(
                    "Poll request failed (%s/%s): %s — retrying in %ss",
                    consecutive_errors,
                    self.ASYNC_POLL_MAX_RETRIES,
                    exc,
                    retry_in,
                )
                await asyncio.sleep(retry_in)
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
        method, path, json_body = companies_request(payload, format)
        return parse_response(
            await self.request(method=method, path=path, json=json_body),
            format,
        )

    @asynccontextmanager
    async def stream_companies(
        self,
        payload: dict | str,
        format: ResponseFormat = DEFAULT_STREAM_FORMAT,
    ) -> AsyncIterator[AsyncIterator[str]]:
        """Stream company data line by line (`csv` / `jsonl` only)."""
        ensure_streamable(format)
        method, path, json_body = companies_request(payload, format)
        async with self.stream(method=method, path=path, json=json_body) as lines:
            yield lines

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

    @asynccontextmanager
    async def stream_organizations(
        self,
        payload: dict,
        format: ResponseFormat = DEFAULT_STREAM_FORMAT,
    ) -> AsyncIterator[AsyncIterator[str]]:
        """Stream organization data line by line (`csv` / `jsonl` only)."""
        ensure_streamable(format)
        async with self.stream(
            method=http.HTTPMethod.POST,
            path=f"/v3/organizations/?format={format}",
            json=payload,
        ) as lines:
            yield lines

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

    async def organizations_search(
        self,
        payload: dict,
        format: ResponseFormat = DEFAULT_RESPONSE_FORMAT,
    ) -> dict | list | str:
        """Fuzzy free-text lookup by company name, business id or domain.

        Unlike `organizations`, this takes a plain `search` term instead of a VQL
        `query`, and answers with a bare array of the requested `fields` — no
        `count` or `next` wrapper. Only the fields named in `fields` come back;
        ask for none and every hit is an empty object.

        Paging is best-effort: the endpoint ignores the `skip` key its API
        reference documents, and `offset` slices a relevance-ranked pool whose
        size follows `limit` — so raise `limit` instead of offsetting deep.
        """
        return parse_response(
            await self.request(
                method=http.HTTPMethod.POST,
                path=f"/v3/organizations/search/?format={format}",
                json=payload,
            ),
            format,
        )

    @asynccontextmanager
    async def stream_organizations_search(
        self,
        payload: dict,
        format: ResponseFormat = DEFAULT_STREAM_FORMAT,
    ) -> AsyncIterator[AsyncIterator[str]]:
        """Stream fuzzy-search hits line by line (`csv` / `jsonl` only)."""
        ensure_streamable(format)
        async with self.stream(
            method=http.HTTPMethod.POST,
            path=f"/v3/organizations/search/?format={format}",
            json=payload,
        ) as lines:
            yield lines

    async def organizations_count(
        self,
        payload: dict,
        wait: bool = False,
        poll_interval: int | None = None,
        max_wait_seconds: int | None = None,
    ) -> dict:
        """Count the organizations matching a query, without returning any rows.

        The endpoint ignores `fields`, `limit` and `offset` and answers with count
        metadata only. `order` is dropped before sending — the count endpoint 400s on
        it — so a payload written for `organizations` can be counted unchanged. It
        also defaults to `async: true`, so a cold cache replies
        `{"count": null, "status": "scheduled"}`. With `wait=True` the same payload
        is re-POSTed every `poll_interval` seconds until `status` goes terminal —
        re-sending the payload is the documented way to collect the finished count.
        """
        poll_interval = self.ASYNC_POLL_INTERVAL if poll_interval is None else poll_interval
        first_request = True
        started_at = time.monotonic()
        consecutive_errors = 0
        while True:
            try:
                api_response = await self.request(
                    method=http.HTTPMethod.POST,
                    path="/v3/organizations/count/?format=json",
                    json=count_payload(payload, first_request=first_request),
                )
                response = api_response.json()
                first_request = False
                consecutive_errors = 0
            except POLL_RETRY_ERRORS as exc:
                if not _is_retryable_poll_error(exc):
                    raise
                consecutive_errors += 1
                if consecutive_errors > self.ASYNC_POLL_MAX_RETRIES:
                    raise
                retry_in = poll_retry_delay(poll_interval, consecutive_errors)
                logger.warning(
                    "Count request failed (%s/%s): %s — retrying in %ss",
                    consecutive_errors,
                    self.ASYNC_POLL_MAX_RETRIES,
                    exc,
                    retry_in,
                )
                await asyncio.sleep(retry_in)
                continue
            if not wait or not count_is_pending(response):
                return response
            if max_wait_seconds is not None and time.monotonic() - started_at > max_wait_seconds:
                raise TimeoutError(
                    f"Count polling exceeded {max_wait_seconds}s "
                    f"(last status {response.get('status')!r})"
                )
            logger.debug(
                "Count status: %s — polling again in %ss",
                response.get("status"),
                poll_interval,
            )
            await asyncio.sleep(poll_interval)

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

    @asynccontextmanager
    async def stream_signals_news(
        self,
        payload: dict,
        format: ResponseFormat = DEFAULT_STREAM_FORMAT,
    ) -> AsyncIterator[AsyncIterator[str]]:
        """Stream news signals line by line (`jsonl` only — the API renders no csv)."""
        ensure_streamable(format)
        async with self.stream(
            method=http.HTTPMethod.POST,
            path=f"/v3/signals/news/?format={format}",
            json=payload,
        ) as lines:
            yield lines

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

    @asynccontextmanager
    async def stream_signals_data_changes(
        self,
        payload: dict,
        format: ResponseFormat = DEFAULT_STREAM_FORMAT,
    ) -> AsyncIterator[AsyncIterator[str]]:
        """Stream data-change signals line by line (`jsonl` only)."""
        ensure_streamable(format)
        async with self.stream(
            method=http.HTTPMethod.POST,
            path=f"/v3/signals/data-changes/?format={format}",
            json=payload,
        ) as lines:
            yield lines

    async def enrichment_agent(
        self,
        payload: dict,
        format: ResponseFormat = DEFAULT_RESPONSE_FORMAT,
    ) -> dict | str:
        """Run an enrichment agent prompt against one company.

        `payload` carries the prompt id created in the Vainu UI, the `database`
        and the `business_id`; `refresh: True` re-runs a prompt that already ran
        for that company instead of reusing the cached answer. The result is not
        paginated — it is a single object of the prompt's own fields under
        `response`. There is no streaming variant for the same reason.
        """
        return parse_response(
            await self.request(
                method=http.HTTPMethod.POST,
                path=f"/v3/enrichment_agent/?format={format}",
                json=payload,
            ),
            format,
        )

    async def organization_fields(
        self,
        api_versions: str = "v3",
    ) -> list:
        """Return organization field metadata (filterable vs output availability)."""
        return parse_response(
            await self.request(
                method=http.HTTPMethod.GET,
                path=f"/v3/organizations_fields/?api_versions={api_versions}",
            ),
            DEFAULT_RESPONSE_FORMAT,
        )

    async def organization_lists(
        self,
        format: ResponseFormat = DEFAULT_RESPONSE_FORMAT,
    ) -> list | str:
        """List all accessible organization lists (static and dynamic)."""
        return parse_response(
            await self.request(
                method=http.HTTPMethod.GET,
                path=f"/v3/lists/organizations/?format={format}",
            ),
            format,
        )

    async def organization_list_get(
        self,
        list_id: str,
        format: ResponseFormat = DEFAULT_RESPONSE_FORMAT,
    ) -> dict | str:
        """Retrieve one organization list summary by id."""
        return parse_response(
            await self.request(
                method=http.HTTPMethod.GET,
                path=f"/v3/lists/organizations/{list_id}/?format={format}",
            ),
            format,
        )

    async def organization_list_delete(self, list_id: str) -> None:
        """Delete an organization list (static or dynamic) by id."""
        (
            await self.request(
                method=http.HTTPMethod.DELETE,
                path=f"/v3/lists/organizations/{list_id}/",
            )
        ).raise_for_status()

    async def organization_lists_static(
        self,
        format: ResponseFormat = DEFAULT_RESPONSE_FORMAT,
    ) -> list | str:
        """List static organization lists."""
        return parse_response(
            await self.request(
                method=http.HTTPMethod.GET,
                path=f"/v3/lists/organizations/static/?format={format}",
            ),
            format,
        )

    async def organization_list_static_get(
        self,
        list_id: str,
        format: ResponseFormat = DEFAULT_RESPONSE_FORMAT,
    ) -> dict | str:
        """Retrieve one static organization list."""
        return parse_response(
            await self.request(
                method=http.HTTPMethod.GET,
                path=f"/v3/lists/organizations/static/{list_id}/?format={format}",
            ),
            format,
        )

    async def organization_list_static_create(
        self,
        payload: dict,
        format: ResponseFormat = DEFAULT_RESPONSE_FORMAT,
    ) -> dict | str:
        """Create a static organization list."""
        return parse_response(
            await self.request(
                method=http.HTTPMethod.POST,
                path=f"/v3/lists/organizations/static/?format={format}",
                json=payload,
            ),
            format,
        )

    async def organization_list_static_update(
        self,
        list_id: str,
        payload: dict,
        format: ResponseFormat = DEFAULT_RESPONSE_FORMAT,
    ) -> dict | str:
        """Partially update a static organization list."""
        return parse_response(
            await self.request(
                method=http.HTTPMethod.PATCH,
                path=f"/v3/lists/organizations/static/{list_id}/?format={format}",
                json=payload,
            ),
            format,
        )

    async def organization_list_static_delete(self, list_id: str) -> None:
        """Delete a static organization list."""
        (
            await self.request(
                method=http.HTTPMethod.DELETE,
                path=f"/v3/lists/organizations/static/{list_id}/",
            )
        ).raise_for_status()

    async def organization_list_static_add(self, list_id: str, business_ids: list[str]) -> None:
        """Add business IDs to a static organization list."""
        (
            await self.request(
                method=http.HTTPMethod.PATCH,
                path=f"/v3/lists/organizations/static/{list_id}/add/",
                json=business_ids,
            )
        ).raise_for_status()

    async def organization_list_static_remove(self, list_id: str, business_ids: list[str]) -> None:
        """Remove business IDs from a static organization list."""
        (
            await self.request(
                method=http.HTTPMethod.PATCH,
                path=f"/v3/lists/organizations/static/{list_id}/remove/",
                json=business_ids,
            )
        ).raise_for_status()

    async def organization_lists_dynamic(
        self,
        format: ResponseFormat = DEFAULT_RESPONSE_FORMAT,
    ) -> list | str:
        """List dynamic organization lists."""
        return parse_response(
            await self.request(
                method=http.HTTPMethod.GET,
                path=f"/v3/lists/organizations/dynamic/?format={format}",
            ),
            format,
        )

    async def organization_list_dynamic_get(
        self,
        list_id: str,
        format: ResponseFormat = DEFAULT_RESPONSE_FORMAT,
    ) -> dict | str:
        """Retrieve one dynamic organization list."""
        return parse_response(
            await self.request(
                method=http.HTTPMethod.GET,
                path=f"/v3/lists/organizations/dynamic/{list_id}/?format={format}",
            ),
            format,
        )

    async def organization_list_dynamic_create(
        self,
        payload: dict,
        format: ResponseFormat = DEFAULT_RESPONSE_FORMAT,
    ) -> dict | str:
        """Create a dynamic organization list."""
        return parse_response(
            await self.request(
                method=http.HTTPMethod.POST,
                path=f"/v3/lists/organizations/dynamic/?format={format}",
                json=payload,
            ),
            format,
        )

    async def organization_list_dynamic_update(
        self,
        list_id: str,
        payload: dict,
        format: ResponseFormat = DEFAULT_RESPONSE_FORMAT,
    ) -> dict | str:
        """Partially update a dynamic organization list."""
        return parse_response(
            await self.request(
                method=http.HTTPMethod.PATCH,
                path=f"/v3/lists/organizations/dynamic/{list_id}/?format={format}",
                json=payload,
            ),
            format,
        )

    async def organization_list_dynamic_delete(self, list_id: str) -> None:
        """Delete a dynamic organization list."""
        (
            await self.request(
                method=http.HTTPMethod.DELETE,
                path=f"/v3/lists/organizations/dynamic/{list_id}/",
            )
        ).raise_for_status()

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
        timeout: int = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        super().__init__(base_url=base_url, language=language, timeout=timeout)
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
        timeout: int = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        super().__init__(base_url=base_url, language=language, timeout=timeout)
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
        timeout: int = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        super().__init__(base_url=base_url, language=language, timeout=timeout)
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
