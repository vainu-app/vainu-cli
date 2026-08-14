#!/bin/sh
# Install vainu-cli using uv (bootstraps Python if needed).
# POSIX sh: docs pipe this script to `sh`, which is dash on Debian/Ubuntu.
set -eu

UV_INSTALL_URL="https://astral.sh/uv/install.sh"
GIT_URL="git+https://github.com/vainu-app/vainu-cli.git"
INSTALL_LOCAL=false

for arg in "$@"; do
  case "$arg" in
    --local)
      INSTALL_LOCAL=true
      ;;
    -h | --help)
      echo "Usage: $0 [--local]"
      echo ""
      echo "Install vainu-cli with uv."
      echo "  --local   install from the git checkout containing this script"
      exit 0
      ;;
    *)
      echo "Unknown option: $arg" >&2
      echo "Run $0 --help for usage." >&2
      exit 1
      ;;
  esac
done

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
  uv tool install --editable "${REPO_ROOT}"
else
  echo "Installing vainu-cli from PyPI..."
  if ! uv tool install vainu-cli; then
    echo ""
    echo "PyPI install failed — falling back to GitHub (${GIT_URL})..."
    uv tool install "$GIT_URL"
  fi
fi

echo ""
echo "Installed: $(vainu --version 2>/dev/null || echo 'vainu-cli (open a new terminal if vainu is not found)')"
echo ""
echo "Next steps:"
echo "  vainu login          # sign in via browser"
echo "  vainu doctor         # verify everything works"
echo "  vainu examples list  # bundled example payloads"
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
