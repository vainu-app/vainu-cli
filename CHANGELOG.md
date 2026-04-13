# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
