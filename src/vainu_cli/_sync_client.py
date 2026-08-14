"""Synchronous Vainu API client (requests-based)."""

import http
import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from urllib.parse import urljoin

import requests

from vainu_cli.auth.storage import ClientCredentialsCache
from vainu_cli.common import (
    DEFAULT_BASE_URL,
    DEFAULT_RESPONSE_FORMAT,
    DEFAULT_STREAM_FORMAT,
    DEFAULT_TIMEOUT_SECONDS,
    JWT_REFRESH_ENDPOINT_PATH,
    AsyncJobState,
    ResponseFormat,
    companies_request,
    ensure_streamable,
    lines_from_text,
    parse_response,
)

logger = logging.getLogger(__name__)


@dataclass
class AsyncResult:
    download_url: str | None
    duration: int
    result_url: str | None = None

    def json(self) -> dict:
        if not self.download_url:
            if self.result_url:
                raise RuntimeError(f"Result exists in result_url: {self.result_url}")
            raise RuntimeError("Async result is missing both download_url and result_url")
        logger.info("Downloading and parsing JSON from: %s", self.download_url)
        response = requests.get(self.download_url, timeout=DEFAULT_TIMEOUT_SECONDS)
        response.raise_for_status()
        return response.json()

    def download_to_file(self, output_path: str) -> bool:
        if self.result_url and not self.download_url:
            logger.info("Result exists in result_url: %s", self.result_url)
            return False
        if not self.download_url:
            raise RuntimeError("Async result is missing both download_url and result_url")
        logger.info("Downloading file to %s", self.download_url)
        with requests.get(
            self.download_url, stream=True, timeout=DEFAULT_TIMEOUT_SECONDS
        ) as response:
            response.raise_for_status()
            with open(output_path, "wb") as output_file:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        output_file.write(chunk)
        logger.info("Downloaded file: %s", output_path)
        return True


def _iter_nonempty_lines(response: requests.Response) -> Iterator[str]:
    """Decode the body's lines as UTF-8, skipping blanks.

    Decoding explicitly rather than via `decode_unicode=True`: requests guesses
    ISO-8859-1 for a `text/*` response that omits its charset, which would
    mangle any non-ASCII row.
    """
    for line in response.iter_lines():
        if line:
            yield line.decode("utf-8")


def _raise_for_status_with_body(response: requests.Response) -> requests.Response:
    try:
        response.raise_for_status()
    except requests.exceptions.HTTPError as err:
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
    ASYNC_MAX_WAIT_SECONDS = 14400  # 4 hours
    ASYNC_POLL_MAX_RETRIES = 5

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        timeout: int = DEFAULT_TIMEOUT_SECONDS,
        language: str | None = None,
    ) -> None:
        self._base_url = base_url
        self._timeout = timeout
        self._language = language
        self._http = requests.Session()
        self._async_max_wait_seconds = self.ASYNC_MAX_WAIT_SECONDS

    def request(self, method: http.HTTPMethod, path: str, **kwargs) -> requests.Response:
        logger.debug("Vainu API %s %s", method, path)
        url = path if path.startswith(("http://", "https://")) else f"{self._base_url}{path}"
        response = self._send(method, url, **kwargs)
        if response.status_code == http.HTTPStatus.UNAUTHORIZED and self._invalidate_credentials():
            logger.debug("Access token rejected — retrying once with a fresh token")
            response = self._send(method, url, **kwargs)
        _raise_for_status_with_body(response)
        return response

    def _send(self, method: http.HTTPMethod, url: str, **kwargs) -> requests.Response:
        headers = self.get_headers()
        if self._language:
            headers["Accept-Language"] = self._language
        return self._http.request(
            method=str(method),
            url=url,
            headers=headers,
            timeout=self._timeout,
            **kwargs,
        )

    @contextmanager
    def stream(self, method: http.HTTPMethod, path: str, **kwargs) -> Iterator[Iterator[str]]:
        """Yield the response body one line at a time, as it arrives.

        Same auth-retry contract as `request`, but the body is never buffered in
        full — so a slow export can be written out while the server is still
        producing it. The response is released when the context manager exits,
        even if the caller stops iterating early.
        """
        logger.debug("Vainu API %s %s (streaming)", method, path)
        url = path if path.startswith(("http://", "https://")) else f"{self._base_url}{path}"
        response = self._send(method, url, stream=True, **kwargs)
        if response.status_code == http.HTTPStatus.UNAUTHORIZED and self._invalidate_credentials():
            logger.debug("Access token rejected — retrying once with a fresh token")
            response.close()
            response = self._send(method, url, stream=True, **kwargs)
        try:
            if response.status_code >= http.HTTPStatus.BAD_REQUEST:
                # Draining the body first so .text works, and because an error
                # payload is not rows either way.
                response.content  # noqa: B018
                _raise_for_status_with_body(response)
                yield lines_from_text(response.text)
            else:
                yield _iter_nonempty_lines(response)
        finally:
            response.close()

    def _invalidate_credentials(self) -> bool:
        """Discard credentials the server just rejected with a 401.

        Returns True when something was dropped and the request is worth
        retrying — only clients that reuse a persisted token override this.
        """
        return False

    def request_api_async(
        self,
        method: http.HTTPMethod,
        path: str,
        payload: dict | str,
        format: ResponseFormat = DEFAULT_RESPONSE_FORMAT,
    ) -> AsyncResult:
        """Submit an async job and poll until complete."""
        separator = "&" if "?" in path else "?"
        get_async_job = self.request(
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
                poll_response = self.request(method=http.HTTPMethod.GET, path=link_to_poll)
                consecutive_errors = 0
            except (
                requests.exceptions.ConnectionError,
                requests.exceptions.Timeout,
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
                time.sleep(self.ASYNC_POLL_INTERVAL)
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
                "Async job state: %s — polling again in %ss (progress: %s)",
                status,
                self.ASYNC_POLL_INTERVAL,
                progress,
            )
            time.sleep(self.ASYNC_POLL_INTERVAL)

    def companies_async(
        self,
        payload: dict | str,
        format: ResponseFormat = DEFAULT_RESPONSE_FORMAT,
    ) -> AsyncResult:
        path = "/v2/companies/async/"
        if isinstance(payload, dict):
            return self.request_api_async(
                path=path, method=http.HTTPMethod.POST, payload=payload, format=format
            )
        if isinstance(payload, str):
            return self.request_api_async(
                method=http.HTTPMethod.GET,
                path=f"{path}{payload}",
                format=format,
                payload={},
            )
        raise ValueError("payload must be str or dict")

    def companies(
        self,
        payload: dict | str,
        format: ResponseFormat = DEFAULT_RESPONSE_FORMAT,
    ) -> dict | str:
        method, path, json_body = companies_request(payload, format)
        return parse_response(
            self.request(method=method, path=path, json=json_body),
            format,
        )

    @contextmanager
    def stream_companies(
        self,
        payload: dict | str,
        format: ResponseFormat = DEFAULT_STREAM_FORMAT,
    ) -> Iterator[Iterator[str]]:
        """Stream company data line by line (`csv` / `jsonl` only)."""
        ensure_streamable(format)
        method, path, json_body = companies_request(payload, format)
        with self.stream(method=method, path=path, json=json_body) as lines:
            yield lines

    def organizations(
        self,
        payload: dict,
        format: ResponseFormat = DEFAULT_RESPONSE_FORMAT,
    ) -> dict | str:
        return parse_response(
            self.request(
                method=http.HTTPMethod.POST,
                path=f"/v3/organizations/?format={format}",
                json=payload,
            ),
            format,
        )

    @contextmanager
    def stream_organizations(
        self,
        payload: dict,
        format: ResponseFormat = DEFAULT_STREAM_FORMAT,
    ) -> Iterator[Iterator[str]]:
        """Stream organization data line by line (`csv` / `jsonl` only)."""
        ensure_streamable(format)
        with self.stream(
            method=http.HTTPMethod.POST,
            path=f"/v3/organizations/?format={format}",
            json=payload,
        ) as lines:
            yield lines

    def organizations_async(
        self,
        payload: dict,
        format: ResponseFormat = DEFAULT_RESPONSE_FORMAT,
    ) -> AsyncResult:
        return self.request_api_async(
            method=http.HTTPMethod.POST,
            path="/v3/organizations/async/",
            payload=payload,
            format=format,
        )

    def signals_news(
        self,
        payload: dict,
        format: ResponseFormat = DEFAULT_RESPONSE_FORMAT,
    ) -> list | str:
        return parse_response(
            self.request(
                method=http.HTTPMethod.POST,
                path=f"/v3/signals/news/?format={format}",
                json=payload,
            ),
            format,
        )

    @contextmanager
    def stream_signals_news(
        self,
        payload: dict,
        format: ResponseFormat = DEFAULT_STREAM_FORMAT,
    ) -> Iterator[Iterator[str]]:
        """Stream news signals line by line (`jsonl` only — the API renders no csv)."""
        ensure_streamable(format)
        with self.stream(
            method=http.HTTPMethod.POST,
            path=f"/v3/signals/news/?format={format}",
            json=payload,
        ) as lines:
            yield lines

    def signals_data_changes(
        self,
        payload: dict,
        format: ResponseFormat = DEFAULT_RESPONSE_FORMAT,
    ) -> list | str:
        return parse_response(
            self.request(
                method=http.HTTPMethod.POST,
                path=f"/v3/signals/data-changes/?format={format}",
                json=payload,
            ),
            format,
        )

    @contextmanager
    def stream_signals_data_changes(
        self,
        payload: dict,
        format: ResponseFormat = DEFAULT_STREAM_FORMAT,
    ) -> Iterator[Iterator[str]]:
        """Stream data-change signals line by line (`jsonl` only)."""
        ensure_streamable(format)
        with self.stream(
            method=http.HTTPMethod.POST,
            path=f"/v3/signals/data-changes/?format={format}",
            json=payload,
        ) as lines:
            yield lines

    def enrichment_agent(
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
            self.request(
                method=http.HTTPMethod.POST,
                path=f"/v3/enrichment_agent/?format={format}",
                json=payload,
            ),
            format,
        )

    def organization_fields(
        self,
        api_versions: str = "v3",
    ) -> list:
        """Return organization field metadata (filterable vs output availability)."""
        return parse_response(
            self.request(
                method=http.HTTPMethod.GET,
                path=f"/v3/organizations_fields/?api_versions={api_versions}",
            ),
            DEFAULT_RESPONSE_FORMAT,
        )

    def organization_lists(
        self,
        format: ResponseFormat = DEFAULT_RESPONSE_FORMAT,
    ) -> list | str:
        """List all accessible organization lists (static and dynamic)."""
        return parse_response(
            self.request(
                method=http.HTTPMethod.GET,
                path=f"/v3/lists/organizations/?format={format}",
            ),
            format,
        )

    def organization_list_get(
        self,
        list_id: str,
        format: ResponseFormat = DEFAULT_RESPONSE_FORMAT,
    ) -> dict | str:
        """Retrieve one organization list summary by id."""
        return parse_response(
            self.request(
                method=http.HTTPMethod.GET,
                path=f"/v3/lists/organizations/{list_id}/?format={format}",
            ),
            format,
        )

    def organization_list_delete(self, list_id: str) -> None:
        """Delete an organization list (static or dynamic) by id."""
        self.request(
            method=http.HTTPMethod.DELETE,
            path=f"/v3/lists/organizations/{list_id}/",
        ).raise_for_status()

    def organization_lists_static(
        self,
        format: ResponseFormat = DEFAULT_RESPONSE_FORMAT,
    ) -> list | str:
        """List static organization lists."""
        return parse_response(
            self.request(
                method=http.HTTPMethod.GET,
                path=f"/v3/lists/organizations/static/?format={format}",
            ),
            format,
        )

    def organization_list_static_get(
        self,
        list_id: str,
        format: ResponseFormat = DEFAULT_RESPONSE_FORMAT,
    ) -> dict | str:
        """Retrieve one static organization list."""
        return parse_response(
            self.request(
                method=http.HTTPMethod.GET,
                path=f"/v3/lists/organizations/static/{list_id}/?format={format}",
            ),
            format,
        )

    def organization_list_static_create(
        self,
        payload: dict,
        format: ResponseFormat = DEFAULT_RESPONSE_FORMAT,
    ) -> dict | str:
        """Create a static organization list."""
        return parse_response(
            self.request(
                method=http.HTTPMethod.POST,
                path=f"/v3/lists/organizations/static/?format={format}",
                json=payload,
            ),
            format,
        )

    def organization_list_static_update(
        self,
        list_id: str,
        payload: dict,
        format: ResponseFormat = DEFAULT_RESPONSE_FORMAT,
    ) -> dict | str:
        """Partially update a static organization list."""
        return parse_response(
            self.request(
                method=http.HTTPMethod.PATCH,
                path=f"/v3/lists/organizations/static/{list_id}/?format={format}",
                json=payload,
            ),
            format,
        )

    def organization_list_static_delete(self, list_id: str) -> None:
        """Delete a static organization list."""
        self.request(
            method=http.HTTPMethod.DELETE,
            path=f"/v3/lists/organizations/static/{list_id}/",
        ).raise_for_status()

    def organization_list_static_add(self, list_id: str, business_ids: list[str]) -> None:
        """Add business IDs to a static organization list."""
        self.request(
            method=http.HTTPMethod.PATCH,
            path=f"/v3/lists/organizations/static/{list_id}/add/",
            json=business_ids,
        ).raise_for_status()

    def organization_list_static_remove(self, list_id: str, business_ids: list[str]) -> None:
        """Remove business IDs from a static organization list."""
        self.request(
            method=http.HTTPMethod.PATCH,
            path=f"/v3/lists/organizations/static/{list_id}/remove/",
            json=business_ids,
        ).raise_for_status()

    def organization_lists_dynamic(
        self,
        format: ResponseFormat = DEFAULT_RESPONSE_FORMAT,
    ) -> list | str:
        """List dynamic organization lists."""
        return parse_response(
            self.request(
                method=http.HTTPMethod.GET,
                path=f"/v3/lists/organizations/dynamic/?format={format}",
            ),
            format,
        )

    def organization_list_dynamic_get(
        self,
        list_id: str,
        format: ResponseFormat = DEFAULT_RESPONSE_FORMAT,
    ) -> dict | str:
        """Retrieve one dynamic organization list."""
        return parse_response(
            self.request(
                method=http.HTTPMethod.GET,
                path=f"/v3/lists/organizations/dynamic/{list_id}/?format={format}",
            ),
            format,
        )

    def organization_list_dynamic_create(
        self,
        payload: dict,
        format: ResponseFormat = DEFAULT_RESPONSE_FORMAT,
    ) -> dict | str:
        """Create a dynamic organization list."""
        return parse_response(
            self.request(
                method=http.HTTPMethod.POST,
                path=f"/v3/lists/organizations/dynamic/?format={format}",
                json=payload,
            ),
            format,
        )

    def organization_list_dynamic_update(
        self,
        list_id: str,
        payload: dict,
        format: ResponseFormat = DEFAULT_RESPONSE_FORMAT,
    ) -> dict | str:
        """Partially update a dynamic organization list."""
        return parse_response(
            self.request(
                method=http.HTTPMethod.PATCH,
                path=f"/v3/lists/organizations/dynamic/{list_id}/?format={format}",
                json=payload,
            ),
            format,
        )

    def organization_list_dynamic_delete(self, list_id: str) -> None:
        """Delete a dynamic organization list."""
        self.request(
            method=http.HTTPMethod.DELETE,
            path=f"/v3/lists/organizations/dynamic/{list_id}/",
        ).raise_for_status()

    def close(self) -> None:
        self._http.close()

    def get_headers(self) -> dict:
        raise NotImplementedError


class VainuAPIKeySyncClient(VainuAPIBaseClient):
    """Synchronous client using a static API key."""

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

    def get_headers(self) -> dict:
        return {"API-Key": self.api_key}


class VainuJWTSyncClient(VainuAPIBaseClient):
    """Synchronous client with automatic JWT refresh token exchange."""

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

    def get_headers(self) -> dict:
        self._ensure_access_token()
        return {"Authorization": f"Bearer {self._access_token}"}

    def _ensure_access_token(self) -> None:
        """Fetch a new access token if missing or expiring within 60 seconds."""
        if self._access_token and time.time() < self._token_expires_at - 60:
            return
        refresh_url = urljoin(
            f"{self._base_url.rstrip('/')}/",
            JWT_REFRESH_ENDPOINT_PATH.lstrip("/"),
        )
        response = self._http.post(
            refresh_url,
            json={"refresh": self.jwt_token},
            timeout=self._timeout,
        )
        _raise_for_status_with_body(response)
        response.raise_for_status()
        data = response.json()
        self._access_token = data["access"]
        self._token_expires_at = time.time() + int(data.get("expires_in", 3600))


class VainuOAuthSyncClient(VainuAPIBaseClient):
    """Synchronous client with automatic OAuth 2.0 client credentials token management."""

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

    def get_headers(self) -> dict:
        self._ensure_token()
        return {"Authorization": f"Bearer {self._access_token}"}

    def _ensure_token(self) -> None:
        """Reuse a live token — in memory, then from the store — else mint one."""
        if self._access_token and time.time() < self._token_expires_at - 60:
            return
        cached = self._cache.load()
        if cached is not None:
            self._access_token, self._token_expires_at = cached
            self._token_from_cache = True
            return
        response = self._http.post(
            f"{self._base_url}/oauth/token/",
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "scope": self.scope,
            },
            timeout=self._timeout,
        )
        response.raise_for_status()
        data = response.json()
        self._access_token = data["access_token"]
        self._token_expires_at = time.time() + data["expires_in"]
        self._token_from_cache = False
        self._cache.save(self._access_token, self._token_expires_at)

    def _invalidate_credentials(self) -> bool:
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
        self._cache.clear()
        return True
