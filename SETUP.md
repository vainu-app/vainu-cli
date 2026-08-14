# Get started with Vainu (Mac, Windows, Linux)

No coding experience needed. You will copy one command, sign in with your browser,
and run your first company search.

**Time:** about 5 minutes.

---

## Step 1 — Install

Pick the section for your computer.

### Mac

1. Open **Terminal** (press `Cmd + Space`, type `Terminal`, press Enter).
2. Copy and paste this entire line, then press Enter:

```bash
curl -LsSf https://raw.githubusercontent.com/vainu-app/vainu-cli/main/scripts/install.sh | sh
```

3. Wait until you see `Next steps:` — installation is done.
4. **Close Terminal and open it again** (so the `vainu` command is recognized).

### Windows

1. Open **PowerShell** (Start menu → type `PowerShell` → open **Windows PowerShell**).
2. Copy and paste this entire line, then press Enter:

```powershell
irm https://raw.githubusercontent.com/vainu-app/vainu-cli/main/scripts/install.ps1 | iex
```

3. Wait until you see `Next steps:` — installation is done.
4. **Close PowerShell and open it again.**

> If Windows blocks the script, run PowerShell as your normal user (not Administrator)
> and try again. The installer uses [uv](https://docs.astral.sh/uv/) to handle Python
> automatically — you do not need to install Python yourself.

### Linux

Same as Mac — open a terminal and run:

```bash
curl -LsSf https://raw.githubusercontent.com/vainu-app/vainu-cli/main/scripts/install.sh | sh
```

Then close and reopen the terminal.

---

## Step 2 — Sign in

In Terminal (Mac/Linux) or PowerShell (Windows), run:

```bash
vainu login
```

Your browser opens. Sign in with your Vainu account. When done, return to the
terminal — you should see `Logged in as ...`.

---

## Step 3 — Verify

```bash
vainu doctor
```

You should see `All checks passed.` If something failed, the command prints what to
fix.

---

## Step 4 — Your first search

Look up a Finnish company by business ID:

**Mac / Linux:**

```bash
vainu organizations --payload "$(vainu examples path 08-simple-filtering)"
```

**Windows (PowerShell):**

```powershell
vainu organizations --payload (vainu examples path 08-simple-filtering)
```

You get JSON with company details. That's it.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `'vainu' is not recognized` | Close and reopen Terminal / PowerShell. Still broken? Run install again. |
| Mac: command not found after install | Add to `~/.zprofile`: `export PATH="$HOME/.local/bin:$PATH"`, then open a new window. |
| Linux: command not found after install | Add to `~/.bashrc`: `export PATH="$HOME/.local/bin:$PATH"`, then open a new window. |
| Windows: command not found | Close PowerShell completely and reopen. Check `%USERPROFILE%\.local\bin` exists. |
| Login browser does not open | Run `vainu login --no-browser` and open the printed URL manually. |
| Signals commands fail | Signals need OAuth — use `vainu login`, not an API key alone. |
| Want the latest CLI | Run `vainu update` (or `vainu upgrade`). |

Run `vainu doctor` anytime to diagnose install and auth issues.

---

## Using with AI assistants (Cursor, Claude, Codex)

If you use an AI coding assistant, see [AGENTS.md](AGENTS.md) for agent skills and
optional skill installation (`scripts/install-skills.sh` on Mac/Linux).

---

## Next steps

- [README.md](README.md) — full command reference
- [skills/vainu-cli/SKILL.md](skills/vainu-cli/SKILL.md) — guide for AI agents
- `vainu examples list` — browse ready-made search templates
- `vainu update` — upgrade to the latest version
- `vainu --help` — list all commands
