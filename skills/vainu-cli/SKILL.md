---
name: vainu-cli
description: Install, authenticate, and run the vainu-cli for Nordic company data — organizations search, bulk export, signals, and shell pipelines. Use when the user asks to query Vainu via terminal, vainu commands, JSONL/CSV export, or CI automation.
---

# vainu-cli

CLI and Python client for the [Vainu](https://vainu.com) API.

## Common use cases

| Task | Approach |
|------|----------|
| Company / organization search | `vainu organizations --payload ...` |
| Bulk async export to JSONL/CSV | `vainu organizations-async` / `companies-async` |
| Shell pipes (`\| jq`, `\| grep`) | CLI with `--format jsonl` |
| CI / cron / offline scripts | CLI or Python library |

## Install (agent-runnable)

Never lead with `pip install`. Use `uv` — it bootstraps Python automatically.

**Non-technical users:** point them to [SETUP.md](../../SETUP.md) (Mac, Windows, Linux).

```bash
# Mac / Linux
curl -LsSf https://raw.githubusercontent.com/vainu-app/vainu-cli/main/scripts/install.sh | sh
# Windows (PowerShell)
# irm https://raw.githubusercontent.com/vainu-app/vainu-cli/main/scripts/install.ps1 | iex
# git checkout:
./scripts/install.sh --local
# one-off without install:
uvx vainu-cli --version
```

After install: `vainu login` then `vainu doctor`.

## Authenticate

```bash
vainu login   # browser OAuth — easiest for non-devs
```

Or environment variables:

| Method | Variables | Works for |
|--------|-----------|-----------|
| API key | `VAINU_API_KEY` | `companies`, `organizations` |
| OAuth | `VAINU_CLIENT_ID`, `VAINU_CLIENT_SECRET` | orgs + **signals** |
| JWT | `VAINU_JWT_REFRESH_TOKEN` + `--auth-method jwt` | orgs + signals |
| Browser session | `vainu login` (stored credentials) | all commands |

**Signals require OAuth, JWT, or `vainu login` — not a static API key alone.**

Optional: `VAINU_BASE_URL` to override the API host.

## Command routing

| Command | API | Input |
|---------|-----|-------|
| `vainu companies` | v2 GET/POST | `--query "?country=FI&..."` or `--payload` |
| `vainu companies-async` | v2 async export | `--payload` + required `--output` |
| `vainu organizations` | v3 POST | `--payload` JSON with `database` + `query` |
| `vainu organizations-async` | v3 async export | `--payload` + required `--output` |
| `vainu signals-news` | v3 signals | `--payload` JSON, OAuth/JWT/login |
| `vainu signals-data-changes` | v3 signals | `--payload` JSON, OAuth/JWT/login |
| `vainu lists` | v3 list index | OAuth/JWT/login — list all organization lists |
| `vainu lists delete ID` | v3 list index | delete any list by id |
| `vainu lists static` | v3 static lists | list, create, update, add, remove, delete |
| `vainu lists dynamic` | v3 dynamic lists | list, create, update, delete |

Country scoping for organizations: set `"database": "FI"` \| `"SE"` \| `"NO"` \| `"DK"` in the payload (not a separate `country` key).

## Bundled examples (prefer these)

Example payloads ship with the package. Do not hand-write JSON unless necessary.

```bash
vainu examples list
vainu examples list --category organizations_api
vainu organizations --payload "$(vainu examples path 08-simple-filtering)"
vainu signals-news --payload "$(vainu examples path 01-news-signals-for-one-company)"
```

Adapt a bundled example by copying its path, editing fields, then passing to `--payload`.

## Output and streaming

- `--format jsonl` and `csv` **stream by default** (line-by-line)
- `--format json` buffers the full body (organizations/companies only)
- Signals support `json` and `jsonl` only (no CSV)
- `--output FILE` writes to file; status messages go to stderr

Large result sets: use `*-async` with `--format jsonl --output file.jsonl`.

## Reference files

- [organizations.md](organizations.md) — VQL payload patterns for `vainu organizations*`
- [signals.md](signals.md) — payload rules for `vainu signals-*`
- [README.md](../../README.md) — full CLI reference
- [SETUP.md](../../SETUP.md) — non-technical setup (Mac, Windows, Linux)
- [AGENTS.md](../../AGENTS.md) — agent setup and cross-agent install notes
