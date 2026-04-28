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

Tokens are fetched and cached automatically; expired tokens are refreshed transparently.

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
--format             json | csv | jsonl  (default: json)
--output FILE        Write to file instead of stdout
```

### `vainu companies-async`

Submits an async export job, polls until complete, and downloads the result.

```
--query TEXT         Query string
--payload FILE/-     JSON payload file or "-" for stdin
--format             json | csv | jsonl  (default: json)
--output FILE        Output file (required)
--poll-interval INT  Polling interval in seconds (default: 3)
--timeout INT        Max wait seconds (default: 14400)
```

### `vainu organizations` / `vainu organizations-async`

Same options as the company commands (organizations always use POST with a JSON payload).

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
| `companies(payload, format)` | Fetch company data |
| `companies_async(payload, format)` | Submit async job → `AsyncResult` |
| `organizations(payload)` | Fetch organization data |
| `organizations_async(payload)` | Submit async job → `AsyncResult` |
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
