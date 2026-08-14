# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `vainu fields organizations` — inspect organization field metadata from
  `GET /v3/organizations_fields/`, including which paths are filterable vs returnable
  and which require an extra account permission
- `organization_fields(api_versions)` on the async and sync clients

- [SETUP.md](SETUP.md) — step-by-step install guide for non-technical users (Mac, Windows, Linux)
- `scripts/install.ps1` — Windows PowerShell installer via uv
- `vainu doctor` — verify install, auth, and bundled examples
- [AGENTS.md](AGENTS.md) — setup guide for Cursor/Claude Code/Codex (uv CLI install + agent skills)
- Cross-agent CLI skill under [skills/vainu-cli/](skills/vainu-cli/) (symlinked to `.cursor/skills/`, `.claude/skills/`, `.agents/skills/`)
- `scripts/install-skills.sh` — copy skill to personal agent directories
- `scripts/install.sh` — one-line install via uv (`curl … | sh` or `./scripts/install.sh --local`)
- Example payloads bundled in the wheel under `vainu_cli/example_payloads/`
- `vainu examples list` and `vainu examples path` to discover bundled payloads after install
- `vainu enrichment-agent` — run an enrichment agent prompt (built in the Vainu UI) against one
  company and get the prompt's structured fields back. Takes `--prompt`, `--database` and
  `--business-id` directly, or the same keys via `--payload` with flags overriding the file, plus
  `--refresh` to bypass the server-side cache
- `enrichment_agent(payload, format)` on the async and sync clients, hitting
  `POST /v3/enrichment_agent/`
- `timeout` argument on every client constructor, surfaced as `--request-timeout` on
  `enrichment-agent`: an uncached agent run researches the company on the spot and can outlast
  the 121s default
- Example Enrichment Agent API request body under `example_payloads/enrichment_agent_api/`
- Line-by-line streaming on `companies`, `organizations`, `signals-news` and
  `signals-data-changes`, **on by default** for `--format jsonl` and `csv`: each line is written
  as it arrives instead of the whole body being buffered first. `--no-stream` restores the
  buffered behaviour, and `--format json` still buffers (a single JSON document cannot be split
  into lines)
- `stream_companies` / `stream_organizations` / `stream_signals_news` /
  `stream_signals_data_changes` on the async and sync clients: (async) context managers yielding
  an iterator of lines, with the same auth-retry behaviour as the buffered methods
- `vainu signals-news` — fetch news signals from the v3 Signals API (beta)
- `vainu signals-data-changes` — fetch data-change signals from the v3 Signals API (beta)
- `signals_news` / `signals_data_changes` on the async and sync clients, returning the API's
  bare JSON array under `format="json"`
- Example Signals API request bodies under `example_payloads/signals_api/`, covering tag
  filtering, keyword monitoring and JSON Lines paging
- Example Organizations API request bodies under `example_payloads/organizations_api/`, with a
  README section cataloguing them and showing how to run each one through the CLI

## [0.1.0] - 2026-04-13

### Added

- `vainu companies search` — fetch company data synchronously (GET or POST)
- `vainu companies export` — submit an async export job, poll until complete, download to file
- `vainu organizations search` — fetch organization data via POST
- `vainu organizations export` — async export for organizations
- Authentication via API key (`--api-key` / `VAINU_API_KEY`)
- Authentication via OAuth 2.0 client credentials (`--auth-method oauth`)
- `VainuAPIKeyClient` — async httpx-based client
- `VainuAPIKeySyncClient` — synchronous requests-based client
- `VainuOAuthAPIClient` / `VainuOAuthSyncClient` — OAuth clients with automatic token refresh
- Automatic async job polling with configurable `--poll-interval` and `--timeout`
- `--format` option: `json`, `csv`, `jsonl`
- `--output` option to write results to a file instead of stdout
- PEP 561 `py.typed` marker for downstream type checkers
