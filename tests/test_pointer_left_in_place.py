"""How sync, SessionStart, and the edit guard report files left in place for pointer text.

A file holding SuperCtx pointer text cannot be adopted (#108), so no surface may offer to
connect it or set SuperCtx up for it; each says why it was left in place instead. Real
instruction files keep the normal adoption suggestion. Nothing here writes to the
repository. All repositories are synthetic.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

from superctx import shim, sync as sync_cmd
from superctx.__main__ import main
from superctx.guard import handle_pre_tool_use
from test_v2_migration_safety import snapshot

ROOT = Path(__file__).resolve().parents[1]
REL = ".codex/AGENTS.md"
VARIANTS = {
    "exact": (shim.generate_shim(REL, "plain-pointer"), "already_a_pointer"),
    "modified": (shim.generate_shim(REL, "plain-pointer") + "Also: prefer tabs.\n", "pointer_with_changes"),
    "truncated": (f"# SuperCtx\n{shim.WARNING_MARKER}\n", "pointer_with_changes"),
    "real": ("# AGENTS.md\n\nUse spaces.\n", None),
}
OFFERS = ("Offer to connect", "Offer to set up", "Proceed?")


def write(project: Path, rel: str, text: str) -> None:
    (project / rel).parent.mkdir(parents=True, exist_ok=True)
    (project / rel).write_text(text, encoding="utf-8")


def repo(tmp_path: Path, managed: bool, variant: str) -> Path:
    project = tmp_path / "repo"
    if managed:
        write(project, "CLAUDE.md", "# P\n\nUse tabs.\n")
        assert sync_cmd.run(project)["final_state"] == "healthy"
    write(project, REL, VARIANTS[variant][0])
    return project


def session_start(project: Path) -> str:
    env = dict(os.environ, CLAUDE_PLUGIN_ROOT=str(ROOT),
               PATH=str(Path(sys.executable).parent) + os.pathsep + os.environ.get("PATH", ""))
    out = subprocess.run(["bash", str(ROOT / "hooks" / "session-start")], cwd=project, env=env,
                         capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    return out.stdout


def guard_edit(project: Path, rel: str):
    return handle_pre_tool_use({"cwd": str(project), "tool_name": "Write",
                                "tool_input": {"file_path": str(project / rel)}})


def run_cli(capsys, project: Path) -> tuple[int, str]:
    capsys.readouterr()
    code = main(["sync", str(project)])
    return code, capsys.readouterr().out


@pytest.mark.parametrize("managed", [True, False], ids=["managed", "unmanaged"])
@pytest.mark.parametrize("variant", ["exact", "modified", "truncated"])
def test_every_surface_explains_a_pointer_text_file_instead_of_offering_it(tmp_path, capsys, managed, variant):
    project = repo(tmp_path, managed, variant)
    reason = VARIANTS[variant][1]
    before = snapshot(project)

    code, out = run_cli(capsys, project)
    assert f"- {REL} (instructions): {reason}" in out, out
    assert "Untracked candidates" not in out and not any(o in out for o in OFFERS), out
    assert code == (0 if managed else 1)

    hook = session_start(project)
    assert REL in hook and reason in hook and "cannot tell what" in hook, hook
    assert "Do not offer to connect" in hook, hook
    assert "setup opportunity" not in hook and "unconnected instruction files" not in hook, hook

    code, msg = guard_edit(project, REL)
    assert code == 2 and f"`{REL}`" in msg and reason in msg and "left it in place" in msg, msg
    assert not any(o in msg for o in OFFERS) and "connect this file" not in msg, msg

    assert snapshot(project) == before  # contents and manifest metadata untouched


@pytest.mark.parametrize("managed", [True, False], ids=["managed", "unmanaged"])
def test_every_surface_keeps_offering_to_adopt_a_real_instruction_file(tmp_path, capsys, managed):
    project = repo(tmp_path, managed, "real")

    if managed:
        before = snapshot(project)
        code, out = run_cli(capsys, project)
        assert code == 0 and f"Untracked candidates:\n- {REL}" in out and "Offer to connect" in out, out
        assert "Left in place" not in out, out
        hook = session_start(project)
        assert "unconnected instruction files" in hook and f"- {REL}" in hook, hook
        code, msg = guard_edit(project, REL)
        assert code == 2 and "not yet tracked by SuperCtx" in msg, msg
        assert snapshot(project) == before
    else:
        hook = session_start(project)
        assert "setup opportunity" in hook and f"- {REL}" in hook, hook
        code, msg = guard_edit(project, REL)
        assert code == 2 and "set up one shared context hub" in msg and f"- {REL}" in msg, msg
        code, out = run_cli(capsys, project)  # first-time setup adopts it as before
        assert code == 0 and f"Connected:\n- {REL}" in out, out
    assert "cannot tell what" not in hook and "left it in place" not in msg


def test_mixed_files_get_the_offer_and_the_explanation_separately(tmp_path, capsys):
    project = repo(tmp_path, True, "exact")
    write(project, "GEMINI.md", "# Gemini\n\nUse Gemini.\n")
    before = snapshot(project)

    code, out = run_cli(capsys, project)
    assert code == 0, out
    assert f"- {REL} (instructions): already_a_pointer" in out
    assert "Untracked candidates:\n- GEMINI.md\n" in out and REL not in out.split("Untracked candidates:")[1], out

    hook = session_start(project)
    offer, _, note = hook.partition("Do not offer to connect")
    assert "- GEMINI.md" in offer and REL not in offer.split("unconnected instruction files")[1].split("\n\n")[0], hook
    assert REL in hook and "already_a_pointer" in hook, hook

    assert "not yet tracked" in guard_edit(project, "GEMINI.md")[1]
    assert "left it in place" in guard_edit(project, REL)[1]
    assert snapshot(project) == before


ALIAS, TARGET = "GEMINI.md", "docs/orphan.md"
ALIAS_CONTENT = {
    # Judged against the target's own path, as add does.
    "exact": (shim.generate_shim(TARGET, "plain-pointer"), "already_a_pointer"),
    "written_for_alias": (shim.generate_shim(ALIAS, "plain-pointer"), "pointer_with_changes"),
}


def aliased_repo(tmp_path: Path, managed: bool, content: str) -> Path:
    project = tmp_path / "repo"
    if managed:
        write(project, "CLAUDE.md", "# P\n\nUse tabs.\n")
        assert sync_cmd.run(project)["final_state"] == "healthy"
    write(project, TARGET, content)
    os.symlink(TARGET, project / ALIAS)
    return project


@pytest.mark.parametrize("managed", [True, False], ids=["managed", "unmanaged"])
@pytest.mark.parametrize("kind", sorted(ALIAS_CONTENT))
def test_an_alias_to_pointer_text_inside_the_repo_is_explained_on_every_surface(tmp_path, capsys, managed, kind):
    from superctx import add as add_cmd
    content, reason = ALIAS_CONTENT[kind]
    project = aliased_repo(tmp_path, managed, content)
    before = snapshot(project)  # the link, its target, and the manifest

    code, out = run_cli(capsys, project)
    assert f"- {ALIAS} (instructions): {reason}" in out, out
    assert "Untracked candidates" not in out and not any(o in out for o in OFFERS), out
    assert code == (0 if managed else 1)

    hook = session_start(project)
    assert f"- {ALIAS} ({reason})" in hook and "Do not offer to connect" in hook, hook
    assert "setup opportunity" not in hook and "unconnected instruction files" not in hook, hook

    for rel in (ALIAS, TARGET):  # an edit through the alias or to its target lands in the same file
        code, msg = guard_edit(project, rel)
        assert code == 2 and "left it in place" in msg and reason in msg, (rel, msg)
        assert f"`{rel}`" in msg and not any(o in msg for o in OFFERS), msg

    if managed:
        with pytest.raises(add_cmd.AddError, match=reason):
            add_cmd.run(project, ALIAS)

    assert snapshot(project) == before
    assert os.readlink(project / ALIAS) == TARGET


@pytest.mark.parametrize("managed", [True, False], ids=["managed", "unmanaged"])
def test_an_alias_leaving_the_repo_is_not_read(tmp_path, managed):
    from superctx import status
    outside = tmp_path / "outside.md"
    outside.write_text(shim.generate_shim(ALIAS, "plain-pointer"), encoding="utf-8")
    project = tmp_path / "repo"
    if managed:
        write(project, "CLAUDE.md", "# P\n\nUse tabs.\n")
        assert sync_cmd.run(project)["final_state"] == "healthy"
    project.mkdir(exist_ok=True)
    os.symlink(outside, project / ALIAS)

    state = status.detect_repo_state(project)

    assert "left_in_place" not in state  # the target outside the repository is never opened
    assert ALIAS in state["candidates"]


def test_the_guard_names_the_alias_when_the_project_is_reached_through_a_link(tmp_path):
    # Like macOS /var -> /private/var: the project path the agent uses is not the resolved one.
    content, reason = ALIAS_CONTENT["exact"]
    project = aliased_repo(tmp_path, True, content)
    via = tmp_path / "via"
    os.symlink(project, via)

    code, msg = handle_pre_tool_use({"cwd": str(via), "tool_name": "Write",
                                     "tool_input": {"file_path": str(via / ALIAS)}})

    assert code == 2 and f"`{ALIAS}`" in msg and reason in msg, msg
