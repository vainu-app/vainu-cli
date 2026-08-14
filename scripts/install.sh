#!/usr/bin/env bash
# Install vainu-cli using uv (bootstraps Python if needed).
set -euo pipefail

UV_INSTALL_URL="https://astral.sh/uv/install.sh"
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

if [[ "$INSTALL_LOCAL" == true ]]; then
  REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
  echo "Installing vainu-cli from ${REPO_ROOT}..."
  uv tool install --editable "${REPO_ROOT}"
else
  echo "Installing vainu-cli from PyPI..."
  uv tool install vainu-cli
fi

echo ""
echo "Installed: $(vainu --version 2>/dev/null || echo 'vainu-cli')"
echo ""
echo "Next steps:"
echo "  vainu login          # sign in via browser"
echo "  vainu examples list  # bundled example payloads"
echo "  vainu organizations --payload \"\$(vainu examples path 08-simple-filtering)\""
