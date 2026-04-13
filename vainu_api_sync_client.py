"""
Vainu API Client (synchronous)

Example usage:

python3 scripts/api_scripts/sync_api_client.py \
  --query "?country=FI&business_id=FI01320292" \
  --output "companies_async_result.json"
"""

import argparse
import enum
import http
import logging
import os
import time

from dataclasses import dataclass

import requests


BASE_URL = os.getenv("VAINU_BASE_URL", "https://api.vainu.io/api")

# Set these environment variables before running the script, or replace with your credentials directly.
VAINU_CLIENT_ID = os.getenv("VAINU_CLIENT_ID", "your-client-id")
VAINU_CLIENT_SECRET = os.getenv("VAINU_CLIENT_SECRET", "your-client-secret")
VAINU_API_KEY = os.getenv("VAINU_API_KEY", "your-api-key")
VAINU_JWT_REFRESH_TOKEN = os.getenv("VAINU_JWT_REFRESH_TOKEN", "your-jwt-refresh-token")

logger = logging.getLogger(__name__)


def raise_for_status_with_body(response):
    """
    Checks the response for errors.
    If an error exists, prints the body and raises the exception.
    """
    try:
        response.raise_for_status()
    except requests.exceptions.HTTPError as err:
        logger.error(f"--- Error Response Body ---")
        logger.error(response.text)
        logger.error(f"---------------------------")
        raise err
    except Exception as err:
        logger.error(f"--- Unexpected Error ---")
        logger.error(str(err))
        logger.error(f"------------------------")
        raise err
    return response


class AsyncJobState(str, enum.Enum):
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
        logger.info("Downloading file: %s", self.download_url)
        with requests.get(self.download_url, stream=True, timeout=120) as response:
            response.raise_for_status()
            with open(output_path, "wb") as output_file:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        output_file.write(chunk)
        logger.info("Downloaded file: %s", output_path)


class VainuAPIBaseClient:
    ASYNC_POLL_INTERVAL = 3  # seconds
    ASYNC_MAX_WAIT_SECONDS = 14400  # 4 hours

    def __init__(self, timeout: int = 120):
        self._http = requests.Session()
        self._async_max_wait_seconds = self.ASYNC_MAX_WAIT_SECONDS
        self._timeout = timeout

    def request(self, method: http.HTTPMethod, path: str, **kwargs) -> requests.Response:
        logger.debug("Calling Vainu API: %s %s with request keys %s", method, path, sorted(kwargs.keys()))
        url = path if path.startswith("http://") or path.startswith("https://") else f"{BASE_URL}{path}"
        response = self._http.request(
            method=str(method),
            url=url,
            headers=self.get_headers(),
            timeout=self._timeout,
            **kwargs,
        )
        raise_for_status_with_body(response)
        return response

    def request_api_async(
        self,
        method: http.HTTPMethod,
        path: str,
        payload: dict | str,
        format: str = "json",
    ) -> AsyncResult:
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
                    f"Async job polling exceeded {self._async_max_wait_seconds} seconds for link {link_to_poll}"
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
                raise RuntimeError(f"Async job failed: {poll_data} {status}")
            logger.debug(
                "Async job status: %s. Polling again in %s seconds, processed %s...",
                status,
                self.ASYNC_POLL_INTERVAL,
                progress,
            )
            time.sleep(self.ASYNC_POLL_INTERVAL)

    def companies_async(self, payload: dict | str, format: str = "json") -> AsyncResult:
        path = "/v2/companies/async/"
        if isinstance(payload, dict):
            return self.request_api_async(
                path=path,
                method=http.HTTPMethod.POST,
                payload=payload,
                format=format,
            )
        if isinstance(payload, str):
            return self.request_api_async(
                method=http.HTTPMethod.GET,
                path=f"{path}{payload}",
                format=format,
                payload={},
            )
        raise ValueError("payload needs to be str or dict")

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
        raise ValueError("payload needs to be str or dict")

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


class VainuAPIKeyClient(VainuAPIBaseClient):
    """Synchronous Vainu API client using a static API key."""

    def __init__(self, api_key: str | None = None):
        super().__init__()
        self.api_key = api_key or VAINU_API_KEY

    def get_headers(self) -> dict:
        return {"API-Key": self.api_key}


class VainuJWTAPIClient(VainuAPIBaseClient):
    """Synchronous Vainu API client using JWT tokens."""

    def __init__(self, refresh_token: str | None = None):
        super().__init__()
        self.jwt_token = refresh_token or VAINU_JWT_REFRESH_TOKEN
        self._access_token: str | None = None

    def get_headers(self) -> dict:
        self._ensure_access_token()
        return {"Authorization": f"Bearer {self._access_token}"}

    def _ensure_access_token(self) -> None:
        raise NotImplementedError("JWT token refresh logic needs to be implemented based on your auth setup.")


class VainuOAuthAPIClient(VainuAPIBaseClient):
    """Synchronous Vainu API client with automatic OAuth token management."""

    def __init__(
            self,
            *,
            client_id: str | None = None,
            client_secret: str | None = None,
            scope: str = "vainu:api",
    ):
        super().__init__(timeout=30)
        self.client_id = client_id or VAINU_CLIENT_ID
        self.client_secret = client_secret or VAINU_CLIENT_SECRET
        self.scope = scope
        self._access_token: str | None = None
        self._token_expires_at: float = 0

    def get_headers(self) -> dict:
        self._ensure_token()
        return {"Authorization": f"Bearer {self._access_token}"}

    def _ensure_token(self) -> None:
        # Refresh 60 seconds before expiry to avoid race conditions.
        if self._access_token and time.time() < self._token_expires_at - 60:
            return

        response = self._http.post(
            f"{BASE_URL}/oauth/token/",
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


def test_api_key_client(query: str) -> None:
    vainu_api_client = VainuAPIKeyClient()
    try:
        companies_response = vainu_api_client.companies(payload=query)
        print(f"Sync Result\n{companies_response}")

        async_result = vainu_api_client.companies_async(payload=query)
        result = async_result.json()
        print("Async Result")
        print(result)
        async_result.download_to_file("companies_async_result.json")
    finally:
        vainu_api_client.close()


def companies_api_download_file(*, query: str, file_output_path: str, format: str = "json") -> None:
    vainu_api_client = VainuAPIKeyClient()
    try:
        async_result = vainu_api_client.companies_async(payload=query, format=format)
        async_result.download_to_file(file_output_path)
    finally:
        vainu_api_client.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    parser = argparse.ArgumentParser(description="Download companies from Vainu API asynchronously.")
    parser.add_argument(
        "--query",
        type=str,
        default="?country=FI&business_id=FI01320292",
        help="Query string for the API (default: ?country=FI&business_id=FI01320292)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="companies_async_result.json",
        help="Output file path (default: companies_async_result.json)",
    )
    parser.add_argument(
        "--format",
        type=str,
        choices=["json", "csv", "jsonl"],
        default="json",
        help="Format of the output file (default: json)",
    )

    args = parser.parse_args()
    companies_api_download_file(query=args.query, file_output_path=args.output, format=args.format)
