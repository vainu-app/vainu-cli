"""Validate cross-agent CLI skill files."""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILL_ROOT = REPO_ROOT / "skills" / "vainu-cli"
SYMLINK_PATHS = [
    REPO_ROOT / ".cursor" / "skills" / "vainu-cli",
    REPO_ROOT / ".claude" / "skills" / "vainu-cli",
    REPO_ROOT / ".agents" / "skills" / "vainu-cli",
]
SYMLINK_IDS = ["cursor", "claude", "agents"]
CODEX_AGENTS_MD_MAX_BYTES = 32 * 1024


def _parse_frontmatter(text: str) -> dict[str, str]:
    match = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
    if not match:
        msg = "SKILL.md must start with YAML frontmatter"
        raise ValueError(msg)
    fields: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            fields[key.strip()] = value.strip()
    return fields


class TestSkillFiles:
    def test_canonical_skill_files_exist(self) -> None:
        assert (SKILL_ROOT / "SKILL.md").is_file()
        assert (SKILL_ROOT / "organizations.md").is_file()
        assert (SKILL_ROOT / "signals.md").is_file()

    def test_skill_frontmatter(self) -> None:
        text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        fields = _parse_frontmatter(text)
        assert fields["name"] == "vainu-cli"
        assert len(fields["name"]) <= 64
        assert fields["description"]
        assert len(fields["description"]) <= 1024
        assert text.count("\n") + 1 <= 500

    def test_skill_links_to_reference_files(self) -> None:
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        assert "organizations.md" in skill
        assert "signals.md" in skill

    def test_reference_files_non_empty(self) -> None:
        for name in ("organizations.md", "signals.md"):
            content = (SKILL_ROOT / name).read_text(encoding="utf-8")
            assert len(content.strip()) > 100, f"{name} looks too short"


class TestSkillSymlinks:
    @pytest.mark.parametrize("link_path", SYMLINK_PATHS, ids=SYMLINK_IDS)
    def test_symlink_points_to_canonical_skill(self, link_path: Path) -> None:
        assert link_path.is_symlink(), f"{link_path} should be a symlink"
        assert link_path.resolve() == SKILL_ROOT.resolve()
        assert (link_path / "SKILL.md").is_file()


class TestAgentDocs:
    def test_agents_md_under_codex_size_cap(self) -> None:
        agents_md = REPO_ROOT / "AGENTS.md"
        size = agents_md.stat().st_size
        assert size < CODEX_AGENTS_MD_MAX_BYTES, (
            f"AGENTS.md is {size} bytes; keep under {CODEX_AGENTS_MD_MAX_BYTES} for Codex"
        )

    def test_agents_md_links_to_skill(self) -> None:
        content = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")
        assert "skills/vainu-cli" in content


class TestInstallSkillsScript:
    def test_install_script_exists_and_executable(self) -> None:
        script = REPO_ROOT / "scripts" / "install-skills.sh"
        assert script.is_file()
        assert script.stat().st_mode & 0o111, "install-skills.sh should be executable"
