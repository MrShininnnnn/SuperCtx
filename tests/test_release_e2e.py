"""v0.2 release check: one repository through the whole lifecycle, driven by the CLI
the plugin runs (source tree on PYTHONPATH, no install).

Adoption, canonical edits, publication, native edits, conflict reporting, recovery,
and repeat sync, then the same for a workspace set up by the released v0.1.4 client.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from superctx import manifest
from test_v2_migration_safety import AGENTS_ORIGINAL, CLAUDE_ORIGINAL, build_v1, legacy_scripts, snapshot, write  # noqa: F401 (fixture)

ROOT = Path(__file__).resolve().parents[1]

FILES = {
    "CLAUDE.md": "# Claude\n\nRun the tests before committing.\n",
    "AGENTS.md": "# Agents\n\nPrefer small diffs.\n",
    ".claude/rules/python.md": '---\npaths:\n  - "src/**/*.py"\n---\n\nUse type hints.\n',
    ".cursor/rules/style.mdc": "---\nglobs: src/**/*.py\nalwaysApply: false\n---\n\nUse snake_case.\n",
    ".claude/skills/review/SKILL.md": "---\nname: review\ndescription: Review a diff\n---\n\nRun scripts/run.sh.\n",
    ".grok/skills/deploy/SKILL.md": "---\nname: deploy\ndescription: Deploy\n---\n\nShip it.\n",
    "docs/architecture/adr-1.md": "# ADR 1\n\nSee [the code](../../src/app.py).\n",
    ".planning/2026-11-05-release/progress.md": "# Progress\n",
    "src/app.py": "print('hello')\n",
}
SCRIPT = (".claude/skills/review/scripts/run.sh", "#!/bin/sh\necho review\n")
# Tool configuration SuperCtx must never touch.
CONFIG = {
    ".grok/config.toml": "[permissions]\nallow = []\n",
    ".grok/hooks/check.json": "{}\n",
    ".claude/settings.json": "{}\n",
    ".cursor/hooks.json": "{}\n",
}
LINKS = {
    ".claude/rules/python.md": "../../.ctx/rules/python.md",
    ".cursor/rules/style.mdc": "../../.ctx/cursor-rules/style.mdc",
    ".claude/skills/review": "../../.ctx/skills/review",
    ".grok/skills/deploy": "../../.ctx/skills/deploy",
}
FOLDERS = {"docs/architecture": "../.ctx/architecture", ".planning": ".ctx/planning"}


def cli(project: Path, *args: str) -> tuple[int, str]:
    env = dict(os.environ, PYTHONPATH=str(ROOT / "scripts"))
    out = subprocess.run([sys.executable, "-m", "superctx", *args], cwd=project, env=env,
                         capture_output=True, text=True)
    assert "Traceback" not in out.stderr, out.stderr
    return out.returncode, out.stdout + out.stderr


def read(project: Path, rel: str) -> str:
    return (project / rel).read_text(encoding="utf-8")


def unchanged_sync(project: Path) -> None:
    before = snapshot(project)
    code, out = cli(project, "sync")
    assert code == 0 and "healthy" in out, out
    assert snapshot(project) == before


def test_release_lifecycle(tmp_path):
    project = tmp_path / "repo"
    for rel, text in {**FILES, **CONFIG}.items():
        write(project, rel, text)
    write(project, *SCRIPT, mode=0o755)
    config = {rel: snapshot(project / rel) if (project / rel).is_dir() else read(project, rel) for rel in CONFIG}

    # 1. Adoption: one sync sets up instructions, rules, and skills; folders wait for add.
    code, out = cli(project, "sync")
    assert code == 0, out
    for rel, target in LINKS.items():
        assert os.readlink(project / rel) == target
        assert read(project, f".ctx/sources/{rel}/SKILL.md" if "skills" in rel else f".ctx/sources/{rel}") \
            == FILES[f"{rel}/SKILL.md" if "skills" in rel else rel]
    hub = read(project, ".ctx/SUPERCTX.md")
    assert "Run the tests before committing." in hub and "Prefer small diffs." in hub
    assert "SUPERCTX.md" in read(project, "CLAUDE.md") and "SUPERCTX.md" in read(project, "AGENTS.md")
    assert not os.path.islink(project / "docs/architecture") and not os.path.islink(project / ".planning")
    code, out = cli(project, "sync")
    assert code == 0 and "- .planning" in out, out  # a candidate, never adopted by setup

    for rel, target in FOLDERS.items():
        code, out = cli(project, "add", rel)
        assert code == 0 and "Added" in out, out
        assert os.readlink(project / rel) == target
    unchanged_sync(project)
    code, out = cli(project, "add", "docs/architecture")
    assert code == 0 and "already tracked" in out
    code, out = cli(project, "add", ".grok/hooks")
    assert code == 1 and "tool_folder" in out

    # 2. Canonical edits are what every tool reads, with nothing to publish.
    with open(project / ".ctx/SUPERCTX.md", "a", encoding="utf-8") as f:
        f.write("\nUse Python 3.9+.\n")
    write(project, ".ctx/rules/python.md", FILES[".claude/rules/python.md"] + "Prefer dataclasses.\n")
    write(project, ".ctx/skills/review/SKILL.md", FILES[".claude/skills/review/SKILL.md"] + "Be brief.\n")
    assert read(project, ".claude/rules/python.md").endswith("Prefer dataclasses.\n")
    assert read(project, ".claude/skills/review/SKILL.md").endswith("Be brief.\n")
    unchanged_sync(project)

    # 3. Edits through a link reach the canonical file (planning tools write this way).
    with open(project / ".planning/2026-11-05-release/progress.md", "a", encoding="utf-8") as f:
        f.write("- [x] adopted\n")
    assert read(project, ".ctx/planning/2026-11-05-release/progress.md") == "# Progress\n- [x] adopted\n"
    unchanged_sync(project)

    # 4. Publication: deleted pointers and links are recreated.
    for rel in ("AGENTS.md", ".claude/rules/python.md", ".grok/skills/deploy", ".planning"):
        os.unlink(project / rel)
    code, out = cli(project, "sync")
    assert code == 0, out
    for rel in ("AGENTS.md", ".claude/rules/python.md", ".grok/skills/deploy", ".planning"):
        assert f"+ {rel}" in out
    assert os.readlink(project / ".planning") == ".ctx/planning"
    assert "SUPERCTX.md" in read(project, "AGENTS.md")
    unchanged_sync(project)

    # 5. Native edits that bypass the canonical copy are conflicts: preserved and reported,
    # while the same run still repairs a pointer and a link that are merely missing.
    write(project, "CLAUDE.md", "Never use tabs.\n")                         # pointer edited
    os.unlink(project / ".claude/rules/python.md")                           # link replaced
    write(project, ".claude/rules/python.md", "Use mypy.\n")
    os.unlink(project / ".cursor/rules/style.mdc")                           # link retargeted
    os.symlink("../../src/app.py", project / ".cursor/rules/style.mdc")
    shutil.rmtree(project / ".ctx/architecture")                             # canonical deleted
    os.unlink(project / "AGENTS.md")                                         # pointer missing
    os.unlink(project / ".grok/skills/deploy")                               # link missing
    before = snapshot(project)
    code, out = cli(project, "sync")
    assert code == 1, out
    assert "! CLAUDE.md: native_edited" in out
    assert "! .claude/rules/python.md: native_replaced" in out
    assert "! .cursor/rules/style.mdc: link_retargeted" in out
    assert "! docs/architecture: canonical_missing" in out
    assert "+ AGENTS.md" in out and "+ .grok/skills/deploy" in out
    assert "SUPERCTX.md" in read(project, "AGENTS.md")
    assert os.readlink(project / ".grok/skills/deploy") == LINKS[".grok/skills/deploy"]
    after = snapshot(project)
    assert after.pop("AGENTS.md") and after.pop(".grok/skills/deploy")
    assert after.pop(".grok/skills")[:2] == before.pop(".grok/skills")[:2]  # its mtime moves with the new link
    assert after == before  # everything else, conflicts included, is untouched
    assert read(project, ".ctx/SUPERCTX.md").count("Never use tabs.") == 0  # never imported from a native

    # 6. Recovery: move the edits to the canonical copies, restore from backup, then sync.
    with open(project / ".ctx/SUPERCTX.md", "a", encoding="utf-8") as f:
        f.write(read(project, "CLAUDE.md"))
    os.unlink(project / "CLAUDE.md")
    with open(project / ".ctx/rules/python.md", "a", encoding="utf-8") as f:
        f.write(read(project, ".claude/rules/python.md"))
    os.unlink(project / ".claude/rules/python.md")
    os.unlink(project / ".cursor/rules/style.mdc")
    shutil.copytree(project / ".ctx/sources/docs/architecture", project / ".ctx/architecture")
    code, out = cli(project, "sync")
    assert code == 0, out
    for rel in ("CLAUDE.md", ".claude/rules/python.md", ".cursor/rules/style.mdc"):
        assert f"+ {rel}" in out
    assert read(project, ".claude/rules/python.md").endswith("Prefer dataclasses.\nUse mypy.\n")
    assert read(project, "docs/architecture/adr-1.md") == FILES["docs/architecture/adr-1.md"]
    assert "Never use tabs." in read(project, ".ctx/SUPERCTX.md")

    # 7. Repeat sync is a no-op, and tool configuration was never touched.
    unchanged_sync(project)
    unchanged_sync(project)
    for rel, before in config.items():
        assert (snapshot(project / rel) if (project / rel).is_dir() else read(project, rel)) == before
    assert {r["type"] for r in manifest.load_v2(project)["resources"]} == \
        {"instructions", "rule", "skill", "reference", "planning"}


def test_upgrade_from_a_v01_workspace(tmp_path, legacy_scripts):  # noqa: F811
    project = build_v1(tmp_path / "repo", legacy_scripts)
    write(project, ".claude/rules/testing.md", "Run pytest before committing.\n")

    # The first sync migrates the manifest, keeps the imported context, and leaves
    # the pointers pointing at the hub (sync adds the current edit-policy wording).
    code, out = cli(project, "sync")
    assert code == 0 and "Migrated the manifest" in out, out
    hub = read(project, ".ctx/SUPERCTX.md")
    assert CLAUDE_ORIGINAL.strip() in hub and AGENTS_ORIGINAL.strip() in hub
    assert all("SUPERCTX.md" in read(project, rel) for rel in ("CLAUDE.md", "AGENTS.md"))
    assert (project / ".ctx/manifest.v1.toml").is_file()

    # Rules found in an existing workspace are candidates, connected with add.
    assert "- .claude/rules/testing.md" in out
    assert not os.path.islink(project / ".claude/rules/testing.md")
    code, out = cli(project, "add", ".claude/rules/testing.md")
    assert code == 0, out
    assert os.readlink(project / ".claude/rules/testing.md") == "../../.ctx/rules/testing.md"
    unchanged_sync(project)
