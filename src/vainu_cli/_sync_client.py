"""Synchronous Vainu API client (requests-based)."""

import enum
import http
import logging
import time
from dataclasses import dataclass

import requests

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.vainu.io/api"


class AsyncJobState(enum.StrEnum):
    ACCEPTED = "accepted"
    COMPLETED = "completed"
    FAILURE = "failure"
    PARTIAL_FAILURE_COMPLETE = "partial_failure_complete"
    PARTIAL_FAILURE_INCOMPLETE = "partial_failure_incomplete"
    PROCESS = "process"
    STOPPED = "stopped"


@dataclass
class AsyncResult:
    download_url: str
    duration: int

    def json(self) -> dict:
        logger.info("Downloading and parsing JSON from: %s", self.download_url)
        response = requests.get(self.download_url, timeout=120)
        response.raise_for_status()
        return response.json()

    def download_to_file(self, output_path: str) -> None:
        logger.info("Downloading file to %s", self.download_url)
        with requests.get(self.download_url, stream=True, timeout=120) as response:
            response.raise_for_status()
            with open(output_path, "wb") as output_file:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        output_file.write(chunk)
        logger.info("Downloaded file: %s", output_path)


def _raise_for_status_with_body(response: requests.Response) -> requests.Response:
    try:
        response.raise_for_status()
    except requests.exceptions.HTTPError as err:
        logger.error("HTTP error: %s — body: %s", err, response.text)
        raise
    return response


class VainuAPIBaseClient:
    ASYNC_POLL_INTERVAL = 3  # seconds
    ASYNC_MAX_WAIT_SECONDS = 14400  # 4 hours

    def __init__(self, base_url: str = DEFAULT_BASE_URL, timeout: int = 120) -> None:
        self._base_url = base_url
        self._timeout = timeout
        self._http = requests.Session()
        self._async_max_wait_seconds = self.ASYNC_MAX_WAIT_SECONDS

    def request(self, method: http.HTTPMethod, path: str, **kwargs) -> requests.Response:
        logger.debug("Vainu API %s %s", method, path)
        url = path if path.startswith(("http://", "https://")) else f"{self._base_url}{path}"
        response = self._http.request(
            method=str(method),
            url=url,
            headers=self.get_headers(),
            timeout=self._timeout,
            **kwargs,
        )
        _raise_for_status_with_body(response)
        return response

    def request_api_async(
        self,
        method: http.HTTPMethod,
        path: str,
        payload: dict | str,
        format: str = "json",
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
        while True:
            if time.monotonic() - started_at > self._async_max_wait_seconds:
                raise TimeoutError(
                    f"Async job polling exceeded {self._async_max_wait_seconds}s "
                    f"for link {link_to_poll}"
                )
            poll_response = self.request(method=http.HTTPMethod.GET, path=link_to_poll)
            poll_data = poll_response.json()
            status = AsyncJobState(poll_data.get("state"))
            progress = poll_data.get("progress", 0)
            if status == AsyncJobState.COMPLETED:
                return AsyncResult(
                    download_url=poll_data.get("download_link"),
                    duration=poll_data.get("duration"),
                )
            if status not in {AsyncJobState.ACCEPTED, AsyncJobState.PROCESS}:
                raise RuntimeError(f"Async job failed with state {status!r}: {poll_data}")
            logger.debug(
                "Async job %s — polling again in %ss (progress: %s)",
                status,
                self.ASYNC_POLL_INTERVAL,
                progress,
            )
            time.sleep(self.ASYNC_POLL_INTERVAL)

    def companies_async(self, payload: dict | str, format: str = "json") -> AsyncResult:
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

    def companies(self, payload: dict | str, format: str = "json") -> dict:
        path = "/v2/companies/"
        if isinstance(payload, dict):
            return self.request(
                method=http.HTTPMethod.POST,
                path=f"{path}?format={format}",
                json=payload,
            ).json()
        if isinstance(payload, str):
            return self.request(
                method=http.HTTPMethod.GET,
                path=f"{path}{payload}&format={format}",
            ).json()
        raise ValueError("payload must be str or dict")

    def organizations(self, payload: dict) -> dict:
        return self.request(
            method=http.HTTPMethod.POST,
            path="/v3/organizations/",
            json=payload,
        ).json()

    def organizations_async(self, payload: dict) -> AsyncResult:
        return self.request_api_async(
            method=http.HTTPMethod.POST,
            path="/v3/organizations/async/",
            payload=payload,
        )

    def close(self) -> None:
        self._http.close()

    def get_headers(self) -> dict:
        raise NotImplementedError


class VainuAPIKeySyncClient(VainuAPIBaseClient):
    """Synchronous client using a static API key."""

    def __init__(self, api_key: str, base_url: str = DEFAULT_BASE_URL) -> None:
        super().__init__(base_url=base_url, timeout=120)
        if not api_key:
            raise ValueError("api_key must not be empty. Set VAINU_API_KEY or pass api_key=...")
        self.api_key = api_key

    def get_headers(self) -> dict:
        return {"API-Key": self.api_key}


class VainuJWTSyncClient(VainuAPIBaseClient):
    """Synchronous client using JWT refresh tokens (not yet implemented)."""

    def __init__(self, refresh_token: str, base_url: str = DEFAULT_BASE_URL) -> None:
        super().__init__(base_url=base_url, timeout=120)
        if not refresh_token:
            raise ValueError("refresh_token must not be empty.")
        self.jwt_token = refresh_token
        self._access_token: str | None = None

    def get_headers(self) -> dict:
        self._ensure_access_token()
        return {"Authorization": f"Bearer {self._access_token}"}

    def _ensure_access_token(self) -> None:
        raise NotImplementedError(
            "JWT token refresh logic needs to be implemented based on your auth setup."
        )


class VainuOAuthSyncClient(VainuAPIBaseClient):
    """Synchronous client with automatic OAuth 2.0 client credentials token management."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        scope: str = "vainu:api",
        base_url: str = DEFAULT_BASE_URL,
    ) -> None:
        super().__init__(base_url=base_url, timeout=30)
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

    def get_headers(self) -> dict:
        self._ensure_token()
        return {"Authorization": f"Bearer {self._access_token}"}

    def _ensure_token(self) -> None:
        """Fetch a new token if missing or expiring within 60 seconds."""
        if self._access_token and time.time() < self._token_expires_at - 60:
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
