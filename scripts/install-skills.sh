#!/usr/bin/env bash
# Copy vainu-cli agent skills to personal skill directories.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
SKILL_SRC="${REPO_ROOT}/skills/vainu-cli"
SKILL_NAME="vainu-cli"

INSTALL_CURSOR=true
INSTALL_CLAUDE=true
INSTALL_CODEX=true

usage() {
  echo "Usage: $0 [--cursor-only | --claude-only | --codex-only]"
  echo ""
  echo "Copy skills/vainu-cli/ to personal agent skill directories:"
  echo "  Cursor:      ~/.cursor/skills/${SKILL_NAME}/"
  echo "  Claude Code: ~/.claude/skills/${SKILL_NAME}/"
  echo "  Codex:       ~/.agents/skills/${SKILL_NAME}/"
  exit 0
}

for arg in "$@"; do
  case "$arg" in
    --cursor-only)
      INSTALL_CLAUDE=false
      INSTALL_CODEX=false
      ;;
    --claude-only)
      INSTALL_CURSOR=false
      INSTALL_CODEX=false
      ;;
    --codex-only)
      INSTALL_CURSOR=false
      INSTALL_CLAUDE=false
      ;;
    -h | --help)
      usage
      ;;
    *)
      echo "Unknown option: $arg" >&2
      usage
      ;;
  esac
done

if [[ ! -f "${SKILL_SRC}/SKILL.md" ]]; then
  echo "Skill source not found: ${SKILL_SRC}/SKILL.md" >&2
  exit 1
fi

install_skill() {
  local dest_parent="$1"
  local label="$2"
  local dest="${dest_parent}/${SKILL_NAME}"

  mkdir -p "${dest_parent}"
  rm -rf "${dest}"
  cp -R "${SKILL_SRC}" "${dest}"
  echo "Installed ${label} skill → ${dest}"
}

if [[ "$INSTALL_CURSOR" == true ]]; then
  install_skill "${HOME}/.cursor/skills" "Cursor"
fi

if [[ "$INSTALL_CLAUDE" == true ]]; then
  install_skill "${HOME}/.claude/skills" "Claude Code"
fi

if [[ "$INSTALL_CODEX" == true ]]; then
  install_skill "${HOME}/.agents/skills" "Codex"
fi

echo ""
echo "Done. Agents will discover the skill via its description in SKILL.md."
