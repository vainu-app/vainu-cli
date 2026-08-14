# Using Vainu with AI agents

This guide is for Cursor, Claude Code, ChatGPT Codex, and other agent-assisted
workflows. **Use vainu-cli via `uv`** — no manual Python or pip setup required.

**Non-technical users** should start with [SETUP.md](SETUP.md) instead (Mac, Windows, Linux).

For detailed **CLI workflows** (VQL payloads, signals, auth, exports), load the
`vainu-cli` agent skill — see [Agent skills](#agent-skills) below.

## Install vainu-cli via uv

**Do not ask users to run `pip install`.** Use `uv` instead — it bootstraps Python
automatically.

### Mac / Linux

```bash
curl -LsSf https://raw.githubusercontent.com/vainu-app/vainu-cli/main/scripts/install.sh | sh
```

### Windows (PowerShell)

```powershell
irm https://raw.githubusercontent.com/vainu-app/vainu-cli/main/scripts/install.ps1 | iex
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
vainu doctor   # verify install and auth
```

See the `vainu-cli` skill ([skills/vainu-cli/SKILL.md](skills/vainu-cli/SKILL.md)) for
auth options (API key, OAuth, JWT) and command routing.

---

## Agent skills

Canonical skill source: [skills/vainu-cli/](skills/vainu-cli/) (`SKILL.md` + reference
files). Repo symlinks wire it into each tool's discovery path:

| Tool | Project path |
|------|----------------|
| Cursor | `.cursor/skills/vainu-cli/` |
| Claude Code | `.claude/skills/vainu-cli/` (invoke as `/vainu-cli`) |
| ChatGPT Codex | `.agents/skills/vainu-cli/` |

**Personal install** (PyPI/uv users without cloning the repo):

```bash
./scripts/install-skills.sh              # ~/.cursor, ~/.claude, ~/.agents
./scripts/install-skills.sh --codex-only
```

Codex also reads this `AGENTS.md` every session — keep it for setup routing; the skill
carries detailed CLI instructions (VQL, signals, exports).

---

## CLI use cases

| Task | Approach |
|------|----------|
| Company / organization search | `vainu organizations --payload ...` |
| Bulk async export to JSONL/CSV | `vainu organizations-async` / `companies-async` |
| Shell pipes (`\| jq`, `\| grep`) | CLI with `--format jsonl` |
| CI / cron automation | CLI or Python library |
| Custom Python integration | `from vainu_cli import VainuAPIKeyClient` |

---

## Agent instructions (copy-paste)

If you are an AI agent helping a user set up Vainu:

1. Run the install script ([SETUP.md](SETUP.md): Mac/Linux `install.sh`, Windows `install.ps1`) or `uv tool install vainu-cli`, then `vainu login` and `vainu doctor`.
2. Load the `vainu-cli` skill for command routing and payload patterns.
3. Use bundled examples: `vainu examples list` and `vainu examples path <name>` — do not
   hand-write JSON unless necessary.
4. **Signals commands** require OAuth (`--auth-method oauth` or `vainu login`), not
   a static API key alone.
5. See [skills/vainu-cli/SKILL.md](skills/vainu-cli/SKILL.md) and [README.md](README.md)
   for full CLI reference.
