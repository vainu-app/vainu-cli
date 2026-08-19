#!/bin/sh
# Install or upgrade vainu-cli using uv (bootstraps Python if needed).
# POSIX sh: docs pipe this script to `sh`, which is dash on Debian/Ubuntu.
set -eu

UV_INSTALL_URL="https://astral.sh/uv/install.sh"
GIT_URL="git+https://github.com/vainu-app/vainu-cli.git"
PYPI_JSON_URL="https://pypi.org/pypi/vainu-cli/json"
INSTALL_LOCAL=false
UPGRADE_MODE=ask # ask | always | never

for arg in "$@"; do
  case "$arg" in
    --local)
      INSTALL_LOCAL=true
      ;;
    --upgrade | -y | --yes)
      UPGRADE_MODE=always
      ;;
    --no-upgrade)
      UPGRADE_MODE=never
      ;;
    -h | --help)
      echo "Usage: $0 [--local] [--upgrade|-y] [--no-upgrade]"
      echo ""
      echo "Install or upgrade vainu-cli with uv."
      echo "  --local        install from the git checkout containing this script"
      echo "  --upgrade, -y  upgrade an existing install without asking"
      echo "  --no-upgrade   keep an existing install as-is"
      echo ""
      echo "With no flags, an existing install prompts before upgrading when a"
      echo "terminal is available, and upgrades automatically when it is not."
      exit 0
      ;;
    *)
      echo "Unknown option: $arg" >&2
      echo "Run $0 --help for usage." >&2
      exit 1
      ;;
  esac
done

# Version of vainu-cli currently installed as a uv tool ("" if not installed).
installed_version() {
  uv tool list 2>/dev/null | sed -n 's/^vainu-cli v\([^ ]*\).*/\1/p' | head -n 1
}

# Latest version published to PyPI ("" if the lookup fails).
latest_version() {
  curl -LsSf "$PYPI_JSON_URL" 2>/dev/null |
    tr ',' '\n' |
    sed -n 's/.*"version":"\([^"]*\)".*/\1/p' |
    head -n 1
}

# Whether there is somebody to ask: a terminal, and not a CI run.
can_prompt() {
  [ -z "${CI:-}" ] && [ -r /dev/tty ]
}

# Ask a yes/no question, defaulting to yes. Reads from /dev/tty, not stdin:
# stdin is the piped script itself, so a plain `read` would eat the script.
confirm() {
  printf '%s [Y/n] ' "$1"
  read -r reply < /dev/tty || reply=""
  case "$reply" in
    "" | y | Y | yes | YES | Yes) return 0 ;;
    *) return 1 ;;
  esac
}

print_next_steps() {
  echo ""
  echo "Next steps:"
  echo "  vainu login          # sign in via browser"
  echo "  vainu doctor         # verify everything works"
  echo "  vainu examples list  # bundled example payloads"
}

if ! command -v uv >/dev/null 2>&1; then
  echo "Installing uv..."
  curl -LsSf "$UV_INSTALL_URL" | sh
fi

export PATH="${HOME}/.local/bin:${PATH}"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv was installed but is not on PATH. Add ~/.local/bin to PATH and retry." >&2
  exit 1
fi

if [ "$INSTALL_LOCAL" = true ]; then
  REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
  echo "Installing vainu-cli from ${REPO_ROOT}..."
  uv tool install --force --editable "${REPO_ROOT}"
else
  CURRENT="$(installed_version)"
  if [ -n "$CURRENT" ]; then
    LATEST="$(latest_version)"

    if [ -n "$LATEST" ] && [ "$CURRENT" = "$LATEST" ]; then
      echo "vainu-cli ${CURRENT} is already the latest version."
      print_next_steps
      exit 0
    fi

    if [ -n "$LATEST" ]; then
      echo "vainu-cli ${CURRENT} is installed; PyPI has ${LATEST}."
    else
      echo "vainu-cli ${CURRENT} is installed; could not reach PyPI to check for a newer version."
    fi

    case "$UPGRADE_MODE" in
      never)
        echo "Keeping vainu-cli ${CURRENT} (--no-upgrade)."
        print_next_steps
        exit 0
        ;;
      ask)
        if can_prompt; then
          if ! confirm "Upgrade now?"; then
            echo "Keeping vainu-cli ${CURRENT}. Re-run with --upgrade to upgrade later."
            print_next_steps
            exit 0
          fi
        else
          echo "Non-interactive shell — upgrading automatically (pass --no-upgrade to skip)."
        fi
        ;;
    esac

    echo "Upgrading vainu-cli..."
    if ! uv tool upgrade vainu-cli; then
      uv tool install --force vainu-cli
    fi
    # An install pinned to a git ref stays on that ref through `upgrade`;
    # reinstall from PyPI when it did not land on the published version.
    if [ -n "$LATEST" ] && [ "$(installed_version)" != "$LATEST" ]; then
      echo "Reinstalling vainu-cli ${LATEST} from PyPI..."
      uv tool install --force vainu-cli
    fi
  else
    echo "Installing vainu-cli from PyPI..."
    if ! uv tool install vainu-cli; then
      echo ""
      echo "PyPI install failed — falling back to GitHub (${GIT_URL})..."
      uv tool install "$GIT_URL"
    fi
  fi
fi

echo ""
echo "Installed: $(vainu --version 2>/dev/null || echo 'vainu-cli (open a new terminal if vainu is not found)')"
print_next_steps
if ! command -v vainu >/dev/null 2>&1; then
  echo ""
  echo "If 'vainu' is not found, close this terminal and open a new one."
  case "$(uname -s)" in
    Darwin)
      echo "Still missing? Add to ~/.zprofile:  export PATH=\"\$HOME/.local/bin:\$PATH\""
      ;;
    Linux)
      echo "Still missing? Add to ~/.bashrc:  export PATH=\"\$HOME/.local/bin:\$PATH\""
      ;;
  esac
  echo "See the README 'Get started' section for step-by-step instructions."
fi
