"""A missing backup is not shim damage.

Sync cannot recreate a missing backup, and the pointers themselves are intact, so state
detection, SessionStart, the edit guard and sync must not say the shims are broken or were
repaired. Each still names every missing backup. Real pointer or link damage keeps its
existing handling, and missing backups never cause writes themselves. All repositories are
synthetic.
"""
import os

import pytest

from superctx import core, shim, sync as sync_cmd
from superctx.__main__ import main
from superctx.status import detect_repo_state
from test_adoption import TOOL_CONFIG, adopted_by_an_earlier_version
from test_pointer_left_in_place import guard_edit, session_start, write
from test_v2_migration_safety import snapshot

POINTERS = ["CLAUDE.md", "AGENTS.md", "GEMINI.md", ".codex/AGENTS.md", ".github/copilot-instructions.md"]
BROKEN = "broken or missing"
REPAIR_OFFER = "Proceed with repair?"
REDIRECT = "is a generated SuperCtx shim, so I will update `.ctx/SUPERCTX.md` instead"
BACKUP_WARNING = "Backup missing for {}; original content cannot be recovered."


def managed(tmp_path, missing=POINTERS):
    project = tmp_path / "repo"
    for rel in POINTERS:
        write(project, rel, f"# {rel}\n\nOriginal.\n")
    write(project, ".claude/rules/python.md", "Use type hints.\n")
    result = sync_cmd.run(project)
    assert result["final_state"] == "healthy" and sorted(result["init_result"]["connected"]) == sorted(POINTERS)
    for rel in missing:
        (core.sources_dir(project) / rel).unlink()
    return project


def run_cli(capsys, project):
    capsys.readouterr()
    code = main(["sync", str(project)])
    return code, capsys.readouterr().out


# --- missing backups alone ----------------------------------------------------

def test_state_detection_names_every_missing_backup_without_calling_it_damage(tmp_path):
    project = managed(tmp_path)
    before = snapshot(project)
    state = detect_repo_state(project)
    assert state["state"] == "managed_healthy"
    assert state["recommended_action"] == "none" and state["recommended_action_mutates_files"] is False
    assert "missing_backup" in state["reasons"]
    assert state["missing_backups"] == sorted(POINTERS)
    assert snapshot(project) == before


def test_session_start_names_every_missing_backup_and_offers_no_repair(tmp_path):
    project = managed(tmp_path)
    out = session_start(project)
    assert BROKEN not in out and "offer to repair" not in out
    for rel in POINTERS:
        assert f"- {rel}\n" in out
    assert "sync does not recreate" in out


@pytest.mark.parametrize("rel", POINTERS)
def test_guard_redirects_an_intact_pointer_to_the_hub(tmp_path, rel):
    project = managed(tmp_path)
    code, msg = guard_edit(project, rel)
    assert code == 2 and REDIRECT in msg and REPAIR_OFFER not in msg


def test_sync_keeps_the_warnings_reports_no_repair_and_writes_nothing(tmp_path, capsys):
    project = managed(tmp_path)
    before = snapshot(project)
    result = sync_cmd.run(project)
    assert result["final_state"] == "healthy" and result["mutated"] is False
    assert result["warnings"] == [{"path": rel, "reason": "missing_backup"} for rel in sorted(POINTERS)]
    assert "repaired" not in result["message"]
    code, out = run_cli(capsys, project)
    assert code == 0 and "repaired" not in out.lower()
    for rel in POINTERS:
        assert BACKUP_WARNING.format(rel) in out
    assert snapshot(project) == before


def test_old_pointer_wording_is_still_refreshed_and_nothing_else_written(tmp_path):
    project = managed(tmp_path)
    old = shim.generated_pointers("CLAUDE.md")[2]  # the v0.2.5 wording
    assert old != shim.generated_pointers("CLAUDE.md")[0]
    (project / "CLAUDE.md").write_text(old, encoding="utf-8")
    before = snapshot(project)
    result = sync_cmd.run(project)
    after = snapshot(project)
    assert result["mutated"] is True and {"path": "CLAUDE.md", "reason": "missing_backup"} in result["warnings"]
    assert [k for k in sorted(set(before) | set(after)) if before.get(k) != after.get(k)] == ["CLAUDE.md"]
    assert not (core.sources_dir(project) / "CLAUDE.md").exists()


# --- combined findings --------------------------------------------------------

def test_with_untracked_candidates(tmp_path):
    project = managed(tmp_path, missing=["AGENTS.md"])
    os.unlink(project / ".github/copilot-instructions.md")
    sync_cmd.run(project)  # repair it so only the candidate and missing backup remain
    write(project, ".agy/ANTIGRAVITY.md", "# AGY\n\nLocal.\n")
    write(project, ".cursor/rules/style.mdc", "---\nalwaysApply: true\n---\nUse tabs.\n")
    before = snapshot(project)
    state = detect_repo_state(project)
    assert state["state"] == "managed_healthy" and state["missing_backups"] == ["AGENTS.md"]
    assert state["candidates"]
    out = session_start(project)
    assert "unconnected instruction files" in out and "- AGENTS.md\n" in out and BROKEN not in out
    code, msg = guard_edit(project, "AGENTS.md")
    assert code == 2 and REDIRECT in msg
    result = sync_cmd.run(project)
    assert result["candidates"] and {"path": "AGENTS.md", "reason": "missing_backup"} in result["warnings"]
    assert snapshot(project) == before


def test_with_adopted_tool_config(tmp_path, monkeypatch, capsys):
    project = managed(tmp_path, missing=["AGENTS.md"])
    rel = ".grok/config.toml"
    write(project, rel, TOOL_CONFIG[rel])
    adopted_by_an_earlier_version(project, rel, monkeypatch)
    before = snapshot(project)
    state = detect_repo_state(project)
    assert state["missing_backups"] == ["AGENTS.md"] and state["adopted_tool_config"] == [rel]
    out = session_start(project)
    assert BROKEN not in out and "registered instruction files are intact" in out
    assert f"- {rel}\n" in out and "- AGENTS.md\n" in out
    code, msg = guard_edit(project, "AGENTS.md")
    assert code == 2 and REDIRECT in msg and REPAIR_OFFER not in msg
    result = sync_cmd.run(project)
    assert {"path": rel, "reason": "tool_config_adopted"} in result["unresolved"]
    assert {"path": "AGENTS.md", "reason": "missing_backup"} in result["warnings"]
    assert result["repaired"] == [] and result["message"] == "SuperCtx found unresolved issues; nothing was repaired."
    code, out = run_cli(capsys, project)
    assert code == 1 and BACKUP_WARNING.format("AGENTS.md") in out and "Repaired" not in out
    assert snapshot(project) == before


@pytest.mark.parametrize("damage", ["missing_pointer", "edited_pointer", "missing_link"])
def test_with_real_damage_keeps_the_repair_handling(tmp_path, damage):
    project = managed(tmp_path, missing=["AGENTS.md"])
    if damage == "missing_pointer":
        os.unlink(project / "CLAUDE.md")
    elif damage == "edited_pointer":
        with open(project / "CLAUDE.md", "a", encoding="utf-8") as fh:
            fh.write("Local note.\n")
    else:
        os.unlink(project / ".claude/rules/python.md")
    state = detect_repo_state(project)
    assert state["state"] == "managed_needs_repair" and state["missing_backups"] == ["AGENTS.md"]
    out = session_start(project)
    assert BROKEN in out and "- AGENTS.md\n" in out
    code, msg = guard_edit(project, "AGENTS.md")
    assert code == 2 and REPAIR_OFFER in msg
    result = sync_cmd.run(project)
    assert {"path": "AGENTS.md", "reason": "missing_backup"} in result["warnings"]
    assert not (core.sources_dir(project) / "AGENTS.md").exists()
    if damage == "edited_pointer":
        assert result["unresolved"] == [{"path": "CLAUDE.md", "reason": "native_edited"}]
        assert result["repaired"] == [] and result["message"] == "SuperCtx found unresolved issues; nothing was repaired."
    else:
        assert result["repaired"] == ["CLAUDE.md" if damage == "missing_pointer" else ".claude/rules/python.md"]
        assert result["message"] == "SuperCtx shims repaired."
