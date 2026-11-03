"""Real-tool checks for adopted rules and skills (opt-in: SUPERCTX_REAL_AGENTS=1).

Each check sets up a repository with the real `superctx sync`, so rules and skills
reach the tool through the relative symlinks SuperCtx publishes, then asks the tool
(non-interactive, read-only where it allows) to use them. Results are recorded in
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
    os.environ.get("SUPERCTX_REAL_AGENTS") != "1",
    reason="set SUPERCTX_REAL_AGENTS=1 to run real-agent checks",
)
needs_claude = pytest.mark.skipif(shutil.which("claude") is None, reason="Claude Code is not installed")
# Cursor's CLI installs as both `agent` and `cursor-agent`; the second name is unambiguous.
needs_cursor = pytest.mark.skipif(shutil.which("cursor-agent") is None, reason="Cursor Agent CLI is not installed")

SKILL_MD = """---
name: review
description: Review helper. Use when the user asks to run the review skill.
---

Run `bash scripts/run.sh` from this skill's directory and report its exact output.
Then read `references/guide.md` in this skill's directory and report the codeword it contains.
"""
RULE_MD = '---\npaths:\n  - "src/**/*.py"\n---\n\nThe Python codeword for this project is RULE-PY-5521.\n'
CURSOR_RULE_MDC = (
    "---\ndescription:\nglobs: src/**/*.py\nalwaysApply: false\n---\n\n"
    "The Python codeword for this project is RULE-PY-5521.\n"
)
RULE_PROMPT = (
    "Read the file {f}. Do not read, list, or search any other file. "
    "Then answer: what is the Python codeword defined by this project's rules? "
    "Reply with only the codeword, or NONE if no rule gave you one."
)
# Cursor's free plan allows only Grok and Auto; pin one so results are repeatable.
CURSOR_MODEL = "grok-4.7-medium"


def set_up(root: Path, files: dict[str, str], executable: tuple[str, ...] = ()) -> None:
    """Write files, then adopt them with the real `superctx sync`."""
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    for rel in executable:
        (root / rel).chmod(0o755)
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    sync = subprocess.run(
        [sys.executable, "-m", "superctx", "sync", str(root)],
        env={**os.environ, "PYTHONPATH": str(ROOT / "scripts")}, capture_output=True, text=True,
    )
    assert sync.returncode == 0, sync.stdout + sync.stderr


@pytest.fixture(scope="module")
def adopted_repo(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("real-agent") / "repo"
    set_up(root, {
        "CLAUDE.md": "# Project\n\nKeep answers short.\n",
        "src/app.py": "print('hello')\n",
        "docs/notes.md": "# Notes\n\nNothing here.\n",
        ".claude/rules/python.md": RULE_MD,
        ".claude/skills/review/SKILL.md": SKILL_MD,
        ".claude/skills/review/scripts/run.sh": "#!/bin/sh\necho SCRIPT-TOKEN-7731\n",
        ".claude/skills/review/references/guide.md": "# Guide\n\nThe reference codeword is REF-TOKEN-4410.\n",
    }, executable=(".claude/skills/review/scripts/run.sh",))
    assert os.readlink(root / ".claude/rules/python.md") == "../../.ctx/rules/python.md"
    assert os.readlink(root / ".claude/skills/review") == "../../.ctx/skills/review"
    return root


@pytest.fixture(scope="module")
def cursor_repo(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("real-agent-cursor") / "repo"
    set_up(root, {
        "src/app.py": "print('hello')\n",
        "docs/notes.md": "# Notes\n\nNothing here.\n",
        ".cursor/rules/python.mdc": CURSOR_RULE_MDC,
    })
    assert os.readlink(root / ".cursor/rules/python.mdc") == "../../.ctx/cursor-rules/python.mdc"
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


def ask_cursor(root: Path, prompt: str) -> str:
    """Run Cursor Agent read-only (ask mode) and return its final answer; fail unless it succeeded."""
    proc = subprocess.run(
        ["cursor-agent", "-p", prompt, "--model", CURSOR_MODEL, "--mode", "ask", "--trust",
         "--output-format", "json"],
        cwd=root, capture_output=True, text=True, timeout=300,
    )
    # Errors such as a model the plan does not include are printed as plain text, with exit 0.
    try:
        event = json.loads(proc.stdout)
    except ValueError:
        pytest.fail(f"cursor-agent produced no result (exit {proc.returncode}): "
                    f"{(proc.stdout + proc.stderr)[-400:]}")
    if proc.returncode != 0 or event.get("is_error") or event.get("subtype") != "success":
        pytest.fail(f"cursor-agent run failed (exit {proc.returncode}, {event.get('subtype')}): "
                    f"{str(event.get('result', ''))[:400]}")
    return event.get("result", "")


def is_none(answer: str) -> bool:
    # Cursor's result joins the agent's narration and its final reply ("...file.NONE"),
    # so require the reply to end with NONE and contain no codeword.
    return answer.strip().strip(".").upper().endswith("NONE") and "RULE-PY" not in answer


@needs_claude
def test_linked_skill_loads_with_its_script_and_reference(adopted_repo):
    result = ask_claude(adopted_repo, "/review", "Skill,Read,Bash")
    assert "SCRIPT-TOKEN-7731" in result and "REF-TOKEN-4410" in result, result


@needs_claude
def test_linked_scoped_rule_applies_to_a_matching_file(adopted_repo):
    assert "RULE-PY-5521" in ask_claude(adopted_repo, RULE_PROMPT.format(f="src/app.py"), "Read")


@needs_claude
def test_linked_scoped_rule_stays_inactive_for_a_non_matching_file(adopted_repo):
    # Require the requested answer, not merely the codeword's absence.
    answer = ask_claude(adopted_repo, RULE_PROMPT.format(f="docs/notes.md"), "Read")
    assert answer.strip().strip(".").upper() == "NONE", answer


@needs_cursor
def test_cursor_linked_scoped_rule_applies_to_a_matching_file(cursor_repo):
    answer = ask_cursor(cursor_repo, RULE_PROMPT.format(f="src/app.py"))
    assert "RULE-PY-5521" in answer, answer


@needs_cursor
def test_cursor_linked_scoped_rule_stays_inactive_for_a_non_matching_file(cursor_repo):
    answer = ask_cursor(cursor_repo, RULE_PROMPT.format(f="docs/notes.md"))
    assert is_none(answer), answer
