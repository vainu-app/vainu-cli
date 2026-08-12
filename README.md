# vainu-cli

[![PyPI version](https://img.shields.io/pypi/v/vainu-cli.svg)](https://pypi.org/project/vainu-cli/)
[![Python versions](https://img.shields.io/pypi/pyversions/vainu-cli.svg)](https://pypi.org/project/vainu-cli/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

CLI and Python client library for the [Vainu](https://vainu.com) company data API.
Query Nordic company data, export large datasets, and integrate Vainu into your workflows.

---

## Installation

```bash
pip install vainu-cli
```

Or with [uv](https://docs.astral.sh/uv/):

```bash
uv add vainu-cli
```

Or directly from GitHub:

```bash
pip install git+https://github.com/vainu-app/vainu-cli.git
```

```bash
uv add git+https://github.com/vainu-app/vainu-cli.git
```

Requires Python 3.11+.

---

## Quick start

### CLI

Set your API key:

```bash
export VAINU_API_KEY=your-api-key
```

Search for a company:

```bash
vainu companies --query "?country=FI&business_id=FI01320292"
```

Export a large dataset to a file:

```bash
vainu companies-async \
  --query "?country=FI" \
  --format jsonl \
  --output finnish_companies.jsonl
```

Search organizations with a JSON payload:

```bash
echo '{"query": {"country": "SE"}}' | \
  vainu organizations --payload -
```

### Python library

**Async client:**

```python
import asyncio
from vainu_cli import VainuAPIKeyClient

async def main():
    client = VainuAPIKeyClient(api_key="your-api-key")
    try:
        result = await client.companies(payload="?country=FI&business_id=FI01320292")
        print(result)

        # Async export job — polls until complete
        async_result = await client.companies_async(
            payload="?country=FI", format="jsonl"
        )
        await async_result.download_to_file("companies.jsonl")
    finally:
        await client.close()

asyncio.run(main())
```

**Sync client:**

```python
from vainu_cli import VainuAPIKeySyncClient

client = VainuAPIKeySyncClient(api_key="your-api-key")
try:
    result = client.companies(payload="?country=FI&business_id=FI01320292")
    print(result)
finally:
    client.close()
```

---

## Authentication

### API key (default)

```bash
export VAINU_API_KEY=your-api-key
vainu companies --query "?country=FI"

# or pass inline
vainu --api-key your-api-key companies --query "?country=FI"
```

### OAuth 2.0 client credentials

```bash
export VAINU_CLIENT_ID=your-client-id
export VAINU_CLIENT_SECRET=your-client-secret
vainu --auth-method oauth companies --payload payload.json
```

Tokens are fetched and refreshed transparently, and the access token is cached between
invocations so repeated commands skip the token round-trip. The cache lives in the OS
keyring (Keychain / Secret Service / Credential Locker), falling back to a 0600 file under
the user config dir when no keyring backend is available. Entries are keyed by base URL,
client ID and scope, so several environments can be used side by side.

```bash
VAINU_TOKEN_CACHE=0 vainu --auth-method oauth companies ...  # mint a fresh token
VAINU_AUTH_STORE=file vainu --auth-method oauth companies ...  # skip the keyring
vainu auth logout                                            # drop cached tokens
```

A token that the API rejects with 401 is discarded and the request retried once, so a
revoked token costs one extra call rather than an hour of failures.

---

## CLI reference

```
vainu [OPTIONS] COMMAND [ARGS]...

Options:
  --auth-method [apikey|oauth|jwt]  Authentication method (default: apikey)
  --api-key TEXT                    API key (or VAINU_API_KEY)
  --client-id TEXT                  OAuth client ID (or VAINU_CLIENT_ID)
  --client-secret TEXT              OAuth client secret (or VAINU_CLIENT_SECRET)
  --base-url TEXT                   Override API base URL
  --async-mode / --no-async-mode    Use async client for search commands
  -v, --verbose                     Enable DEBUG logging
  --version                         Show version and exit

Commands:
  companies            Fetch company data
  companies-async      Export company data via async job
  organizations        Fetch organization data
  organizations-async  Export organization data via async job
```

### `vainu companies`

```
--query TEXT         Query string, e.g. "?country=FI"
--payload FILE/-     JSON payload file or "-" for stdin
--payload-path FILE/-
--format             json | csv | jsonl  (default: json)
--output FILE        Write to file instead of stdout
```

### `vainu companies-async`

Submits an async export job, polls until complete, and downloads the result.

```
--query TEXT         Query string
--payload FILE/-     JSON payload file or "-" for stdin
--payload-path FILE/-
--format             json | csv | jsonl  (default: json)
--output FILE        Output file (required)
--poll-interval INT  Polling interval in seconds (default: 3)
--timeout INT        Max wait seconds (default: 14400)
```

### `vainu organizations` / `vainu organizations-async`

Same options as the company commands (organizations always use POST with a JSON payload).

`organizations` and `organizations-async` also accept `--payload-path` as an alias for
`--payload`.

---

## Example payloads

The repository ships ready-made Organizations API request bodies under
[`example_payloads/organizations_api/`](https://github.com/vainu-app/vainu-cli/tree/main/example_payloads/organizations_api),
transcribed from the [v3 recipes](https://developers.vainu.com/v3/recipes). Each file is a
complete POST body — `query`, `fields`, `database`, `limit` and friends at the top level — so it
can be handed straight to `--payload`. The paths below assume you have cloned the repo.

| File | What it shows | Notes |
|---|---|---|
| [`01-amount-of-companies-matching-the-query.json`](https://github.com/vainu-app/vainu-cli/blob/main/example_payloads/organizations_api/01-amount-of-companies-matching-the-query.json) | Counting NO companies with revenue ≥ 1M | Targets `/v3/organizations/count/`, which the CLI does not reach |
| [`02-filter-contacts-return-only-ceos-of-companies.json`](https://github.com/vainu-app/vainu-cli/blob/main/example_payloads/organizations_api/02-filter-contacts-return-only-ceos-of-companies.json) | Subdocument aggregation returning only CEO / Privacy Officer contacts | |
| [`03-geospatial-business-unit-search-returning-only-matching-business_units.json`](https://github.com/vainu-app/vainu-cli/blob/main/example_payloads/organizations_api/03-geospatial-business-unit-search-returning-only-matching-business_units.json) | Geo sphere search with `unwind_subdocument` — only matching business units | |
| [`04-get-all-companies-in-vainu-list-async-sync.json`](https://github.com/vainu-app/vainu-cli/blob/main/example_payloads/organizations_api/04-get-all-companies-in-vainu-list-async-sync.json) | Every company in a saved Vainu list | `list` is a placeholder ID — swap in your own |
| [`05-get-count-of-vehicles-with-make-and-registration.json`](https://github.com/vainu-app/vainu-cli/blob/main/example_payloads/organizations_api/05-get-count-of-vehicles-with-make-and-registration.json) | Per-company Skoda count via `?FILTER_SUBDOCUMENTS` + `?COUNT` | `limit` is 1000000 — lower it before running interactively |
| [`06-simple-fuzzy-search-api.json`](https://github.com/vainu-app/vainu-cli/blob/main/example_payloads/organizations_api/06-simple-fuzzy-search-api.json) | Fuzzy free-text search for "volvo" | Targets `/v3/organizations/search/`, which the CLI does not reach |
| [`07-search-companies-with-geo-sphere-with-coordinates.json`](https://github.com/vainu-app/vainu-cli/blob/main/example_payloads/organizations_api/07-search-companies-with-geo-sphere-with-coordinates.json) | `?GEO_WITHIN_SPHERE` returning whole companies | Radius is in radians (metres ÷ 6371000) |
| [`08-simple-filtering-example-using-v3organizations.json`](https://github.com/vainu-app/vainu-cli/blob/main/example_payloads/organizations_api/08-simple-filtering-example-using-v3organizations.json) | Minimal exact-match filter on `business_id` | Start here |
| [`09-simple-oauth-client-credentials-example.json`](https://github.com/vainu-app/vainu-cli/blob/main/example_payloads/organizations_api/09-simple-oauth-client-credentials-example.json) | The same filter, run under OAuth client credentials | |
| [`10-technology-search-shopify.json`](https://github.com/vainu-app/vainu-cli/blob/main/example_payloads/organizations_api/10-technology-search-shopify.json) | `?STARTSWITH` on `technology_data.name` | |
| [`11-track-modifications.json`](https://github.com/vainu-app/vainu-cli/blob/main/example_payloads/organizations_api/11-track-modifications.json) | `?RANGE` over `modifications.*` for incremental sync | Contains `<NOW_MINUS_10_SECONDS_ISO8601>` — substitute both timestamps before sending |

Set up credentials once (see [Authentication](#authentication)), then run the smallest example:

```bash
export VAINU_API_KEY=your-api-key
vainu organizations \
  --payload example_payloads/organizations_api/08-simple-filtering-example-using-v3organizations.json
```

Aggregations use the same command — only the payload changes:

```bash
vainu organizations \
  --payload example_payloads/organizations_api/02-filter-contacts-return-only-ceos-of-companies.json
```

Add the global `-v` before the command to see request timing, and `--language` after it to
localise the response:

```bash
vainu -v organizations \
  --language fi \
  --payload example_payloads/organizations_api/10-technology-search-shopify.json
```

`--async-mode` runs the same request through the httpx client instead of requests:

```bash
vainu --async-mode organizations \
  --payload example_payloads/organizations_api/07-search-companies-with-geo-sphere-with-coordinates.json
```

With `--output` the result is written to a file and the confirmation goes to stderr, so stdout
stays clean for piping:

```bash
vainu organizations \
  --payload example_payloads/organizations_api/03-geospatial-business-unit-search-returning-only-matching-business_units.json \
  --output uppsala_units.json
```

`--format csv` returns the raw CSV body untouched:

```bash
vainu organizations \
  --payload example_payloads/organizations_api/05-get-count-of-vehicles-with-make-and-registration.json \
  --format csv \
  --output skoda_counts.csv
```

Large result sets belong in an async export job, where `--output` is required:

```bash
vainu organizations-async \
  --payload example_payloads/organizations_api/04-get-all-companies-in-vainu-list-async-sync.json \
  --format jsonl \
  --poll-interval 5 \
  --output list_companies.jsonl
```

Any payload works under OAuth client credentials instead of an API key:

```bash
export VAINU_CLIENT_ID=your-client-id
export VAINU_CLIENT_SECRET=your-client-secret
vainu --auth-method oauth organizations \
  --payload example_payloads/organizations_api/09-simple-oauth-client-credentials-example.json
```

---

## Python API

### Async clients

| Class | Auth |
|---|---|
| `VainuAPIKeyClient(api_key, base_url?)` | Static API key |
| `VainuOAuthAPIClient(client_id, client_secret, scope?, base_url?)` | OAuth 2.0 |

**Methods** (all `async`):

| Method | Description |
|---|---|
| `companies(payload, format)` | Fetch company data (`dict` for `json`, raw `str` for `csv`/`jsonl`) |
| `companies_async(payload, format)` | Submit async job → `AsyncResult` |
| `organizations(payload, format)` | Fetch organization data (`dict` for `json`, raw `str` for `csv`/`jsonl`) |
| `organizations_async(payload, format)` | Submit async job → `AsyncResult` |
| `close()` | Close HTTP connection |

### Sync clients

| Class | Auth |
|---|---|
| `VainuAPIKeySyncClient(api_key, base_url?)` | Static API key |
| `VainuOAuthSyncClient(client_id, client_secret, scope?, base_url?)` | OAuth 2.0 |

Same methods as the async clients but blocking (no `await`).

### `AsyncResult`

```python
result.download_url          # URL of the exported file
result.duration              # Job duration in seconds
await result.json()          # Download and parse as dict (async)
await result.download_to_file(path)  # Download via curl (async)

result.json()                # Download and parse as dict (sync)
result.download_to_file(path)        # Download via streaming requests (sync)
```

Search methods return parsed JSON only when `format="json"`. For `format="csv"` and
`format="jsonl"`, they return the raw response text so the caller can write or stream it
without JSON re-encoding.

---

## Environment variables

| Variable | Description |
|---|---|
| `VAINU_API_KEY` | Static API key |
| `VAINU_CLIENT_ID` | OAuth client ID |
| `VAINU_CLIENT_SECRET` | OAuth client secret |
| `VAINU_JWT_REFRESH_TOKEN` | JWT refresh token |
| `VAINU_BASE_URL` | Override API base URL |

---

## Development

```bash
git clone https://gitlab.com/vainu/vainu-cli.git
cd vainu-cli
uv sync --extra dev

# Run tests
uv run pytest -v

# Lint
uv run ruff check src/ tests/
uv run ruff format src/ tests/

# Security checks
uv run bandit -c pyproject.toml -r src/
uv run pip-audit

# Build
uv build
```

---

## License

[MIT](LICENSE) © 2026 Vainu
