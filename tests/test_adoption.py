"""One-step adoption: instruction pointers plus linked rules and skills."""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from superctx import add as add_cmd, adopt, core, init as init_cmd, manifest, shim, sync as sync_cmd
from test_v2_migration_safety import snapshot

CLAUDE = "# Claude\n\nRun the tests before committing.\n"
RULE = '---\npaths:\n  - "src/**/*.py"\n---\n\nUse type hints in Python files.\n'
SKILL_MD = "---\nname: review\ndescription: Review a diff\n---\n\nRun scripts/run.sh, then read references/guide.md.\n"
RUN_SH = "#!/bin/sh\necho review\n"
GUIDE = "# Guide\n\nCheck naming.\n"

ORIGINALS = {
    "CLAUDE.md": CLAUDE,
    ".claude/rules/python.md": RULE,
    ".claude/skills/review/SKILL.md": SKILL_MD,
    ".claude/skills/review/scripts/run.sh": RUN_SH,
    ".claude/skills/review/references/guide.md": GUIDE,
}


def write(project: Path, rel: str, text: str, mode: int | None = None) -> None:
    path = project / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    if mode is not None:
        path.chmod(mode)


def happy_repo(tmp_path: Path) -> Path:
    project = tmp_path / "repo"
    for rel, text in ORIGINALS.items():
        write(project, rel, text, mode=0o755 if rel.endswith(".sh") else None)
    return project


# --- happy path -------------------------------------------------------------

def test_one_sync_adopts_instructions_rules_and_skills(tmp_path):
    project = happy_repo(tmp_path)

    result = sync_cmd.run(project)

    assert result["mode"] == "init" and result["final_state"] == "healthy"
    init_res = result["init_result"]
    assert init_res["connected"] == ["CLAUDE.md"]
    assert sorted(init_res["linked"]) == [".claude/rules/python.md", ".claude/skills/review"]
    assert init_res["left_in_place"] == []

    assert shim.is_shim_file(project / "CLAUDE.md")
    assert os.readlink(project / ".claude/rules/python.md") == "../../.ctx/rules/python.md"
    assert os.readlink(project / ".claude/skills/review") == "../../.ctx/skills/review"
    # Tools read the original bytes through the links; executable bits survive.
    for rel, text in ORIGINALS.items():
        if rel != "CLAUDE.md":
            assert (project / rel).read_text(encoding="utf-8") == text
            assert (project / rel.replace(".claude/", ".ctx/", 1)).read_text(encoding="utf-8") == text
        assert (core.sources_dir(project) / rel).read_text(encoding="utf-8") == text
    assert os.access(project / ".claude/skills/review/scripts/run.sh", os.X_OK)
    assert stat.S_IMODE((core.sources_dir(project) / ".claude/skills/review/scripts/run.sh").stat().st_mode) & 0o111

    doc = manifest.load_v2(project)
    assert {(n["path"], n["mode"], n["resource"]) for n in doc["natives"]} == {
        ("CLAUDE.md", "pointer", "instructions"),
        (".claude/rules/python.md", "link", "rule-python"),
        (".claude/skills/review", "link", "skill-review"),
    }
    assert {(r["id"], r["type"], r["canonical"]) for r in doc["resources"]} >= {
        ("rule-python", "rule", ".ctx/rules/python.md"),
        ("skill-review", "skill", ".ctx/skills/review"),
    }


def test_editing_through_a_link_edits_the_canonical_resource(tmp_path):
    project = happy_repo(tmp_path)
    sync_cmd.run(project)

    (project / ".claude/skills/review/SKILL.md").write_text(SKILL_MD + "\nNew step.\n", encoding="utf-8")

    assert (project / ".ctx/skills/review/SKILL.md").read_text(encoding="utf-8").endswith("New step.\n")
    assert sync_cmd.run(project)["mutated"] is False


def test_second_sync_on_an_unchanged_repo_makes_no_changes(tmp_path):
    project = happy_repo(tmp_path)
    sync_cmd.run(project)
    before = snapshot(project)

    result = sync_cmd.run(project)

    assert result["mode"] == "healthy" and result["mutated"] is False
    assert snapshot(project) == before


def test_canonical_paths_keep_native_depth_so_relative_references_resolve_the_same(tmp_path):
    project = happy_repo(tmp_path)
    sync_cmd.run(project)
    for nat in manifest.load_v2(project)["natives"]:
        if nat["mode"] == "link":
            canonical = next(r["canonical"] for r in manifest.load_v2(project)["resources"] if r["id"] == nat["resource"])
            assert len(Path(canonical).parts) == len(Path(nat["path"]).parts)


# --- edit preservation ------------------------------------------------------

@pytest.mark.parametrize("with_backup", [True, False])
def test_an_edited_pointer_stays_at_its_path_and_is_reported(tmp_path, with_backup):
    project = happy_repo(tmp_path)
    sync_cmd.run(project)
    if not with_backup:
        (core.sources_dir(project) / "CLAUDE.md").unlink()
    (project / "CLAUDE.md").write_text("A hand edit to the pointer.\n", encoding="utf-8")
    before = snapshot(project)

    result = sync_cmd.run(project)

    assert result["final_state"] == "needs_attention"
    assert {"path": "CLAUDE.md", "reason": "native_edited"} in result["unresolved"]
    assert (project / "CLAUDE.md").read_text(encoding="utf-8") == "A hand edit to the pointer.\n"
    assert snapshot(project) == before


def test_an_edited_pointer_created_without_a_backup_is_preserved(tmp_path):
    project = happy_repo(tmp_path)
    sync_cmd.run(project)
    add_cmd.run(project, "GEMINI.md", create_if_missing=True)
    (project / "GEMINI.md").write_text("Gemini notes typed into the pointer.\n", encoding="utf-8")
    before = snapshot(project)

    result = sync_cmd.run(project)

    assert {"path": "GEMINI.md", "reason": "native_edited"} in result["unresolved"]
    assert not (core.sources_dir(project) / "GEMINI.md").exists()
    assert snapshot(project) == before


def test_a_line_appended_to_a_pointer_is_preserved_and_reported(tmp_path):
    project = happy_repo(tmp_path)
    sync_cmd.run(project)
    edited = (project / "CLAUDE.md").read_bytes() + b"extra\n"
    (project / "CLAUDE.md").write_bytes(edited)
    before = snapshot(project)

    result = sync_cmd.run(project)

    assert result["final_state"] == "needs_attention"
    assert {"path": "CLAUDE.md", "reason": "native_edited"} in result["unresolved"]
    assert (project / "CLAUDE.md").read_bytes() == edited
    assert snapshot(project) == before


def test_restoring_the_original_after_setup_is_preserved_and_reported(tmp_path):
    project = happy_repo(tmp_path)
    sync_cmd.run(project)
    (project / "CLAUDE.md").write_text(CLAUDE, encoding="utf-8")  # equal to the backup
    before = snapshot(project)

    result = sync_cmd.run(project)

    assert {"path": "CLAUDE.md", "reason": "native_edited"} in result["unresolved"]
    assert (project / "CLAUDE.md").read_text(encoding="utf-8") == CLAUDE
    assert snapshot(project) == before


def test_a_handwritten_file_replacing_a_published_link_is_never_adopted(tmp_path):
    project = happy_repo(tmp_path)
    sync_cmd.run(project)
    (project / ".ctx/rules/python.md").unlink()
    (project / ".claude/rules/python.md").unlink()
    write(project, ".claude/rules/python.md", "A handwritten replacement rule.\n")
    before = snapshot(project)

    result = sync_cmd.run(project)

    assert {"path": ".claude/rules/python.md", "reason": "canonical_missing"} in result["unresolved"]
    assert (project / ".claude/rules/python.md").read_text(encoding="utf-8") == "A handwritten replacement rule.\n"
    assert not (project / ".ctx/rules/python.md").exists()
    assert snapshot(project) == before


def test_setup_records_publication_and_a_crash_before_recording_is_resumed(tmp_path, monkeypatch):
    project = happy_repo(tmp_path)
    monkeypatch.setattr(manifest, "mark_published", lambda *a, **k: (_ for _ in ()).throw(Crash()))
    with pytest.raises(Crash):
        init_cmd.run(project)
    monkeypatch.undo()
    assert {n["path"]: n.get("published", True) for n in manifest.load_v2(project)["natives"]} == {
        "CLAUDE.md": False, ".claude/rules/python.md": False, ".claude/skills/review": False,
    }

    result = sync_cmd.run(project)

    assert result["final_state"] == "healthy" and result["unresolved"] == []
    assert all(n.get("published", True) for n in manifest.load_v2(project)["natives"])
    assert sync_cmd.run(project)["mutated"] is False


def test_a_missing_pointer_is_recreated(tmp_path):
    project = happy_repo(tmp_path)
    sync_cmd.run(project)
    (project / "CLAUDE.md").unlink()

    result = sync_cmd.run(project)

    assert result["repaired"] == ["CLAUDE.md"] and result["final_state"] == "healthy"
    assert shim.is_shim_file(project / "CLAUDE.md")


# --- link states ------------------------------------------------------------

def test_a_deleted_link_is_recreated(tmp_path):
    project = happy_repo(tmp_path)
    sync_cmd.run(project)
    (project / ".claude/skills/review").unlink()

    result = sync_cmd.run(project)

    assert ".claude/skills/review" in result["repaired"] and result["final_state"] == "healthy"
    assert os.readlink(project / ".claude/skills/review") == "../../.ctx/skills/review"


def _retarget(p: Path) -> None:
    (p / ".claude/skills/review").unlink()
    (p / "elsewhere").mkdir()
    (p / ".claude/skills/review").symlink_to("../../elsewhere")


def _replace_with_copy(p: Path) -> None:
    (p / ".claude/rules/python.md").unlink()
    write(p, ".claude/rules/python.md", RULE + "\nLocal copy edit.\n")


def _delete_canonical(p: Path) -> None:
    (p / ".ctx/rules/python.md").unlink()


@pytest.mark.parametrize("damage,path,reason", [
    (_retarget, ".claude/skills/review", "link_retargeted"),
    (_replace_with_copy, ".claude/rules/python.md", "native_replaced"),
    (_delete_canonical, ".claude/rules/python.md", "canonical_missing"),
])
def test_link_conflicts_are_reported_without_writing(tmp_path, damage, path, reason):
    project = happy_repo(tmp_path)
    sync_cmd.run(project)
    damage(project)
    before = snapshot(project)

    result = sync_cmd.run(project)

    assert result["final_state"] == "needs_attention"
    assert {"path": path, "reason": reason} in result["unresolved"]
    assert snapshot(project) == before


# --- left in place ----------------------------------------------------------

def test_incompatible_resources_are_left_in_place_with_a_reason(tmp_path):
    project = happy_repo(tmp_path)
    write(project, ".cursor/rules/style.mdc", "---\nglobs: src/**\n---\nStyle.\n")
    write(project, ".claude/skills/notes/README.md", "no SKILL.md here\n")
    write(project, ".claude/skills/linky/SKILL.md", SKILL_MD.replace("review", "linky"))
    (project / ".claude/skills/linky/shared").symlink_to("../../../src")
    write(project, "shared/rule.md", RULE)
    (project / ".claude/rules/shared.md").symlink_to("../../shared/rule.md")
    write(project, ".claude/rules/a/b.md", RULE)
    write(project, ".claude/rules/a-b.md", RULE)
    natives_before = {rel: snapshot(project / rel) if (project / rel).is_dir() else (project / rel).read_bytes()
                      for rel in (".cursor/rules", ".claude/skills/notes", ".claude/rules/a/b.md", ".claude/rules/a-b.md")}

    result = sync_cmd.run(project)

    left = {item["path"]: item["reason"] for item in result["init_result"]["left_in_place"]}
    assert left == {
        ".cursor/rules/style.mdc": "not_verified",
        ".claude/skills/notes": "no_skill_md",
        ".claude/skills/linky": "contains_symlink",
        ".claude/rules/shared.md": "already_a_symlink",
        ".claude/rules/a/b.md": "name_collision",
        ".claude/rules/a-b.md": "name_collision",
    }
    assert sorted(result["init_result"]["linked"]) == [".claude/rules/python.md", ".claude/skills/review"]
    for rel, before in natives_before.items():
        after = snapshot(project / rel) if (project / rel).is_dir() else (project / rel).read_bytes()
        assert after == before
    assert os.readlink(project / ".claude/rules/shared.md") == "../../shared/rule.md"
    assert sync_cmd.run(project)["mutated"] is False


def test_a_resource_folder_reached_through_a_symlink_is_left_in_place(tmp_path):
    project = tmp_path / "repo"
    write(project, "CLAUDE.md", CLAUDE)
    write(tmp_path / "shared-skills", "review/SKILL.md", SKILL_MD)
    (project / ".claude").mkdir()
    (project / ".claude/skills").symlink_to(tmp_path / "shared-skills")

    result = sync_cmd.run(project)

    assert result["init_result"]["linked"] == []
    assert {"path": ".claude/skills/review", "type": "skill", "reason": "unsafe_path"} in result["init_result"]["left_in_place"]
    assert (tmp_path / "shared-skills/review/SKILL.md").read_text(encoding="utf-8") == SKILL_MD


def test_a_repo_with_only_a_skill_is_set_up(tmp_path):
    project = tmp_path / "repo"
    write(project, ".claude/skills/review/SKILL.md", SKILL_MD)

    result = sync_cmd.run(project)

    assert result["mode"] == "init"
    assert result["init_result"]["linked"] == [".claude/skills/review"]


def test_ctx_directories_are_created_only_as_needed(tmp_path):
    project = tmp_path / "repo"
    write(project, "CLAUDE.md", CLAUDE)

    sync_cmd.run(project)

    assert not (core.ctx_dir(project) / "rules").exists()
    assert not (core.ctx_dir(project) / "skills").exists()


# --- partial failure --------------------------------------------------------

class Crash(Exception):
    pass


def test_a_crash_while_staging_leaves_the_repo_untouched_and_a_rerun_succeeds(tmp_path, monkeypatch):
    project = happy_repo(tmp_path)
    before = snapshot(project)

    def crash(*args, **kwargs):
        raise Crash()

    monkeypatch.setattr(init_cmd, "_install_staged_ctx", crash)
    with pytest.raises(Crash):
        init_cmd.run(project)
    monkeypatch.undo()

    assert snapshot(project) == before
    assert sync_cmd.run(project)["final_state"] == "healthy"
    assert [p.name for p in project.iterdir() if p.name.startswith(".superctx-staging")] == []


@pytest.mark.parametrize("stage", ["before-publish", "after-move-before-link"])
def test_sync_resumes_an_interrupted_setup(tmp_path, monkeypatch, stage):
    (tmp_path / "reference").mkdir()
    reference = happy_repo(tmp_path / "reference")
    sync_cmd.run(reference)
    expected = snapshot(reference, times=False)

    project = happy_repo(tmp_path)
    if stage == "before-publish":
        monkeypatch.setattr(init_cmd, "_publish", lambda *a, **k: (_ for _ in ()).throw(Crash()))
    else:
        monkeypatch.setattr(adopt, "_symlink", lambda *a, **k: (_ for _ in ()).throw(Crash()))
    with pytest.raises(Crash):
        init_cmd.run(project)
    monkeypatch.undo()

    result = sync_cmd.run(project)

    assert result["final_state"] == "healthy", result
    assert snapshot(project, times=False) == expected
    assert all(n.get("published", True) for n in manifest.load_v2(project)["natives"])


# --- add --------------------------------------------------------------------

def test_add_adopts_a_new_skill_in_an_existing_workspace(tmp_path):
    project = happy_repo(tmp_path)
    sync_cmd.run(project)
    write(project, ".claude/skills/deploy/SKILL.md", SKILL_MD.replace("review", "deploy"))
    assert ".claude/skills/deploy" in sync_cmd.run(project)["candidates"]

    res = add_cmd.run(project, ".claude/skills/deploy")

    assert res.status == "added"
    assert os.readlink(project / ".claude/skills/deploy") == "../../.ctx/skills/deploy"
    assert (core.sources_dir(project) / ".claude/skills/deploy/SKILL.md").is_file()
    assert sync_cmd.run(project)["mutated"] is False


def test_add_refuses_a_skill_whose_canonical_path_is_taken(tmp_path):
    project = happy_repo(tmp_path)
    sync_cmd.run(project)
    write(project, ".ctx/skills/deploy/SKILL.md", "someone else's\n")
    write(project, ".claude/skills/deploy/SKILL.md", SKILL_MD.replace("review", "deploy"))
    before = snapshot(project)

    with pytest.raises(add_cmd.AddError, match="canonical_exists"):
        add_cmd.run(project, ".claude/skills/deploy")
    assert snapshot(project) == before


def test_add_backs_up_an_untracked_pointer_with_extra_lines_instead_of_overwriting(tmp_path):
    project = happy_repo(tmp_path)
    sync_cmd.run(project)
    edited = shim.generated_pointers("GEMINI.md")[0] + "Gemini-only note.\n"
    write(project, "GEMINI.md", edited)

    add_cmd.run(project, "GEMINI.md")

    assert (core.sources_dir(project) / "GEMINI.md").read_text(encoding="utf-8") == edited
    assert "Gemini-only note." in core.hub_path(project).read_text(encoding="utf-8")
