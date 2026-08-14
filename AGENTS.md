# Using Vainu with AI agents

This guide is for Cursor, Claude Code, and other agent-assisted workflows. Users do
not need Python or pip knowledge if they follow the MCP path below.

## Recommended: Vainu MCP (no install)

Add the hosted Vainu MCP server to your IDE. The agent gets typed tools for company
search, signals, documents, and saved lists — with OAuth handled by the IDE.

### Cursor

1. Open **Settings → MCP → Add server** (or edit `~/.cursor/mcp.json`).
2. Paste the snippet below, replacing the placeholders with credentials from your
   Vainu account.
3. Save and restart MCP / reload the window. Sign in when prompted on first use.

```json
{
  "mcpServers": {
    "vainu": {
      "url": "https://mcp.vainu.ai/mcp",
      "auth": {
        "CLIENT_ID": "<your-client-id>",
        "CLIENT_SECRET": "<your-client-secret>",
        "scopes": ["offline_access", "vainu:mcp"]
      }
    }
  }
}
```

### Claude Code / other MCP clients

Use the same URL and OAuth client credentials. Consult your client's MCP
configuration docs for the exact JSON shape.

### When to use MCP

- Natural-language company research and list building
- Exploring VQL filters (`search_filter_values` → `validate_query` → `query_organizations`)
- News and data-change signals
- Document search
- Anything where the agent should discover tools and iterate on queries

---

## Fallback: vainu-cli via uv

Use the CLI when you need bulk exports, shell pipelines, CI jobs, or the Python
library. **Do not ask users to run `pip install`.** Use `uv` instead — it bootstraps
Python automatically.

### One-line install (agent-runnable)

```bash
curl -LsSf https://raw.githubusercontent.com/vainu-app/vainu-cli/main/scripts/install.sh | sh
```

Or from a git checkout:

```bash
./scripts/install.sh --local
```

### Manual install

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
uv tool install vainu-cli
```

Run without installing:

```bash
uvx vainu-cli --version
```

### Authenticate

```bash
vainu login
```

Or set credentials via environment variables:

```bash
export VAINU_API_KEY=your-api-key
# OAuth (required for signals commands):
export VAINU_CLIENT_ID=your-client-id
export VAINU_CLIENT_SECRET=your-client-secret
```

### Bundled example payloads

Example request bodies ship inside the installed package. List them:

```bash
vainu examples list
vainu examples list --category organizations_api
```

Resolve a path for `--payload`:

```bash
vainu organizations --payload "$(vainu examples path 08-simple-filtering)"
vainu signals-news --payload "$(vainu examples path 01-news-signals-for-one-company)"
```

From Python:

```python
from vainu_cli.examples import examples_dir, resolve_example

print(examples_dir())
print(resolve_example("08-simple-filtering"))
```

### Common CLI commands

```bash
# Quick company lookup (API key)
vainu companies --query "?country=FI&business_id=FI01320292"

# Organizations search with a JSON payload
vainu organizations --payload "$(vainu examples path 08-simple-filtering)"

# Large export to file
vainu organizations-async \
  --payload "$(vainu examples path 04-get-all-companies-in-vainu-list-async-sync)" \
  --format jsonl \
  --output companies.jsonl

# Signals (OAuth required)
vainu --auth-method oauth signals-news \
  --payload "$(vainu examples path 01-news-signals-for-one-company)"
```

---

## MCP vs CLI — quick reference

| Task | Use |
|------|-----|
| Agent-driven research in the IDE | MCP |
| Bulk async export to JSONL/CSV | CLI (`*-async` commands) |
| Shell pipes (`\| jq`, `\| grep`) | CLI with `--format jsonl` |
| CI / cron automation | CLI or Python library |
| Custom Python integration | `from vainu_cli import VainuAPIKeyClient` |

---

## Agent instructions (copy-paste)

If you are an AI agent helping a user set up Vainu:

1. **Prefer MCP.** Add the JSON config from above to the user's MCP settings. No
   terminal install is required.
2. **If MCP is unavailable**, run the install script or `uv tool install vainu-cli`,
   then `vainu login`.
3. **For API calls via CLI**, use bundled examples: `vainu examples list` and
   `vainu examples path <name>` — do not ask the user to hand-write JSON unless
   necessary.
4. **Signals commands** require OAuth (`--auth-method oauth` or `vainu login`), not
   a static API key alone.
5. See [README.md](README.md) for full CLI reference and payload documentation.
