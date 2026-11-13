"""Adopting a file that already holds SuperCtx pointer text.

Pointer text says nothing about what the file held before or whether a backup of that
exists, so first-time sync and add refuse it and leave everything unchanged. Real
instructions are adopted as before. All repositories here are synthetic.
"""
from pathlib import Path

import pytest

from superctx import add as add_cmd, core, shim, sync as sync_cmd
from superctx.__main__ import main
from test_v2_migration_safety import snapshot

REL = ".codex/AGENTS.md"
CURRENT = shim.generate_shim(REL, "plain-pointer")
NO_ORIGINAL = shim.generate_shim(REL, "plain-pointer", backup_required=False)
V01 = shim.generated_pointers(REL)[1]  # v0.1.x form, without the edit-policy line
TRUNCATED = CURRENT.split("Expected original backup")[0].rstrip() + "\n"
EDITED = CURRENT + "Also: prefer tabs.\n"

POINTERS = {
    "current": (CURRENT, "already_a_pointer"),
    "no_original_wording": (NO_ORIGINAL, "already_a_pointer"),
    "v0_1": (V01, "already_a_pointer"),
    "edited": (EDITED, "pointer_with_changes"),
    "truncated": (TRUNCATED, "pointer_with_changes"),
}
REAL = "# AGENTS.md\n\nUse spaces.\n"


def write(project: Path, rel: str, text: str) -> None:
    (project / rel).parent.mkdir(parents=True, exist_ok=True)
    (project / rel).write_text(text, encoding="utf-8")


def managed_repo(tmp_path: Path) -> Path:
    project = tmp_path / "repo"
    write(project, "CLAUDE.md", "# P\n\nUse tabs.\n")
    assert sync_cmd.run(project)["final_state"] == "healthy"
    return project


def assert_no_pointer_text_in_hub(project: Path) -> None:
    assert shim.WARNING_MARKER not in core.hub_path(project).read_text(encoding="utf-8")


@pytest.mark.parametrize("name", sorted(POINTERS))
def test_first_sync_refuses_a_file_holding_pointer_text_and_writes_nothing(tmp_path, name):
    text, reason = POINTERS[name]
    project = tmp_path / "repo"
    write(project, REL, text)
    before = snapshot(project)

    result = sync_cmd.run(project)

    assert result["final_state"] == "needs_attention"
    init_res = result["init_result"]
    assert not init_res["created"]
    assert {"path": REL, "type": "instructions", "reason": reason} in init_res["left_in_place"]
    assert snapshot(project) == before  # no .ctx/, no backup, no hub, file unchanged


@pytest.mark.parametrize("name", sorted(POINTERS))
def test_add_refuses_a_file_holding_pointer_text_and_writes_nothing(tmp_path, name):
    text, reason = POINTERS[name]
    project = managed_repo(tmp_path)
    write(project, REL, text)
    before = snapshot(project)

    with pytest.raises(add_cmd.AddError, match=reason):
        add_cmd.run(project, REL)

    assert snapshot(project) == before  # manifest, hub, backups and the file itself
    assert not (core.sources_dir(project) / REL).exists()
    assert_no_pointer_text_in_hub(project)


def test_refusal_explains_that_the_original_cannot_be_established(tmp_path, capsys):
    project = managed_repo(tmp_path)
    write(project, REL, CURRENT)
    capsys.readouterr()

    assert main(["add", REL, str(project)]) == 1
    err = capsys.readouterr().err
    assert "already_a_pointer" in err and "cannot tell" in err and "changed nothing" in err


@pytest.mark.parametrize("how", ["first sync", "add"])
def test_real_instructions_are_still_backed_up_and_imported(tmp_path, how):
    if how == "first sync":
        project = tmp_path / "repo"
        write(project, REL, REAL)
        result = sync_cmd.run(project)
        assert result["final_state"] == "healthy"
        assert f".ctx/sources/{REL}" in result["init_result"]["backups"]
    else:
        project = managed_repo(tmp_path)
        write(project, REL, REAL)
        message = add_cmd.run(project, REL).message
        assert "Original content backed up" in message

    assert (core.sources_dir(project) / REL).read_text(encoding="utf-8") == REAL
    assert "Use spaces." in core.hub_path(project).read_text(encoding="utf-8")
    assert shim.is_generated_pointer_file(project, REL)
    assert_no_pointer_text_in_hub(project)


def test_add_claims_a_backup_only_when_one_was_made(tmp_path):
    project = managed_repo(tmp_path)

    message = add_cmd.run(project, "GEMINI.md", create_if_missing=True).message

    assert "backed up" not in message
    assert not (core.sources_dir(project) / "GEMINI.md").exists()


def test_mixed_first_sync_adopts_real_files_and_reports_skipped_ones(tmp_path, capsys):
    project = tmp_path / "repo"
    write(project, "CLAUDE.md", "# P\n\nUse tabs.\n")
    write(project, REL, CURRENT)
    write(project, "GEMINI.md", shim.generate_shim("GEMINI.md", "plain-pointer") + "Local note.\n")
    skipped = {REL: (project / REL).read_bytes(), "GEMINI.md": (project / "GEMINI.md").read_bytes()}

    assert main(["sync", str(project)]) == 0
    out = capsys.readouterr().out

    assert "Connected:\n- CLAUDE.md" in out
    assert f"- {REL} (instructions): already_a_pointer" in out
    assert "- GEMINI.md (instructions): pointer_with_changes" in out
    assert (core.sources_dir(project) / "CLAUDE.md").is_file()
    for rel, data in skipped.items():
        assert (project / rel).read_bytes() == data
        assert not (core.sources_dir(project) / rel).exists()
    assert_no_pointer_text_in_hub(project)
    tracked = (project / ".ctx/superctx.toml").read_text(encoding="utf-8")
    assert REL not in tracked and "GEMINI.md" not in tracked

    # Later syncs leave the skipped files alone.
    before = snapshot(project)
    assert sync_cmd.run(project)["mutated"] is False
    assert snapshot(project) == before
