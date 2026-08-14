# vainu-cli

[![PyPI version](https://img.shields.io/pypi/v/vainu-cli.svg)](https://pypi.org/project/vainu-cli/)
[![Python versions](https://img.shields.io/pypi/pyversions/vainu-cli.svg)](https://pypi.org/project/vainu-cli/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

CLI and Python client library for the [Vainu](https://vainu.com) company data API.
Query Nordic company data, export large datasets, and integrate Vainu into your workflows.

**New here?** Follow [SETUP.md](SETUP.md) for a step-by-step install guide (Mac, Windows, Linux) — no coding required.

---

## Installation

**Non-technical users:** see **[SETUP.md](SETUP.md)** — copy one command, sign in, run your first search.

**Using with AI agents?** See [AGENTS.md](AGENTS.md) and the
[`vainu-cli` skill](skills/vainu-cli/SKILL.md).

### CLI

Mac / Linux:

```bash
curl -LsSf https://raw.githubusercontent.com/vainu-app/vainu-cli/main/scripts/install.sh | sh
```

Windows (PowerShell):

```powershell
irm https://raw.githubusercontent.com/vainu-app/vainu-cli/main/scripts/install.ps1 | iex
```

From a git checkout: `./scripts/install.sh --local` (Mac/Linux) or `.\scripts\install.ps1 -Local` (Windows).

Then `vainu login` and `vainu doctor`. To get later releases: `vainu update` (or `vainu upgrade`).

The installer uses [uv](https://docs.astral.sh/uv/) and bootstraps Python 3.11+ if needed.

### Python library

```bash
uv add vainu-cli
```

```bash
pip install vainu-cli
```

From GitHub:

```bash
uv add git+https://github.com/vainu-app/vainu-cli.git
```

```bash
pip install git+https://github.com/vainu-app/vainu-cli.git
```

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
  companies             Fetch company data
  companies-async       Export company data via async job
  organizations         Fetch organization data
  organizations-async   Export organization data via async job
  fields                Inspect organization field metadata
  enrichment-agent      Run an enrichment agent prompt against one company
  signals-news          Fetch news signals
  signals-data-changes  Fetch company data-change signals
  lists                 Manage organization lists (static and dynamic)
  update                Upgrade vainu-cli to the latest PyPI release
  upgrade               Alias for update
```

### `vainu companies`

```
--query TEXT         Query string, e.g. "?country=FI"
--payload FILE/-     JSON payload file or "-" for stdin
--payload-path FILE/-
--format             json | csv | jsonl  (default: json)
--stream/--no-stream Stream lines as they arrive (default on for csv/jsonl)
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
`organizations` takes `--stream` / `--no-stream` too; the `-async` export commands do not, since
they already download to a file in chunks.

`organizations` and `organizations-async` also accept `--payload-path` as an alias for
`--payload`.

To see which field paths you can put in `query` vs the `fields` output list, use
[`vainu fields organizations`](#vainu-fields).

### `vainu update` / `vainu upgrade`

Upgrade the CLI to the latest PyPI release. Prefers `uv tool upgrade vainu-cli` (the
SETUP.md installer); falls back to `pip install --upgrade vainu-cli` if `uv` is not on
PATH.

```
vainu update
vainu upgrade
```

### `vainu fields`

Lists organization field metadata from
`GET /v3/organizations_fields/` — names, types, and whether each path is **filterable**
(usable in a VQL `query`) or **output** (usable in the `fields` list). The response is a
catalog, not company records.

```
vainu fields organizations

--view               table | summary | json  (default: table)
--output FILE        Write the view to a file instead of stdout
--api-version TEXT   API version query param (default: v3)
--category TEXT      Only this main_category (e.g. basic, contacts)
--database TEXT      Only fields available for FI | SE | NO | DK | NL
--search TEXT        Case-insensitive match on path, English name, or description
--filterable         Only fields usable in VQL filters (filter/search)
--returnable         Only fields usable in the fields output list (export/profile)
--permission-gated   Only fields that require an extra account entitlement
```

```bash
vainu fields organizations
vainu fields organizations --filterable --search revenue
vainu fields organizations --returnable --category contacts
vainu fields organizations --permission-gated --view summary
vainu fields organizations --view json --output fields.json
```

The default **table** view is grep-friendly: `path`, `name`, `filterable`, `output`,
`permission`, `type`. **summary** prints counts by category and lists permission gates.
**json** returns the (optionally filtered) API payload, including allowed operators.

Filterable means `application_availability` includes `filter` or `search`. Output means
`export` or `profile`. Some paths — contact email/phone, payment delays, vehicles, real
estate — are listed with a `requires_permission` slug and stay inaccessible until the
account is entitled to them.

### Streaming

`--format jsonl` and `--format csv` **stream by default**: each line is written the moment it
arrives, rather than the command sitting silent for a minute and then printing everything at
once. Nothing larger than a single line is held in memory, so piping a large export into another
tool costs almost nothing:

```bash
vainu organizations --payload payload.json --format jsonl | jq -r .business_id
vainu signals-news --payload payload.json --format jsonl --output signals.jsonl
```

- `--format json` never streams — a JSON body is a single document and is not valid until its
  last byte. Asking for `--stream --format json` is an error; leaving the flag off just buffers.
- `--no-stream` forces the old buffered behaviour for `jsonl`/`csv`.
- Works under both the default sync client and `--async-mode`.
- With `csv`, the first line out is the header row.
- Streaming drops blank lines and, with `--output`, always ends the file with a newline;
  `--no-stream` copies the body verbatim, trailing byte included. The rows themselves are the
  same either way.

### `vainu enrichment-agent`

Runs an [enrichment agent](https://developers.vainu.com/v3/recipes/run-enrichment-agent-to-single-business-id-and-get-structured-data)
prompt against one company and prints the structured fields the prompt defines.
The prompt itself is built in the Vainu UI — this command only needs its id.

```
--prompt TEXT            Enrichment agent prompt id from the Vainu UI (required)
--business-id TEXT       Company business id, e.g. FI23365096 (required)
--database TEXT          Country database: FI | SE | NO | DK (required)
--refresh/--no-refresh   Re-run instead of reusing the cached answer
--payload FILE/-         JSON payload file or "-" for stdin (alternative to the flags above)
--payload-path FILE/-
--format                 json | jsonl  (default: json)
--language TEXT          Accept-Language header
--request-timeout INT    HTTP timeout in seconds (default: 121)
--output FILE            Write to file instead of stdout
```

```bash
vainu enrichment-agent --prompt 12345 --database FI --business-id FI23365096
```

```json
{
  "response": {
    "main_business_activity": "Supercell Oy is a mobile game developer that creates …",
    "products_and_services": "Supercell's primary products are its mobile games …"
  }
}
```

The keys under `response` are whatever the prompt was configured to return, so they differ per
prompt. Notes worth knowing:

- Like the rest of the v3 API, this needs an OAuth or JWT token — **not** a static API key.
- Results are **cached per prompt + company**. A cached answer comes back quickly and spends no
  Vainu agent credits; `--refresh` forces a fresh run and does spend them.
- An uncached run researches the company on the spot and can take minutes. Raise
  `--request-timeout` for those; the run continues server-side either way, so a re-run after a
  timeout usually returns the now-cached answer.
- `--prompt` / `--database` / `--business-id` may come from `--payload` instead, and any flag you
  also pass overrides the file. That makes a saved payload reusable: keep the prompt id and
  database in the file and vary `--business-id` per run.
- There is no `--stream` — a single enrichment result is one document, not a row stream.

### `vainu signals-news` / `vainu signals-data-changes`

Fetch signals from the v3 Signals API (beta): `signals-news` returns externally sourced events
(news, press releases, contract notices), `signals-data-changes` returns events generated from
changes in company records.

```
--payload FILE/-     JSON payload file or "-" for stdin (required)
--payload-path FILE/-
--format             json | jsonl  (default: json)
--stream/--no-stream Stream lines as they arrive (default on for jsonl)
--language TEXT      Accept-Language header
--output FILE        Write to file instead of stdout
```

Both endpoints require an OAuth or JWT token — **the v3 API does not accept a static API key**.
Run `vainu login`, or set `VAINU_CLIENT_ID` / `VAINU_CLIENT_SECRET` and pass
`--auth-method oauth`.

Payload keys: `query` (required — see the
[filtering query language](https://developers.vainu.com/v3/docs/filtering-query-language)),
`limit` (default 20, capped at 100) and `offset` (capped at 100000). Notes worth knowing:

- The response is a **bare JSON array**, newest first. There is no `count` or `next`, and
  `order` is not supported — sending it returns `400 invalid order by value`.
- `csv` is not available; use `--format jsonl` for exports and page with `limit`/`offset`
  until a page returns fewer rows than `limit`.
- Signal types are integer `tags` ids, shared by both endpoints and by the Vainu UI. The full
  list is at
  [`TAGS_BY_TYPE.json`](https://filter.vainu.io/filtervalues/en/TAGS_BY_TYPE.json).
- Relative dates need **plural** units: `"30 days ago"` and `"1 years ago"` work, `"1 year ago"`
  returns 400.
- News signals can be filtered by `content`, `title`, `link`, `type` and `countries`;
  data-change signals only by `tags`, `vainu_date`, `business_ids` and `prospects`.
- `business_ids` takes country-prefixed ids (`FI25578642`) and supports `?IN` only.
- An empty array means "nothing matched" *or* "the query timed out", and an unknown field name
  is ignored rather than rejected — so always include a date bound and check field spelling
  when a result looks too large or too empty.

### `vainu lists`

Manage saved [organization lists](https://developers.vainu.com/v3/docs/list-management-apis.md)
— both **dynamic** lists (membership from a VQL query, shown as "My Lists" in the Vainu UI) and
**static** lists (a fixed set of business IDs, shown as "Custom Lists").

Requires OAuth, JWT, or `vainu login` — **not** a static API key alone.

```
vainu lists                              List all lists (static + dynamic)
vainu lists get ID                       Retrieve one list by id
vainu lists delete ID                    Delete any list by id

vainu lists static                       List static lists
vainu lists static get ID
vainu lists static create --payload FILE/-   Required: name, country (FI|SE|NO|DK|NL)
vainu lists static update ID --payload FILE/-
vainu lists static add ID --payload FILE/-     JSON array of business IDs
vainu lists static remove ID --payload FILE/-
vainu lists static delete ID

vainu lists dynamic                      List dynamic lists
vainu lists dynamic get ID
vainu lists dynamic create --payload FILE/-  Required: name, country, query (serialized VQL)
vainu lists dynamic update ID --payload FILE/-
vainu lists dynamic delete ID

--format             json | jsonl  (default: json)
--output FILE        Write JSON response to file (create/update/get/list commands)
```

List all accessible lists and grab an id for export:

```bash
vainu lists
vainu lists get 63d8de4eb7dfe9f5896fa539
```

Create a dynamic list (query is a **JSON string**, not a nested object):

```bash
cat > dynamic.json <<'EOF'
{
  "name": "FI companies with 500+ employees",
  "country": "FI",
  "query": "{\"?GTE\": {\"financial_data.employees.absolute_count\": 500}}"
}
EOF
vainu lists dynamic create --payload dynamic.json
```

Create a static list and add/remove companies (replace placeholder business IDs with your own):

```bash
vainu lists static create --payload - <<'EOF'
{"name": "Targets", "country": "FI", "business_ids": ["FI01234567"]}
EOF

echo '["FI07654321"]' | vainu lists static add LIST_ID --payload -
echo '["FI01234567"]' | vainu lists static remove LIST_ID --payload -
```

Rename or replace membership via update:

```bash
echo '{"name": "Renamed list"}' | vainu lists static update LIST_ID --payload -
echo '{"business_ids": []}' | vainu lists static update LIST_ID --payload -   # clear all members
```

Export every company in a saved list (swap in your list id from `vainu lists`):

```bash
vainu organizations-async \
  --payload example_payloads/organizations_api/04-get-all-companies-in-vainu-list-async-sync.json \
  --format jsonl \
  --output list_companies.jsonl
```

Notes:

- Static lists support atomic **add** and **remove** (`PATCH .../add/` and `.../remove/`); dynamic
  lists do not — edit the `query` with `vainu lists dynamic update` instead.
- `country` is immutable after creation.
- Each `business_id` must match the list country prefix (`FI…`, `SE…`, etc.).
- Add/remove payloads must be a JSON **array** of ids, e.g. `["FI01234567"]`, not an object.

---

## Example payloads

The repository ships ready-made Organizations API request bodies under
[`example_payloads/organizations_api/`](https://github.com/vainu-app/vainu-cli/tree/main/example_payloads/organizations_api),
transcribed from the [v3 recipes](https://developers.vainu.com/v3/recipes). Each file is a
complete POST body — `query`, `fields`, `database`, `limit` and friends at the top level — so it
can be handed straight to `--payload`. The paths below assume you have cloned the repo.

Each file also carries a `_meta` block naming the recipe it came from. It is sent along with the
rest of the body and the API ignores it; drop it if you prefer a minimal request.

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

### Signals API payloads

Signals request bodies live under
[`example_payloads/signals_api/`](https://github.com/vainu-app/vainu-cli/tree/main/example_payloads/signals_api).
Each file is a complete POST body — `query`, `limit`, `offset` at the top level.

| File | What it shows | Notes |
|---|---|---|
| [`01-news-signals-for-one-company.json`](https://github.com/vainu-app/vainu-cli/blob/main/example_payloads/signals_api/01-news-signals-for-one-company.json) | Every news signal for one company over the last year | Start here. Relative dates need plural units |
| [`02-news-signals-by-tags.json`](https://github.com/vainu-app/vainu-cli/blob/main/example_payloads/signals_api/02-news-signals-by-tags.json) | Funding + M&A by signal type id | Values inside one `?IN` are OR-ed |
| [`03-news-signals-excluding-tags.json`](https://github.com/vainu-app/vainu-cli/blob/main/example_payloads/signals_api/03-news-signals-excluding-tags.json) | Excluding a noisy type, keeping only tagged signals | `?NOT` alone also lets untagged signals through, hence `?EXISTS` |
| [`04-news-signals-keyword-monitor.json`](https://github.com/vainu-app/vainu-cli/blob/main/example_payloads/signals_api/04-news-signals-keyword-monitor.json) | Keyword search over signal content in a date window | News only; matching starts at word boundaries |
| [`05-data-changes-for-companies.json`](https://github.com/vainu-app/vainu-cli/blob/main/example_payloads/signals_api/05-data-changes-for-companies.json) | New financial statements and CEO changes for two companies | Data changes have no `countries` field and no text filtering |
| [`06-data-changes-jsonl-paging.json`](https://github.com/vainu-app/vainu-cli/blob/main/example_payloads/signals_api/06-data-changes-jsonl-paging.json) | First page of a JSON Lines export | Raise `offset` by `limit` until a page is short |

```bash
export VAINU_CLIENT_ID=your-client-id
export VAINU_CLIENT_SECRET=your-client-secret

vainu signals-news \
  --payload example_payloads/signals_api/01-news-signals-for-one-company.json
```

`--format jsonl` writes one signal per line, streaming each one as it arrives (pass
`--no-stream` to buffer the whole page instead):

```bash
vainu signals-data-changes \
  --payload example_payloads/signals_api/06-data-changes-jsonl-paging.json \
  --format jsonl \
  --output data_changes.jsonl
```

### Enrichment Agent API payloads

| File | What it shows | Notes |
|---|---|---|
| [`01-run-enrichment-agent-for-one-company.json`](https://github.com/vainu-app/vainu-cli/blob/main/example_payloads/enrichment_agent_api/01-run-enrichment-agent-for-one-company.json) | Running one prompt against one company | `prompt` is `CHANGEME` — swap in the prompt id from your Vainu UI |

```bash
vainu enrichment-agent \
  --payload example_payloads/enrichment_agent_api/01-run-enrichment-agent-for-one-company.json \
  --prompt 12345 \
  --business-id FI01320292
```

---

## Python API

### Async clients

| Class | Auth |
|---|---|
| `VainuAPIKeyClient(api_key, base_url?, language?, timeout?)` | Static API key |
| `VainuOAuthAPIClient(client_id, client_secret, scope?, base_url?, language?, timeout?)` | OAuth 2.0 |

**Methods** (all `async`):

| Method | Description |
|---|---|
| `companies(payload, format)` | Fetch company data (`dict` for `json`, raw `str` for `csv`/`jsonl`) |
| `companies_async(payload, format)` | Submit async job → `AsyncResult` |
| `organizations(payload, format)` | Fetch organization data (`dict` for `json`, raw `str` for `csv`/`jsonl`) |
| `organizations_async(payload, format)` | Submit async job → `AsyncResult` |
| `organization_fields(api_versions?)` | Organization field catalog (`list`) |
| `enrichment_agent(payload, format)` | Run an enrichment agent prompt on one company (`dict` for `json`) |
| `signals_news(payload, format)` | Fetch news signals (`list` for `json`, raw `str` for `jsonl`) |
| `signals_data_changes(payload, format)` | Fetch data-change signals (`list` for `json`, raw `str` for `jsonl`) |
| `organization_lists(format)` | List all organization lists (`list` for `json`) |
| `organization_list_get(list_id, format)` | Retrieve one list summary |
| `organization_list_delete(list_id)` | Delete a list (static or dynamic) |
| `organization_list_static_create(payload, format)` | Create a static list |
| `organization_list_static_update(list_id, payload, format)` | Update a static list |
| `organization_list_static_add(list_id, business_ids)` | Add business IDs to a static list |
| `organization_list_static_remove(list_id, business_ids)` | Remove business IDs from a static list |
| `organization_list_dynamic_create(payload, format)` | Create a dynamic list |
| `organization_list_dynamic_update(list_id, payload, format)` | Update a dynamic list |
| `stream_companies(payload, format)` | Context manager → line iterator (`csv`/`jsonl`) |
| `stream_organizations(payload, format)` | Context manager → line iterator (`csv`/`jsonl`) |
| `stream_signals_news(payload, format)` | Context manager → line iterator (`jsonl`) |
| `stream_signals_data_changes(payload, format)` | Context manager → line iterator (`jsonl`) |
| `close()` | Close HTTP connection |

### Sync clients

| Class | Auth |
|---|---|
| `VainuAPIKeySyncClient(api_key, base_url?, language?, timeout?)` | Static API key |
| `VainuOAuthSyncClient(client_id, client_secret, scope?, base_url?, language?, timeout?)` | OAuth 2.0 |

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
without JSON re-encoding. The signals methods return a `list` under `format="json"` — the
Signals API responds with a bare array rather than a page object — and accept `json`/`jsonl`
only.

`enrichment_agent` returns the prompt's fields under `response` and has no `stream_*` variant,
since one enrichment result is a single document. An uncached run can take minutes, so pass a
higher `timeout` (seconds, default 121) to the client when you expect one:

```python
client = VainuOAuthSyncClient(client_id="...", client_secret="...", timeout=600)
result = client.enrichment_agent(
    payload={"prompt": "12345", "database": "FI", "business_id": "FI23365096"}
)
print(result["response"])
client.close()
```

List management methods (`organization_lists`, `organization_list_static_*`,
`organization_list_dynamic_*`) require OAuth/JWT/browser auth like signals and enrichment — not
a static API key.

```python
import json
from vainu_cli import VainuOAuthSyncClient

client = VainuOAuthSyncClient(client_id="...", client_secret="...")
lists = client.organization_lists()
print(lists[0]["id"], lists[0]["name"])

created = client.organization_list_dynamic_create({
    "name": "Big FI companies",
    "country": "FI",
    "query": json.dumps({"?GTE": {"financial_data.revenue": 1_000_000}}),
})
client.organization_list_delete(created["id"])
client.close()
```

### Streaming

The `stream_*` methods are (async) context managers yielding an iterator of lines, so rows can
be handled while the server is still producing them and no full body is ever held in memory.
Lines arrive as `str` with the newline stripped and blank lines skipped; the response is
released when the `with` block exits, even if you stop iterating early.

```python
import asyncio, json
from vainu_cli import VainuOAuthAPIClient, VainuOAuthSyncClient

# sync
client = VainuOAuthSyncClient(client_id="...", client_secret="...")
with client.stream_signals_news(payload={"query": {}}, format="jsonl") as lines:
    for line in lines:
        print(json.loads(line)["title"])
client.close()

# async
async def main():
    client = VainuOAuthAPIClient(client_id="...", client_secret="...")
    async with client.stream_organizations(payload={"query": {}}, format="jsonl") as lines:
        async for line in lines:
            print(json.loads(line)["business_id"])
    await client.close()

asyncio.run(main())
```

`format` defaults to `jsonl` here and must be a line-oriented format — `format="json"` raises
`ValueError`, since a single JSON document only becomes valid once its last byte lands. With
`csv` the first line is the header row. Error bodies behave as they do on the buffered methods:
`400`/`403`/`404` are yielded as the response text rather than raised, other failures raise.

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
git clone https://github.com/vainu-app/vainu-cli.git
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
