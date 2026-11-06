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
needs_grok = pytest.mark.skipif(shutil.which("grok") is None, reason="Grok Build is not installed")
needs_codex = pytest.mark.skipif(shutil.which("codex") is None, reason="Codex CLI is not installed")

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

# One skill package per tool folder, plus a control outside every tool's skill folders.
# Grok ships a skill named `review`, so these names are unique. Scripts are run by
# absolute path because Grok runs commands from the repository root.
SHARED_SKILL_MD = """---
name: {name}
description: Helper. Use when the user asks to run the {name} skill.
---

Run `bash <absolute path of this skill's folder>/scripts/run.sh` and report its exact output.
If you cannot run commands, report the exact text of scripts/run.sh instead.
Then read references/guide.md in this skill's folder and report the codeword it contains.
"""
SKILLS = {".claude/skills": ("sctx-review", "7731"), ".cursor/skills": ("sctx-lint", "5150"),
          ".grok/skills": ("sctx-deploy", "2207"), ".agents/skills": ("sctx-ship", "3141"),
          "misc/skills": ("sctx-fmt", "9090")}
# Grok trusts the folder for this run only (nothing is written to its trust store) and
# skips the user's own Claude and Cursor hooks and MCP servers.
GROK_ENV = {"GROK_FOLDER_TRUST": "0", "GROK_CLAUDE_HOOKS_ENABLED": "false", "GROK_CLAUDE_MCPS_ENABLED": "false",
            "GROK_CURSOR_HOOKS_ENABLED": "false", "GROK_CURSOR_MCPS_ENABLED": "false"}


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


@pytest.fixture(scope="module")
def shared_repo(tmp_path_factory) -> Path:
    """Instructions, a scoped Claude rule, and one skill per tool, adopted by sync."""
    root = tmp_path_factory.mktemp("real-agent-shared") / "repo"
    files = {
        "CLAUDE.md": "# Project\n\nThe hub codeword is HUB-7781.\n",
        "AGENTS.md": "# Agents\n\nThe agents codeword is AGENTS-3390.\n",
        "src/app.py": "print('hello')\n",
        "docs/notes.md": "# Notes\n\nNothing here.\n",
        ".claude/rules/python.md": RULE_MD,
    }
    for folder, (name, token) in SKILLS.items():
        files[f"{folder}/{name}/SKILL.md"] = SHARED_SKILL_MD.format(name=name)
        files[f"{folder}/{name}/scripts/run.sh"] = f"#!/bin/sh\necho SCRIPT-{token}\n"
        files[f"{folder}/{name}/references/guide.md"] = f"# Guide\n\nThe reference codeword is REF-{token}.\n"
    set_up(root, files, executable=tuple(f"{f}/{n}/scripts/run.sh" for f, (n, _) in SKILLS.items()))
    for folder in (".claude/skills", ".cursor/skills", ".grok/skills", ".agents/skills"):
        name = SKILLS[folder][0]
        assert os.readlink(root / folder / name) == f"../../.ctx/skills/{name}"
    assert not os.path.islink(root / "misc/skills/sctx-fmt")
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


def ask_cursor(root: Path, prompt: str, write: bool = False) -> str:
    """Run Cursor Agent and return its final answer; fail unless it succeeded.

    Read-only (ask mode) unless `write` is set, which uses its default agent mode.
    """
    mode = [] if write else ["--mode", "ask"]
    proc = subprocess.run(
        ["cursor-agent", "-p", prompt, "--model", CURSOR_MODEL, *mode, "--trust",
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


def ask_grok(root: Path, prompt: str, *allow: str) -> str:
    """Run Grok Build headless and return its answer; fail unless the run ended normally.

    Without allow rules the run is read-only (plan mode); allow rules approve only the
    commands they match.
    """
    mode = ["--permission-mode", "plan"] if not allow else [a for rule in allow for a in ("--allow", rule)]
    proc = subprocess.run(
        ["grok", "-p", prompt, "--output-format", "json", "--no-subagents", "--disable-web-search",
         "--max-turns", "10", *mode],
        cwd=root, capture_output=True, text=True, timeout=300, env={**os.environ, **GROK_ENV},
    )
    try:
        event = json.loads(proc.stdout)
    except ValueError:
        pytest.fail(f"grok produced no result (exit {proc.returncode}): {(proc.stdout + proc.stderr)[-400:]}")
    if proc.returncode != 0 or event.get("stopReason") != "end_turn":
        # Errors such as a usage limit arrive as {"type": "error", "message": ...}.
        detail = event.get("message") or event.get("text", "")
        pytest.fail(f"grok run failed (exit {proc.returncode}, {event.get('stopReason')}): {detail[-400:]}")
    return event.get("text", "")


def ask_codex(root: Path, prompt: str, write: bool = False) -> str:
    """Run Codex non-interactively and return its final answer; fail unless it succeeded.

    The sandbox is read-only unless `write` is set (workspace-write). The user's own
    config.toml is not loaded and the session is not saved.
    """
    out = root.parent / "codex-last-message.txt"
    out.unlink(missing_ok=True)
    proc = subprocess.run(
        ["codex", "exec", "--ephemeral", "--ignore-user-config", "-s", "workspace-write" if write else "read-only",
         "-C", str(root), "-o", str(out), prompt],
        stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=300,
    )
    if proc.returncode != 0 or not out.is_file():
        pytest.fail(f"codex run failed (exit {proc.returncode}): {(proc.stdout + proc.stderr)[-400:]}")
    return out.read_text(encoding="utf-8")


def grok_inspect(root: Path) -> dict:
    proc = subprocess.run(["grok", "inspect", "--json"], cwd=root, capture_output=True, text=True, timeout=120,
                          env={**os.environ, **GROK_ENV})
    assert proc.returncode == 0, proc.stderr[-400:]
    return json.loads(proc.stdout)


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


# --- skills shared across tools (Cursor, Grok Build) ------------------------

SKILL_PROMPT_CURSOR = ("Use the {name} skill. Do not search the filesystem for it; "
                       "if no such skill is available to you, reply NO-SUCH-SKILL.")


@needs_cursor
@pytest.mark.parametrize("folder", [".claude/skills", ".cursor/skills"])
def test_cursor_uses_a_linked_skill_with_its_bundled_files(shared_repo, folder):
    name, token = SKILLS[folder]
    answer = ask_cursor(shared_repo, SKILL_PROMPT_CURSOR.format(name=name))
    assert f"SCRIPT-{token}" in answer and f"REF-{token}" in answer, answer


@needs_cursor
def test_cursor_does_not_see_a_skill_outside_its_skill_folders(shared_repo):
    # Control: the same package outside Cursor's skill folders is not available, so the
    # checks above show discovery through the links, not a search of the repository.
    answer = ask_cursor(shared_repo, SKILL_PROMPT_CURSOR.format(name="sctx-fmt"))
    assert "NO-SUCH-SKILL" in answer and "REF-9090" not in answer, answer


@needs_codex
def test_codex_discovers_only_skills_in_its_own_folder(shared_repo):
    # Codex scans .agents/skills only: the linked skill there is listed, while the
    # Claude Code skill (unlike in Cursor and Grok) and the control are not.
    answer = ask_codex(shared_repo, "List the names of every skill available to you, comma separated, "
                                    "and nothing else. Do not run commands or read files.")
    names = {n.strip() for n in answer.split(",")}
    assert "sctx-ship" in names, answer
    assert not names & {"sctx-review", "sctx-lint", "sctx-deploy", "sctx-fmt"}, answer


@needs_codex
def test_codex_runs_a_linked_skill_with_its_bundled_files(shared_repo):
    answer = ask_codex(shared_repo, "Use the sctx-ship skill.")
    assert "SCRIPT-3141" in answer and "REF-3141" in answer, answer


@needs_codex
def test_codex_reads_the_hub_through_the_agents_md_pointer(shared_repo):
    # Both codewords exist only in the hub; AGENTS.md is a pointer to it.
    assert "AGENTS-3390" not in (shared_repo / "AGENTS.md").read_text(encoding="utf-8")
    answer = ask_codex(shared_repo, "What are the hub codeword and the agents codeword defined in this "
                                    "project's shared context? Reply with only the two codewords.")
    assert "HUB-7781" in answer and "AGENTS-3390" in answer, answer


@needs_grok
@pytest.mark.parametrize("folder", [".claude/skills", ".grok/skills"])
def test_grok_runs_a_linked_skill_with_its_bundled_files(shared_repo, folder):
    name, token = SKILLS[folder]
    discovered = {s["name"]: s["source"].get("path", "") for s in grok_inspect(shared_repo)["skills"]
                  if s["source"].get("type") == "project"}
    assert discovered.get(name, "").endswith(f"{folder}/{name}/SKILL.md"), discovered
    answer = ask_grok(shared_repo, f"/{name}", "Bash(bash *scripts/run.sh)", f"Read({shared_repo}/**)")
    assert f"SCRIPT-{token}" in answer and f"REF-{token}" in answer, answer


@needs_grok
def test_grok_loads_the_pointers_not_a_second_copy_of_the_hub(shared_repo):
    # Grok reads both CLAUDE.md and AGENTS.md. With SuperCtx they are short pointers, and
    # the hub itself is not among the instruction sources Grok loads, so its content
    # enters the context only when the model follows a pointer.
    sources = {os.path.relpath(p["path"], shared_repo.resolve()).lower(): p["sizeBytes"]
               for p in grok_inspect(shared_repo)["projectInstructions"]}
    assert {"claude.md", "agents.md"} <= set(sources), sources
    assert not any(".ctx/" in path for path in sources), sources
    assert sources["claude.md"] < 400 and sources["agents.md"] < 400, sources
    answer = ask_grok(shared_repo, "What are the hub codeword and the agents codeword defined in this "
                                   "project's shared context? Reply with only the two codewords.")
    assert "HUB-7781" in answer and "AGENTS-3390" in answer, answer


@needs_grok
def test_grok_applies_a_linked_claude_rule_to_a_matching_file(shared_repo):
    assert "RULE-PY-5521" in ask_grok(shared_repo, RULE_PROMPT.format(f="src/app.py"))


@needs_grok
def test_grok_ignores_a_claude_rule_scope(shared_repo):
    # Limited support, recorded in architecture/compatibility.md: Grok loads Claude rules
    # but not their `paths:` scope, so the rule also applies to a non-matching file (the
    # same happens without SuperCtx). If this starts failing, Grok honors the scope now.
    assert "RULE-PY-5521" in ask_grok(shared_repo, RULE_PROMPT.format(f="docs/notes.md"))


# --- planning and reference folders ------------------------------------------

PROGRESS = ".planning/2026-11-04-demo/progress.md"


@pytest.fixture(scope="module")
def folders_repo(tmp_path_factory) -> Path:
    """A .planning/ folder and a reference folder, connected with /superctx:add."""
    root = tmp_path_factory.mktemp("real-agent-folders") / "repo"
    set_up(root, {
        "CLAUDE.md": "# Project\n\nKeep answers short.\n",
        PROGRESS: "# Progress\n\n- step 1 done\n",
        "docs/architecture/adr-1.md": "# ADR 1\n\nThe decision codeword is ADR-6620.\n",
    })
    for folder in (".planning", "docs/architecture"):
        add = subprocess.run([sys.executable, "-m", "superctx", "add", folder, str(root)],
                             env={**os.environ, "PYTHONPATH": str(ROOT / "scripts")}, capture_output=True, text=True)
        assert add.returncode == 0, add.stdout + add.stderr
    assert os.readlink(root / ".planning") == ".ctx/planning"
    assert os.readlink(root / "docs/architecture") == "../.ctx/architecture"
    return root


def assert_progress_written_through_link(root: Path, line: str) -> None:
    assert os.path.islink(root / ".planning"), "the planning link was replaced"
    canonical = (root / ".ctx/planning/2026-11-04-demo/progress.md").read_text(encoding="utf-8")
    assert line in canonical and "- step 1 done" in canonical, canonical


UPDATE_PROMPT = (f"Append the line `{{line}}` at the end of {PROGRESS}, keeping its existing content. "
                 "Do not create or change any other file. Reply DONE when finished.")


@needs_claude
def test_claude_updates_progress_through_the_planning_link(folders_repo):
    line = "- step 2 done (claude)"
    ask_claude(folders_repo, UPDATE_PROMPT.format(line=line), "Read,Edit,Write")
    assert_progress_written_through_link(folders_repo, line)


@needs_claude
def test_claude_reads_a_reference_through_its_original_path(folders_repo):
    answer = ask_claude(folders_repo, "Read docs/architecture/adr-1.md and reply with only its decision codeword.",
                        "Read")
    assert "ADR-6620" in answer, answer


@needs_grok
def test_grok_updates_progress_through_the_planning_link(folders_repo):
    line = "- step 3 done (grok)"
    ask_grok(folders_repo, UPDATE_PROMPT.format(line=line),
             f"Read({folders_repo}/**)", f"Edit({folders_repo}/**)", f"Write({folders_repo}/**)")
    assert_progress_written_through_link(folders_repo, line)


@needs_cursor
def test_cursor_updates_progress_through_the_planning_link(folders_repo):
    line = "- step 4 done (cursor)"
    ask_cursor(folders_repo, UPDATE_PROMPT.format(line=line), write=True)
    assert_progress_written_through_link(folders_repo, line)


@needs_codex
def test_codex_updates_progress_through_the_planning_link(folders_repo):
    line = "- step 5 done (codex)"
    ask_codex(folders_repo, UPDATE_PROMPT.format(line=line), write=True)
    assert_progress_written_through_link(folders_repo, line)
