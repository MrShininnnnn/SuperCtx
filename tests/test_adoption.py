"""One-step adoption: instruction pointers plus linked rules and skills."""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest

from superctx import add as add_cmd, adopt, core, init as init_cmd, manifest, registry, shim, sync as sync_cmd
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


def _interrupt_before_publish(project: Path, monkeypatch) -> None:
    monkeypatch.setattr(init_cmd, "_publish", lambda *a, **k: (_ for _ in ()).throw(Crash()))
    with pytest.raises(Crash):
        init_cmd.run(project)
    monkeypatch.undo()


def _edit_rule(p: Path) -> None:
    (p / ".claude/rules/python.md").write_text(RULE + "\nEdited after the interruption.\n", encoding="utf-8")


def _edit_skill_file(p: Path) -> None:
    (p / ".claude/skills/review/references/guide.md").write_text(GUIDE + "Edited.\n", encoding="utf-8")


def _add_skill_file(p: Path) -> None:
    write(p, ".claude/skills/review/references/extra.md", "New file.\n")


def _chmod_skill_script(p: Path) -> None:
    (p / ".claude/skills/review/scripts/run.sh").chmod(0o644)


@pytest.mark.parametrize("edit,path", [
    (_edit_rule, ".claude/rules/python.md"),
    (_edit_skill_file, ".claude/skills/review"),
    (_add_skill_file, ".claude/skills/review"),
    (_chmod_skill_script, ".claude/skills/review"),
])
def test_an_interrupted_setup_does_not_adopt_a_native_edited_since_backup(tmp_path, monkeypatch, edit, path):
    project = happy_repo(tmp_path)
    _interrupt_before_publish(project, monkeypatch)
    edit(project)
    native_before = _native_snapshot(project, path)

    result = sync_cmd.run(project)

    assert {"path": path, "reason": "native_edited"} in result["unresolved"]
    assert _native_snapshot(project, path) == native_before
    canonical = path.replace(".claude/", ".ctx/", 1)
    assert not os.path.lexists(project / canonical)
    # Unchanged resources from the same interrupted setup still resume.
    assert shim.is_generated_pointer_file(project, "CLAUDE.md")
    other = ({".claude/rules/python.md", ".claude/skills/review"} - {path}).pop()
    assert (project / other).is_symlink()


def _native_snapshot(project: Path, rel: str):
    path = project / rel
    if path.is_dir() and not path.is_symlink():
        return snapshot(path)
    return (path.is_symlink(), stat.S_IMODE(os.lstat(path).st_mode), path.read_bytes(), os.lstat(path).st_mtime_ns)


def test_a_scan_error_while_comparing_with_the_backup_is_not_a_match(tmp_path, monkeypatch):
    project = happy_repo(tmp_path)
    (project / ".claude/skills/review/assets").mkdir()
    _interrupt_before_publish(project, monkeypatch)
    write(project, ".claude/skills/review/assets/edit", "added after the backup\n")
    unreadable = str(project / ".claude/skills/review/assets")
    real_scandir = os.scandir

    def scandir(path="."):
        if os.fspath(path) == unreadable:
            raise PermissionError(13, "Permission denied", unreadable)
        return real_scandir(path)

    monkeypatch.setattr(os, "scandir", scandir)
    result = sync_cmd.run(project)
    monkeypatch.undo()

    assert {"path": ".claude/skills/review", "reason": "native_edited"} in result["unresolved"]
    native = project / ".claude/skills/review"
    assert native.is_dir() and not native.is_symlink()
    assert (native / "assets/edit").read_text(encoding="utf-8") == "added after the backup\n"
    assert not os.path.lexists(project / ".ctx/skills/review")


def test_an_interrupted_setup_with_a_missing_backup_is_not_resumed(tmp_path, monkeypatch):
    import shutil
    project = happy_repo(tmp_path)
    _interrupt_before_publish(project, monkeypatch)
    shutil.rmtree(core.sources_dir(project) / ".claude/skills/review")
    native_before = _native_snapshot(project, ".claude/skills/review")

    result = sync_cmd.run(project)

    assert {"path": ".claude/skills/review", "reason": "native_edited"} in result["unresolved"]
    assert _native_snapshot(project, ".claude/skills/review") == native_before
    assert not os.path.lexists(project / ".ctx/skills/review")


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

def test_incompatible_resources_are_left_in_place_with_a_reason(tmp_path, monkeypatch):
    # A rule folder whose link behavior has not been verified with the real tool.
    convs = registry.load_conventions()
    for conv in convs:
        if conv["path"] == ".cursor/rules/":
            del conv["publish"]
    monkeypatch.setattr(registry, "load_conventions", lambda path=None: convs)
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


# --- Cursor rules -----------------------------------------------------------

CURSOR_RULE = "---\ndescription:\nglobs: src/**/*.py\nalwaysApply: false\n---\n\nSee [the guide](../../docs/guide.md).\n"


def test_cursor_rules_are_linked_byte_for_byte_from_their_own_canonical_folder(tmp_path):
    project = happy_repo(tmp_path)
    write(project, ".cursor/rules/python.mdc", CURSOR_RULE)
    write(project, ".cursor/rules/frontend/components.mdc", CURSOR_RULE)

    result = sync_cmd.run(project)

    assert result["final_state"] == "healthy"
    assert sorted(result["init_result"]["linked"]) == [
        ".claude/rules/python.md", ".claude/skills/review",
        ".cursor/rules/frontend/components.mdc", ".cursor/rules/python.mdc",
    ]
    assert os.readlink(project / ".cursor/rules/python.mdc") == "../../.ctx/cursor-rules/python.mdc"
    assert os.readlink(project / ".cursor/rules/frontend/components.mdc") == "../../../.ctx/cursor-rules/frontend/components.mdc"
    for rel in (".cursor/rules/python.mdc", ".cursor/rules/frontend/components.mdc"):
        # Activation metadata and relative references are untouched: no conversion happens.
        assert (project / rel).read_text(encoding="utf-8") == CURSOR_RULE
        assert (core.sources_dir(project) / rel).read_text(encoding="utf-8") == CURSOR_RULE
    doc = manifest.load_v2(project)
    assert {(r["id"], r["canonical"]) for r in doc["resources"] if r["type"] == "rule"} == {
        ("rule-python", ".ctx/rules/python.md"),
        ("cursor-rule-python", ".ctx/cursor-rules/python.mdc"),
        ("cursor-rule-frontend-components", ".ctx/cursor-rules/frontend/components.mdc"),
    }
    assert sync_cmd.run(project)["mutated"] is False


def test_a_reference_that_reaches_outside_the_rules_folder_resolves_from_both_locations(tmp_path):
    project = happy_repo(tmp_path)
    write(project, ".cursor/rules/python.mdc", CURSOR_RULE)
    write(project, ".cursor/rules/team.mdc",
          "[a](<../../docs/team guide.md>) [b](../../docs/team%20guide.md) [c][ref]\n\n[ref]: ../../docs/guide.md\n")
    write(project, "docs/guide.md", "# Guide\n")
    write(project, "docs/team guide.md", "# Team guide\n")

    result = sync_cmd.run(project)

    assert {".cursor/rules/python.mdc", ".cursor/rules/team.mdc"} <= set(result["init_result"]["linked"])
    for folder in (".cursor/rules", ".ctx/cursor-rules"):
        for ref in ("../../docs/guide.md", "../../docs/team guide.md"):
            assert (project / folder / ref).resolve() == (project / ref[6:]).resolve()


@pytest.mark.parametrize("native, reference, sibling", [
    (".cursor/rules/review.mdc", "[guide](guide.md)", ".cursor/rules/guide.md"),
    (".cursor/rules/review.mdc", "![diagram](./img/flow.png)", ".cursor/rules/img/flow.png"),
    (".claude/rules/review.md", "See [the guide](guide.md#setup).", ".claude/rules/guide.md"),
    (".claude/rules/review.md", "@guide.md", ".claude/rules/guide.md"),
    (".cursor/rules/review.mdc", "[guide](<team guide.md>)", ".cursor/rules/team guide.md"),
    (".cursor/rules/review.mdc", "[guide](team%20guide.md)", ".cursor/rules/team guide.md"),
    (".cursor/rules/review.mdc", "[guide][ref]\n\n[ref]: guide.md", ".cursor/rules/guide.md"),
    (".cursor/rules/review.mdc", "[guide][ref]\n\n  [ref]: <team guide.md> \"Team\"", ".cursor/rules/team guide.md"),
    (".cursor/rules/review.mdc", "[guide](guide(v2).md \"Guide\")", ".cursor/rules/guide(v2).md"),
    (".cursor/rules/review.mdc", "[guide](team\\_guide.md)", ".cursor/rules/team_guide.md"),
    (".cursor/rules/review.mdc", '<a href="guide.md">guide</a>', ".cursor/rules/guide.md"),
    (".cursor/rules/review.mdc", "<img src='img/flow.png'>", ".cursor/rules/img/flow.png"),
    (".claude/rules/review.md", "@team\\ guide.txt", ".claude/rules/team guide.txt"),
    (".cursor/rules/review.mdc", "[guide][ref]\n\n[ref]:\n    guide.md", ".cursor/rules/guide.md"),
    (".cursor/rules/review.mdc", "<a href=guide.md>guide</a>", ".cursor/rules/guide.md"),
    (".cursor/rules/review.mdc", '<a HREF="guide.md">Guide</a>', ".cursor/rules/guide.md"),
    (".cursor/rules/review.mdc", "[guide](guide.md?view=raw)", ".cursor/rules/guide.md"),
    (".cursor/rules/review.mdc", "[guide](guide.md?view=raw#setup)", ".cursor/rules/guide.md"),
    (".cursor/rules/review.mdc", '<a href="guide&#46;md">Guide</a>', ".cursor/rules/guide.md"),
    (".cursor/rules/review.mdc", "[guide][ref]\n\n[ref]: <\tguide.md >", ".cursor/rules/guide.md"),
    # One fixture per spelling the guard tries: as written, exact CommonMark decoding,
    # HTML decoding (backslash literal), and every backslash escape removed.
    (".cursor/rules/review.mdc", "[guide](a\\_b&#46;md)", ".cursor/rules/a\\_b&#46;md"),
    (".cursor/rules/review.mdc", "[guide](a\\&#46;b&#46;md)", ".cursor/rules/a&#46;b.md"),
    (".cursor/rules/review.mdc", '<a href="a\\_b&#46;md">Guide</a>', ".cursor/rules/a\\_b.md"),
])
def test_a_rule_whose_local_reference_would_break_is_left_in_place(tmp_path, native, reference, sibling):
    project = happy_repo(tmp_path)
    write(project, native, f"Follow this.\n\n{reference}\n")
    write(project, sibling, "# Guide\n")
    before = (project / native).read_bytes()

    result = sync_cmd.run(project)

    assert {"path": native, "type": "rule", "reason": "breaks_reference"} in result["init_result"]["left_in_place"]
    assert native not in result["init_result"]["linked"]
    assert not os.path.islink(project / native) and (project / native).read_bytes() == before
    assert not os.path.lexists(core.sources_dir(project) / native)
    assert result["final_state"] == "healthy"
    # The rest of the one-step setup still happens, and the rule stays reported.
    assert ".claude/rules/python.md" in result["init_result"]["linked"]
    assert {"path": native, "type": "rule", "reason": "breaks_reference"} in sync_cmd.run(project)["left_in_place"]


@pytest.mark.parametrize("reference", [
    "[guide](<team guide.md",             # angle bracket never closed
    "[guide](a(b(c)).md)",                # parentheses nested deeper than the guard parses
    "[guide][ref]\n\n[ref]:\n\n guide.md",  # definition whose destination is not found
    "<a href=>guide</a>",                 # attribute with no value
    "[guide]( <unclosed)",                # empty destination without its closing )
    "<a href=gui\"de.md>guide</a>",       # unquoted value that ends partway
])
def test_a_rule_with_a_reference_the_guard_cannot_resolve_is_left_in_place(tmp_path, reference):
    # Uncertainty preserves the rule: a recognized link or import whose complete
    # destination cannot be determined could be broken by the move.
    project = happy_repo(tmp_path)
    write(project, ".cursor/rules/review.mdc", f"Follow this.\n\n{reference}\n")
    before = (project / ".cursor/rules/review.mdc").read_bytes()

    result = sync_cmd.run(project)

    assert {"path": ".cursor/rules/review.mdc", "type": "rule", "reason": "unclear_reference"} in \
        result["init_result"]["left_in_place"]
    assert not os.path.islink(project / ".cursor/rules/review.mdc")
    assert (project / ".cursor/rules/review.mdc").read_bytes() == before
    assert ".claude/rules/python.md" in result["init_result"]["linked"]


LONG_NAME = "a" * 180 + ".md"


@pytest.mark.parametrize("reference", [
    "[guide](" + "%61" * 180 + ".md)",              # 543 characters encoded
    "[guide](<" + "%61" * 180 + ".md>)",
    "[guide](<" + "dir one/" * 70 + "guide.md>)",   # spaces allowed inside <...>
    '<a href="' + "&#97;" * 180 + '.md">guide</a>',
    '<a href="' + "dir one/" * 70 + 'guide.md">guide</a>',  # spaces allowed inside quotes
])
def test_a_reference_longer_than_the_scan_window_is_unclear(tmp_path, reference):
    project = happy_repo(tmp_path)
    write(project, ".cursor/rules/review.mdc", f"Follow this.\n\n{reference}\n")
    write(project, f".cursor/rules/{LONG_NAME}", "# Guide\n")
    before = (project / ".cursor/rules/review.mdc").read_bytes()

    result = sync_cmd.run(project)

    assert {"path": ".cursor/rules/review.mdc", "type": "rule", "reason": "unclear_reference"} in \
        result["init_result"]["left_in_place"]
    assert not os.path.islink(project / ".cursor/rules/review.mdc")
    assert (project / ".cursor/rules/review.mdc").read_bytes() == before
    assert not os.path.lexists(core.sources_dir(project) / ".cursor/rules/review.mdc")
    assert not os.path.lexists(project / ".ctx/cursor-rules/review.mdc")
    assert ".claude/rules/python.md" in result["init_result"]["linked"]


def test_long_lines_of_ordinary_text_do_not_block_adoption(tmp_path):
    # Unwrapped paragraphs run far past the scan window; only a destination that could
    # still be open at the window's end is uncertain.
    project = happy_repo(tmp_path)
    prose = "Keep functions small and name things clearly. " * 40
    text = (f"{prose}See [the guide](../../docs/guide.md) when x < y. {prose}\n"
            f"{prose}Use @pytest.fixture and <https://example.com> too. {prose}\n")
    write(project, ".cursor/rules/python.mdc", text)
    write(project, "docs/guide.md", "# Guide\n")

    result = sync_cmd.run(project)

    assert ".cursor/rules/python.mdc" in result["init_result"]["linked"]


@pytest.mark.skipif(os.name == "nt" or os.geteuid() == 0, reason="needs POSIX permissions as non-root")
def test_a_rule_that_cannot_be_read_is_treated_as_unclear(tmp_path):
    project = tmp_path / "repo"
    write(project, ".cursor/rules/review.mdc", "[guide](guide.md)\n")
    (project / ".cursor/rules/review.mdc").chmod(0)
    try:
        assert adopt.reference_problem(project, ".cursor/rules/review.mdc", ".ctx/cursor-rules/review.mdc") \
            == "unclear_reference"
    finally:
        (project / ".cursor/rules/review.mdc").chmod(0o644)


def test_add_refuses_a_rule_whose_local_reference_would_break(tmp_path):
    project = happy_repo(tmp_path)
    sync_cmd.run(project)
    write(project, ".cursor/rules/review.mdc", "[guide](guide.md)\n")
    write(project, ".cursor/rules/guide.md", "# Guide\n")
    before = snapshot(project)

    with pytest.raises(add_cmd.AddError, match="breaks_reference"):
        add_cmd.run(project, ".cursor/rules/review.mdc")
    assert snapshot(project) == before


def test_references_that_cannot_break_do_not_block_adoption(tmp_path):
    project = happy_repo(tmp_path)
    text = (
        "[site](https://example.com/guide.md) [mail](mailto:a@b.c) [top](#rules) [abs](/docs/guide.md)\n"
        "[missing](nothing-here.md) Use @pytest.fixture and email me at dev@example.com.\n"
    )
    write(project, ".cursor/rules/python.mdc", text)
    write(project, ".claude/rules/style.md", text)

    result = sync_cmd.run(project)

    assert {".cursor/rules/python.mdc", ".claude/rules/style.md"} <= set(result["init_result"]["linked"])


def test_every_published_link_is_relative_and_resolves_inside_the_repository(tmp_path):
    project = happy_repo(tmp_path)
    write(project, ".cursor/rules/python.mdc", CURSOR_RULE)
    write(project, ".cursor/rules/frontend/components.mdc", CURSOR_RULE)
    sync_cmd.run(project)

    links = [n["path"] for n in manifest.load_v2(project)["natives"] if n["mode"] == "link"]
    assert len(links) == 4
    root = project.resolve()
    for rel in links:
        target = os.readlink(project / rel)
        assert not os.path.isabs(target)
        resolved = (project / rel).resolve()
        assert resolved.is_relative_to(root / ".ctx") and resolved.exists()


def test_a_md_file_in_cursor_rules_is_not_treated_as_a_rule(tmp_path):
    # Cursor ignores .md files in .cursor/rules, so they are not rules SuperCtx manages.
    project = happy_repo(tmp_path)
    write(project, ".cursor/rules/notes.md", "Not a Cursor rule.\n")

    result = sync_cmd.run(project)

    assert ".cursor/rules/notes.md" not in result["init_result"]["linked"]
    assert all(i["path"] != ".cursor/rules/notes.md" for i in result["init_result"]["left_in_place"])
    assert not os.path.islink(project / ".cursor/rules/notes.md")
    assert (project / ".cursor/rules/notes.md").read_text(encoding="utf-8") == "Not a Cursor rule.\n"


def test_add_adopts_a_new_cursor_rule_in_an_existing_workspace(tmp_path):
    project = happy_repo(tmp_path)
    sync_cmd.run(project)
    write(project, ".cursor/rules/python.mdc", CURSOR_RULE)
    assert ".cursor/rules/python.mdc" in sync_cmd.run(project)["candidates"]

    assert add_cmd.run(project, ".cursor/rules/python.mdc").status == "added"
    assert os.readlink(project / ".cursor/rules/python.mdc") == "../../.ctx/cursor-rules/python.mdc"
    assert sync_cmd.run(project)["mutated"] is False


# --- skills from every verified tool -----------------------------------------

def write_skill(project: Path, folder: str, name: str, token: str) -> None:
    write(project, f"{folder}/{name}/SKILL.md", SKILL_MD.replace("review", name) + token + "\n")
    write(project, f"{folder}/{name}/scripts/run.sh", RUN_SH, mode=0o755)
    write(project, f"{folder}/{name}/references/guide.md", GUIDE)


def test_cursor_and_grok_skills_are_linked_from_the_shared_skills_folder(tmp_path):
    project = happy_repo(tmp_path)
    write_skill(project, ".cursor/skills", "lint", "cursor")
    write_skill(project, ".grok/skills", "deploy", "grok")
    native_before = {rel: snapshot(project / rel) for rel in (".cursor/skills/lint", ".grok/skills/deploy")}

    result = sync_cmd.run(project)

    assert result["final_state"] == "healthy"
    assert {".cursor/skills/lint", ".grok/skills/deploy"} <= set(result["init_result"]["linked"])
    assert os.readlink(project / ".cursor/skills/lint") == "../../.ctx/skills/lint"
    assert os.readlink(project / ".grok/skills/deploy") == "../../.ctx/skills/deploy"
    for rel, before in native_before.items():
        assert snapshot(project / rel) == before  # read through the link: same bytes and modes
        assert snapshot(core.sources_dir(project) / rel) == before
    assert os.access(project / ".grok/skills/deploy/scripts/run.sh", os.X_OK)
    doc = manifest.load_v2(project)
    assert {(r["id"], r["canonical"]) for r in doc["resources"] if r["type"] == "skill"} == {
        ("skill-review", ".ctx/skills/review"), ("skill-lint", ".ctx/skills/lint"), ("skill-deploy", ".ctx/skills/deploy"),
    }
    assert sync_cmd.run(project)["mutated"] is False


@pytest.mark.parametrize("same_content", [False, True])
def test_skills_sharing_a_name_across_tools_are_both_preserved_and_reported(tmp_path, same_content):
    project = happy_repo(tmp_path)
    write_skill(project, ".claude/skills", "deploy", "claude")
    write_skill(project, ".grok/skills", "deploy", "claude" if same_content else "grok")
    before = {rel: snapshot(project / rel) for rel in (".claude/skills/deploy", ".grok/skills/deploy")}

    result = sync_cmd.run(project)

    left = {i["path"]: i["reason"] for i in result["init_result"]["left_in_place"]}
    assert left[".claude/skills/deploy"] == left[".grok/skills/deploy"] == "name_collision"
    for rel, snap in before.items():
        assert not os.path.islink(project / rel) and snapshot(project / rel) == snap
    assert not os.path.lexists(project / ".ctx/skills/deploy")
    assert ".claude/skills/review" in result["init_result"]["linked"]


def test_codex_skills_are_left_in_place_until_verified(tmp_path):
    project = happy_repo(tmp_path)
    write_skill(project, ".agents/skills", "release", "codex")
    before = snapshot(project / ".agents")

    result = sync_cmd.run(project)

    assert {"path": ".agents/skills/release", "type": "skill", "reason": "not_verified"} in \
        result["init_result"]["left_in_place"]
    assert snapshot(project / ".agents") == before


def test_grok_configuration_is_never_adopted(tmp_path):
    from test_v2_migration_safety import GROK_FILES
    project = happy_repo(tmp_path)
    for rel, text in GROK_FILES.items():
        write(project, rel, text)
    others = {rel for rel in GROK_FILES if not rel.startswith(".grok/skills/")}
    before = {rel: (project / rel).read_bytes() for rel in others}

    result = sync_cmd.run(project)

    assert ".grok/skills/deploy" in result["init_result"]["linked"]
    linked_or_left = set(result["init_result"]["linked"]) | {i["path"] for i in result["init_result"]["left_in_place"]}
    for rel, data in before.items():
        assert not any(p == rel or rel.startswith(p + "/") for p in linked_or_left), rel
        assert not os.path.islink(project / rel) and (project / rel).read_bytes() == data
        assert not os.path.lexists(core.sources_dir(project) / rel)


# A skill moves as a whole, so references between its own files keep working; a
# reference that leaves the skill folder would resolve from .ctx/skills/ instead.

@pytest.mark.parametrize("rel, text, outside", [
    ("references/more.md", "See [the other skill](../../lint/SKILL.md).\n", ".claude/skills/lint/SKILL.md"),
    ("SKILL.md", SKILL_MD + "Also read [shared notes](../shared.md).\n", ".claude/skills/shared.md"),
    ("scripts/run.sh", "#!/bin/sh\n. ../../shared/lib.sh\n", ".claude/skills/shared/lib.sh"),
    # Scripts usually run from the skill's root, so their paths are relative to it.
    ("scripts/run.py", "open('../../settings.json')\n", ".claude/settings.json"),
    # Equivalent spellings of a parent path: leading ./ segments, a folder before the
    # ../, and a prefix the guard cannot resolve ($0's folder is the script's folder).
    ("scripts/run.sh", "#!/bin/sh\ncat ./../shared.txt\n", ".claude/skills/shared.txt"),
    ("scripts/run.sh", "#!/bin/sh\ncat ././../shared.txt\n", ".claude/skills/shared.txt"),
    ("scripts/run.sh", "#!/bin/sh\ncat scripts/../../shared.txt\n", ".claude/skills/shared.txt"),
    ("scripts/run.sh", '#!/bin/sh\ncat "$(dirname "$0")/../../shared.txt"\n', ".claude/skills/shared.txt"),
    ("scripts/sub/run.sh", '#!/bin/sh\ncat "$(dirname "$0")/../../../shared.txt"\n', ".claude/skills/shared.txt"),
])
def test_a_skill_referencing_a_file_outside_its_folder_is_left_in_place(tmp_path, rel, text, outside):
    project = happy_repo(tmp_path)
    write(project, f".claude/skills/review/{rel}", text)
    write(project, outside, "shared\n")
    before = snapshot(project / ".claude/skills/review")

    result = sync_cmd.run(project)

    assert {"path": ".claude/skills/review", "type": "skill", "reason": "breaks_reference"} in \
        result["init_result"]["left_in_place"]
    assert not os.path.islink(project / ".claude/skills/review")
    assert snapshot(project / ".claude/skills/review") == before
    assert not os.path.lexists(project / ".ctx/skills/review")


def test_add_refuses_a_skill_whose_script_reaches_outside_it(tmp_path):
    project = happy_repo(tmp_path)
    sync_cmd.run(project)
    write_skill(project, ".claude/skills", "deploy", "claude")
    write(project, ".claude/skills/deploy/scripts/run.sh", "#!/bin/sh\ncat ./../shared.txt\n", mode=0o755)
    write(project, ".claude/skills/shared.txt", "shared\n")
    before = snapshot(project)

    with pytest.raises(add_cmd.AddError, match="breaks_reference"):
        add_cmd.run(project, ".claude/skills/deploy")
    assert snapshot(project) == before
    assert not os.path.lexists(project / ".ctx/skills/deploy")
    assert not os.path.lexists(core.sources_dir(project) / ".claude/skills/deploy")


def test_references_inside_a_skill_or_beyond_its_tool_folder_do_not_block_adoption(tmp_path):
    project = happy_repo(tmp_path)
    write(project, ".claude/skills/review/references/more.md",
          "Back to [the skill](../SKILL.md), the [guide](guide.md), and [docs](../../../../docs/guide.md).\n")
    # Parent paths that stay inside the skill, from its root or from the script's folder.
    write(project, ".claude/skills/review/scripts/run.sh",
          '#!/bin/sh\ncat ../references/guide.md ./scripts/../references/guide.md\n'
          'cat "$(dirname "$0")/../references/guide.md"\n', mode=0o755)
    (project / ".claude/skills/review/assets").mkdir()
    # Binary assets name no files, even when their bytes happen to look like a path.
    (project / ".claude/skills/review/assets/logo.png").write_bytes(b"\x89PNG\r\n\x00](../../shared.md)\x00")
    write(project, ".claude/skills/shared.md", "shared\n")
    # Only Markdown is held to the Markdown grammar; `]:` in code is not a definition.
    write(project, ".claude/skills/review/assets/types.ts", "type M = {[key: string]: number};\n")
    write(project, "docs/guide.md", "# Guide\n")

    result = sync_cmd.run(project)

    assert ".claude/skills/review" in result["init_result"]["linked"]
    assert (project / ".ctx/skills/review/references/more.md").is_file()


# --- reference and planning folders -------------------------------------------

def reference_folder(project: Path) -> Path:
    project = happy_repo(project)
    sync_cmd.run(project)
    write(project, "docs/architecture/adr-1.md", "# ADR 1\n\nSee [the code](../../src/app.py).\n")
    write(project, "docs/architecture/diagrams/flow.txt", "a -> b\n")
    write(project, "docs/architecture/tools/check.sh", "#!/bin/sh\necho ok\n", mode=0o755)
    write(project, "src/app.py", "print('hello')\n")
    write(project, "README.md", "Read [ADR 1](docs/architecture/adr-1.md).\n")
    return project


def test_add_connects_a_reference_folder_through_a_relative_link(tmp_path):
    project = reference_folder(tmp_path)
    before = snapshot(project / "docs/architecture")

    res = add_cmd.run(project, "docs/architecture")

    assert res.status == "added"
    assert os.readlink(project / "docs/architecture") == "../.ctx/architecture"
    assert snapshot(project / ".ctx/architecture") == before
    assert snapshot(core.sources_dir(project) / "docs/architecture") == before
    assert snapshot(project / "docs/architecture") == before  # read through the link
    doc = manifest.load_v2(project)
    assert ("reference-docs-architecture", "reference", ".ctx/architecture") in \
        {(r["id"], r["type"], r["canonical"]) for r in doc["resources"]}
    # Existing readers keep working through the original path: a link in another
    # document, a script reading a file, and the folder's own relative reference.
    assert (project / "docs/architecture/adr-1.md").read_text(encoding="utf-8").startswith("# ADR 1")
    out = subprocess.run(["cat", "docs/architecture/adr-1.md"], cwd=project, capture_output=True, text=True)
    assert out.returncode == 0 and out.stdout.startswith("# ADR 1")
    out = subprocess.run(["sh", "docs/architecture/tools/check.sh"], cwd=project, capture_output=True, text=True)
    assert out.stdout == "ok\n"
    assert (project / "docs/architecture/../../src/app.py").resolve() == (project / "src/app.py").resolve()
    assert (project / ".ctx/architecture/../../src/app.py").resolve() == (project / "src/app.py").resolve()
    assert sync_cmd.run(project)["mutated"] is False


def test_writes_through_the_original_path_reach_the_canonical_files(tmp_path):
    project = reference_folder(tmp_path)
    add_cmd.run(project, "docs/architecture")

    with open(project / "docs/architecture/adr-1.md", "a", encoding="utf-8") as f:
        f.write("Accepted.\n")
    write(project, "docs/architecture/adr-2.md", "# ADR 2\n")

    assert (project / ".ctx/architecture/adr-1.md").read_text(encoding="utf-8").endswith("Accepted.\n")
    assert (project / ".ctx/architecture/adr-2.md").read_text(encoding="utf-8") == "# ADR 2\n"
    assert os.path.islink(project / "docs/architecture")
    assert sync_cmd.run(project)["final_state"] == "healthy"


def test_a_planning_folder_is_a_candidate_and_is_adopted_only_when_added(tmp_path):
    project = happy_repo(tmp_path)
    write(project, ".planning/2026-11-04-refactor/progress.md", "# Progress\n")
    write(project, ".planning/.active_plan", "2026-11-04-refactor\n")

    result = sync_cmd.run(project)

    assert ".planning" not in result["init_result"]["linked"]
    assert not os.path.islink(project / ".planning")
    assert ".planning" in sync_cmd.run(project)["candidates"]

    assert add_cmd.run(project, ".planning").status == "added"
    assert os.readlink(project / ".planning") == ".ctx/planning"
    assert (project / ".ctx/planning/2026-11-04-refactor/progress.md").read_text(encoding="utf-8") == "# Progress\n"
    assert ("planning-planning", "planning") in {(r["id"], r["type"]) for r in manifest.load_v2(project)["resources"]}
    assert ".planning" not in sync_cmd.run(project)["candidates"]


@pytest.mark.parametrize("folder, canonical", [
    ("docs/architecture", ".ctx/architecture"),          # same depth
    (".claude/planning-with-files", ".ctx/planning-with-files"),
    ("a/b/c", ".ctx/b/c"),
    ("notes", ".ctx/notes"),                             # top level: one deeper, guard decides
])
def test_a_folder_keeps_its_depth_when_it_can(tmp_path, folder, canonical):
    project = happy_repo(tmp_path)
    sync_cmd.run(project)
    write(project, f"{folder}/note.md", "# Note\n")

    add_cmd.run(project, folder)

    assert os.readlink(project / folder) == os.path.relpath(canonical, os.path.dirname(folder) or ".")
    assert (project / canonical / "note.md").is_file()


@pytest.mark.parametrize("folder, setup, reason", [
    (".claude", None, "tool_folder"),                         # holds tool configuration
    (".claude/rules", None, "tool_folder"),                   # rules there are managed one by one
    (".claude/rules/sub", None, "tool_folder"),
    ("docs/skills", None, "reserved_name"),                   # would be .ctx/skills
    ("docs/arch", lambda p: (p / "docs/arch/link").symlink_to("../../src"), "contains_symlink"),
    ("docs/arch", lambda p: write(p, "docs/arch/a.md", "[guide](../guide.md)\n"), "breaks_reference"),
    ("notes", lambda p: write(p, "notes/a.md", "[code](../src/app.py)\n"), "breaks_reference"),
])
def test_a_folder_that_cannot_move_safely_is_left_in_place(tmp_path, folder, setup, reason):
    project = happy_repo(tmp_path)
    sync_cmd.run(project)
    write(project, f"{folder}/x.md", "# X\n")
    write(project, "docs/guide.md", "# Guide\n")
    write(project, "src/app.py", "print('hello')\n")
    if setup:
        setup(project)
    before = snapshot(project)

    with pytest.raises(add_cmd.AddError, match=reason):
        add_cmd.run(project, folder)
    assert snapshot(project) == before


@pytest.mark.parametrize("folder", [".", ".ctx", ".ctx/sources", "../outside"])
def test_add_refuses_folders_superctx_cannot_own(tmp_path, folder):
    project = happy_repo(tmp_path)
    sync_cmd.run(project)
    (tmp_path / "outside").mkdir()
    before = snapshot(project)

    with pytest.raises(add_cmd.AddError):
        add_cmd.run(project, folder)
    assert snapshot(project) == before


def test_nothing_is_linked_where_directory_links_are_unsupported(tmp_path, monkeypatch):
    def no_links(src, dst, target_is_directory=False):
        raise OSError("symbolic links are not supported here")
    monkeypatch.setattr(adopt, "_symlink", no_links)

    project = happy_repo(tmp_path)
    before = {rel: snapshot(project / rel) for rel in (".claude/rules", ".claude/skills")}
    result = sync_cmd.run(project)

    left = {i["path"]: i["reason"] for i in result["init_result"]["left_in_place"]}
    assert left == {".claude/rules/python.md": "links_unsupported", ".claude/skills/review": "links_unsupported"}
    assert result["init_result"]["connected"] == ["CLAUDE.md"] and result["final_state"] == "healthy"
    for rel, snap in before.items():
        assert snapshot(project / rel) == snap
    assert not os.path.lexists(project / ".ctx/rules") and not os.path.lexists(project / ".ctx/skills")

    write(project, "docs/architecture/a.md", "# A\n")
    before = snapshot(project)
    with pytest.raises(add_cmd.AddError, match="links_unsupported"):
        add_cmd.run(project, "docs/architecture")
    assert snapshot(project) == before


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
