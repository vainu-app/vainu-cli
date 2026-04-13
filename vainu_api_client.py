"""
Vainu API Client

## Example with API Key:
set vainu API-KE to VAINU_API_KEY environment variable:

From shell:
```
python3 scripts/vainu_api_client.py --query "?country=FI&business_id=FI01320292" --output "my_companies.json"
```

With code:
```
vainu_api_client = VainuAPIKeyClient()
response = await vainu_api_client.companies(payload="?country=FI&business_id=FI01320292")
print(response)

vainu_api_client = VainuAPIKeyClient()
response = await vainu_api_client.companies_async(payload="?country=FI&business_id=FI01320292")
response.download_to_file("async_response.json")
```

"""

import argparse
import asyncio
import enum
import http
import httpx
import logging
import os
import time

from dataclasses import dataclass

BASE_URL = "https://api.vainu.io/api"
# Set these environment variables before running the script, or replace with your credentials directly

# Required for OAuth client
VAINU_CLIENT_ID = os.getenv("VAINU_CLIENT_ID", "your-client-id")
VAINU_CLIENT_SECRET = os.getenv("VAINU_CLIENT_SECRET", "your-client-secret")

# Required for API key client
VAINU_API_KEY = os.getenv("VAINU_API_KEY", "your-api-key")

# Required for JWT client
VAINU_JWT_REFRESH_TOKEN = os.getenv("VAINU_JWT_REFRESH_TOKEN", "your-jwt-refresh-token")


logger = logging.getLogger(__name__)


class AsyncJobState(str, enum.Enum):
    ACCEPTED = 'accepted'
    COMPLETED = 'completed'
    FAILURE = 'failure'
    PARTIAL_FAILURE_COMPLETE = 'partial_failure_complete'
    PARTIAL_FAILURE_INCOMPLETE = 'partial_failure_incomplete'
    PROCESS = 'process'
    STOPPED = 'stopped'


@dataclass
class AsyncResult:
    download_url: str
    duration: int

    async def json(self):
        async with httpx.AsyncClient() as client:
            logger.info("Downloading and parsing JSON from: %s", self.download_url)
            response = await client.get(self.download_url)
            response.raise_for_status()
            return response.json()

    async def download_to_file(self, output_path: str):
        """Most performant way to download large files with curl."""
        try:
            logger.info("Downloading file: %s", self.download_url)
            # -L: follow redirects
            # -s: silent (no progress bar in stderr)
            # -f: fail silently (returns an error code on HTTP errors, e.g., 404)
            # -o: output file
            # --compressed: handle compressed responses (e.g., gzip) which is common for large API responses
            process = await asyncio.create_subprocess_exec(
                "curl", "-L", "-s", "-o", output_path, "--compressed", self.download_url,
            )
            await process.wait()
            if process.returncode != 0:
                raise RuntimeError(f"Curl failed with return code {process.returncode}")
            logger.info("Downloaded file: %s", output_path)
        except FileNotFoundError:
            raise RuntimeError(
                "Curl is not installed. Please install curl to your env to download large files "
                "or use json() or download_url directly with the tool you prefer.",
            )
        except Exception as e:
            logger.error("Download failed: %s", e)


class VainuAPIBaseClient:
    ASYNC_POLL_INTERVAL = 3  # seconds

    async def request(self, method: http.HTTPMethod, path: str, **kwargs) -> httpx.Response:
        """Make an authenticated POST request."""
        logger.debug("Calling Vainu API: %s %s with data %s", method, path, kwargs)
        response = await self._http.request(
            method,
            path,
            headers=await self.get_headers(),
            **kwargs,
        )
        response.raise_for_status()
        return response

    async def request_api_async(
            self,
            method: http.HTTPMethod,
            path: str,
            payload: dict | str,
            format: str = "json",
    ) -> AsyncResult:
        """Example of an async polling method that could be used for long-running operations."""
        # Use simple authorization injection if available on self
        # httpx handles merging params into the URL, even if the URL already has query params
        get_async_job = await self.request(
            method=method,
            path=f"{path}&async_format={format}",
            json=payload if isinstance(payload, dict) else None,
        )
        get_async_job.raise_for_status()
        link_to_poll = get_async_job.json().get("link")
        while True:
            poll_response = await self.request(
                method=http.HTTPMethod.GET,
                path=link_to_poll,
            )
            poll_data = poll_response.json()
            status = AsyncJobState(poll_data.get("state"))
            progress = poll_data.get("progress", 0)
            if status == AsyncJobState.COMPLETED:
                return AsyncResult(
                    download_url=poll_data.get("download_link"),
                    duration=poll_data.get("duration"),
                )
            elif status not in {AsyncJobState.ACCEPTED, AsyncJobState.PROCESS}:
                raise RuntimeError(f"Async job failed: {poll_data} {status}")
            logger.debug("Async job status: %s. Polling again in %s seconds, processed %s...", status, self.ASYNC_POLL_INTERVAL, progress)
            await asyncio.sleep(self.ASYNC_POLL_INTERVAL)

    async def companies_async(
            self,
            payload: dict | str,
            format: str = "json",
    ) -> AsyncResult:
        path = "/v2/companies/async/"
        if isinstance(payload, dict):
            return await self.request_api_async(
                path=path,
                method=http.HTTPMethod.POST,
                payload=payload,
                format=format,
            )
        if isinstance(payload, str):
            return await self.request_api_async(
                method=http.HTTPMethod.GET,
                path=f"{path}{payload}",
                format=format,
                payload={},
            )
        raise ValueError("payload needs to be str or dict")

    async def companies(
            self,
            payload: dict | str,
            format: str = "json",
    ) -> dict:

        path = "/v2/companies/"
        if isinstance(payload, dict):
            return (await self.request(
                method=http.HTTPMethod.POST,
                path=f"{path}?format={format}",
                json=payload,
            )).json()
        if isinstance(payload, str):
            return (await self.request(
                method=http.HTTPMethod.GET,
                path=f"{path}{payload}&format={format}",
            )).json()
        raise ValueError("payload needs to be str or dict")

    async def organizations(self, payload: dict) -> dict:
        return await self.request(
            method=http.HTTPMethod.POST,
            path="/v3/organizations/",
            json=payload,
        )

    async def organizations_async(self, payload: dict) -> AsyncResult:
        return await self.request_api_async(
            method=http.HTTPMethod.POST,
            path="/v3/organizations/async/",
            json=payload,
        )

    async def close(self):
        await self._http.aclose()


class VainuAPIKeyClient(VainuAPIBaseClient):
    """Async Vainu API client using a static API key. No token management needed."""

    async def get_headers(self) -> dict:
        return {
            "API-Key": f"{self.api_key}",
        }

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or VAINU_API_KEY
        self._http = httpx.AsyncClient(base_url=BASE_URL, timeout=120)


class VainuJWTAPIClient(VainuAPIBaseClient):
    """Async Vainu API client using JWT tokens. Tokens are generated on demand and cached until expiry."""

    def __init__(self, refresh_token: str | None = None):
        self.jwt_token = refresh_token or VAINU_JWT_REFRESH_TOKEN
        self._http = httpx.AsyncClient(base_url=BASE_URL, timeout=120)
        self._access_token = None

    async def get_headers(self) -> dict:
        await self._ensure_access_token()
        return {
            "Authorization": f"Bearer {self._access_token}",
        }

    async def _ensure_access_token(self):
        raise NotImplementedError("JWT token refresh logic needs to be implemented based on your auth setup.")


class VainuOAuthAPIClient(VainuAPIBaseClient):
    """Async Vainu API client with automatic token management."""

    async def get_headers(self) -> dict:
        await self._ensure_token()
        return {
            "Authorization": f"Bearer {self._access_token}",
        }

    def __init__(self, client_id: str | None = None, client_secret: str | None = None, scope: str = "api"):
        self.client_id = client_id or VAINU_CLIENT_ID
        self.client_secret = client_secret or VAINU_CLIENT_SECRET
        self.scope = scope
        self._access_token: str | None = None
        self._token_expires_at: float = 0
        self._http = httpx.AsyncClient(base_url=BASE_URL, timeout=30)

    async def _ensure_token(self):
        """Get a new token if we don't have one or it's about to expire."""
        # Refresh 60 seconds before expiry to avoid race conditions
        if self._access_token and time.time() < self._token_expires_at - 60:
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


# Usage:
async def test_oauth_api_client():
    api = VainuOAuthAPIClient(scope="api")

    try:
        # Token is fetched automatically on first request
        organizations_response = await api.organizations(payload={"query": "vainu"})
        orgs = organizations_response.json()
        print(f"Found {len(orgs.get('result', []))} organizations")

        # Subsequent calls reuse the token until it expires
        organization_response = await api.organizations(payload="some-id")
        organization = organization_response.json()
        print(f"Organization: {organization.get('company_name')}")

        # When the token expires, the next call auto-renews it
        # No manual refresh needed — client_credentials is stateless
    finally:
        await api.close()


# Usage:
async def test_api_key_client(query: str):
    vainu_api_client = VainuAPIKeyClient()
    try:
        companies_response = await vainu_api_client.companies(payload=query)
        print(f"Sync Result\n{companies_response}")

        async_result = await vainu_api_client.companies_async(payload=query)
        result = await async_result.json()
        print("Async Result")
        print(result)
        await async_result.download_to_file("companies_async_result.json")
    finally:
        await vainu_api_client.close()


async def companies_api_download_file(*, query: str, file_output_path: str, format: str = "json"):
    vainu_api_client = VainuAPIKeyClient()
    try:
        async_result = await vainu_api_client.companies_async(payload=query, format=format)
        await async_result.download_to_file(file_output_path)
    finally:
        await vainu_api_client.close()


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

    asyncio.run(companies_api_download_file(query=args.query, file_output_path=args.output, format=args.format))