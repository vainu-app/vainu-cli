# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

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
- GitLab CI/CD pipeline: ruff, bandit, pip-audit, pytest (Python 3.11–3.13), build, PyPI publish
