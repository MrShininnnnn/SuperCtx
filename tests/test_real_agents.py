"""Real-tool checks for adopted rules and skills (opt-in: SUPERCTX_REAL_AGENTS=1).

Each check sets up a repository with the real `superctx sync`, so the rule and skill
reach Claude Code through the relative symlinks SuperCtx publishes, then asks Claude
Code (non-interactive, project settings only) to use them. Results are recorded in
architecture/compatibility.md.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.skipif(
    os.environ.get("SUPERCTX_REAL_AGENTS") != "1" or shutil.which("claude") is None,
    reason="set SUPERCTX_REAL_AGENTS=1 with Claude Code installed to run real-agent checks",
)

SKILL_MD = """---
name: review
description: Review helper. Use when the user asks to run the review skill.
---

Run `bash scripts/run.sh` from this skill's directory and report its exact output.
Then read `references/guide.md` in this skill's directory and report the codeword it contains.
"""
RULE_MD = '---\npaths:\n  - "src/**/*.py"\n---\n\nThe Python codeword for this project is RULE-PY-5521.\n'
RULE_PROMPT = (
    "Read the file {f}. Do not read, list, or search any other file. "
    "Then answer: what is the Python codeword defined by this project's rules? "
    "Reply with only the codeword, or NONE if no rule gave you one."
)


@pytest.fixture(scope="module")
def adopted_repo(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("real-agent") / "repo"
    files = {
        "CLAUDE.md": "# Project\n\nKeep answers short.\n",
        "src/app.py": "print('hello')\n",
        "docs/notes.md": "# Notes\n\nNothing here.\n",
        ".claude/rules/python.md": RULE_MD,
        ".claude/skills/review/SKILL.md": SKILL_MD,
        ".claude/skills/review/scripts/run.sh": "#!/bin/sh\necho SCRIPT-TOKEN-7731\n",
        ".claude/skills/review/references/guide.md": "# Guide\n\nThe reference codeword is REF-TOKEN-4410.\n",
    }
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    (root / ".claude/skills/review/scripts/run.sh").chmod(0o755)
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    sync = subprocess.run(
        [sys.executable, "-m", "superctx", "sync", str(root)],
        env={**os.environ, "PYTHONPATH": str(ROOT / "scripts")}, capture_output=True, text=True,
    )
    assert sync.returncode == 0, sync.stdout + sync.stderr
    assert os.readlink(root / ".claude/rules/python.md") == "../../.ctx/rules/python.md"
    assert os.readlink(root / ".claude/skills/review") == "../../.ctx/skills/review"
    return root


def ask_claude(root: Path, prompt: str, tools: str) -> str:
    """Run Claude Code and return its final answer; fail unless the run succeeded."""
    proc = subprocess.run(
        ["claude", "-p", prompt, "--model", "haiku", "--setting-sources", "project",
         "--output-format", "stream-json", "--verbose", "--allowedTools", tools,
         "--no-session-persistence", "--max-turns", "8"],
        cwd=root, capture_output=True, text=True, timeout=300,
    )
    for line in proc.stdout.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get("type") == "result":
            if proc.returncode != 0 or event.get("is_error") or event.get("subtype") != "success":
                pytest.fail(f"claude run failed (exit {proc.returncode}, {event.get('subtype')}): "
                            f"{event.get('result', '')[:400]}")
            return event.get("result", "")
    pytest.fail(f"claude produced no result (exit {proc.returncode}): {proc.stderr[-400:]}")


def test_linked_skill_loads_with_its_script_and_reference(adopted_repo):
    result = ask_claude(adopted_repo, "/review", "Skill,Read,Bash")
    assert "SCRIPT-TOKEN-7731" in result and "REF-TOKEN-4410" in result, result


def test_linked_scoped_rule_applies_to_a_matching_file(adopted_repo):
    assert "RULE-PY-5521" in ask_claude(adopted_repo, RULE_PROMPT.format(f="src/app.py"), "Read")


def test_linked_scoped_rule_stays_inactive_for_a_non_matching_file(adopted_repo):
    # Require the requested answer, not merely the codeword's absence.
    answer = ask_claude(adopted_repo, RULE_PROMPT.format(f="docs/notes.md"), "Read")
    assert answer.strip().strip(".").upper() == "NONE", answer
