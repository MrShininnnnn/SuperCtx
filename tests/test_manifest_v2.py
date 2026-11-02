"""v2 manifest: schema validation, workspace states, migration through sync and add."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from superctx import add as add_cmd, core, init as init_cmd, manifest, shim, sync as sync_cmd, toml_compat
from test_v2_migration_safety import snapshot

V1_MANIFEST = """\
[project]
name = "repo"
hub = ".ctx/SUPERCTX.md"

[[files]]
path = "CLAUDE.md"
tools = ["Claude Code"]

[[files]]
path = ".github/copilot-instructions.md"
tools = ["GitHub Copilot"]
backup_required = false

[[files]]
path = "docs/AGENT.md"
tools = []
note = "user-confirmed local convention; not verified official path"
"""


def full_doc() -> dict:
    doc = manifest.new_doc("repo")
    doc["resources"] += [
        {"id": "review", "type": "skill", "canonical": ".ctx/skills/review"},
        {"id": "python", "type": "rule", "canonical": ".ctx/rules/python.md"},
    ]
    doc["natives"] += [
        manifest.instruction_native("CLAUDE.md", ["Claude Code"]),
        manifest.instruction_native("docs/AGENT.md", [], backup=False, note="local"),
        {"resource": "review", "path": ".claude/skills/review", "mode": "link", "tools": ["Claude Code"], "backup": False},
        {"resource": "review", "path": ".agents/skills/review", "mode": "generated", "tools": ["OpenAI Codex"],
         "backup": True, "published_hash": "sha256:" + "a" * 64},
        {"resource": "python", "path": ".cursor/rules/python.mdc", "mode": "link", "tools": ["Cursor"], "backup": True},
    ]
    return doc


def v1_repo(tmp_path: Path) -> Path:
    """A v1 workspace as v0.1.x leaves it: hub, healthy shims, backups, and manifest.toml."""
    project = tmp_path / "repo"
    project.mkdir()
    core.ctx_dir(project).mkdir()
    core.manifest_path(project).write_text(V1_MANIFEST, encoding="utf-8")
    core.hub_path(project).write_text(core.hub_policy_header("repo"), encoding="utf-8")
    core.sources_dir(project).mkdir()
    core.ensure_sources_readme(project)
    for rel, backup in (("CLAUDE.md", True), (".github/copilot-instructions.md", False), ("docs/AGENT.md", True)):
        live = project / rel
        live.parent.mkdir(parents=True, exist_ok=True)
        live.write_text(shim.generate_shim(rel, "plain-pointer", backup_required=backup), encoding="utf-8")
        if backup:
            src = core.sources_dir(project) / rel
            src.parent.mkdir(parents=True, exist_ok=True)
            src.write_text(f"original {rel}\n", encoding="utf-8")
    return project


# --- schema -----------------------------------------------------------------

def test_dump_round_trips_through_every_toml_loader():
    doc = manifest.validate(full_doc())
    text = manifest.dump(doc)

    assert manifest.validate(manifest._parse(text)) == doc
    assert manifest.validate(toml_compat._load_minimal(text)) == doc
    assert manifest.dump(manifest._parse(text)) == text


def _mutate(path, value):
    def apply(doc):
        target = doc
        for key in path[:-1]:
            target = target[key]
        if value is _DELETE:
            del target[path[-1]]
        else:
            target[path[-1]] = value
    return apply


_DELETE = object()

INVALID = {
    "unknown root key": (_mutate(["extra"], 1), "unknown keys"),
    "unknown native key": (_mutate(["natives", 0, "extra"], 1), "unknown keys"),
    "wrong schema": (_mutate(["schema"], 3), "'schema' must be 2"),
    "bool schema": (_mutate(["schema"], True), "'schema' must be 2"),
    "unknown type": (_mutate(["resources", 1, "type"], "command"), "unknown type"),
    "bad id": (_mutate(["resources", 1, "id"], "Review!"), "id is invalid"),
    "duplicate id": (_mutate(["resources", 2, "id"], "review"), "Duplicate resource id"),
    "duplicate canonical": (_mutate(["resources", 2, "canonical"], ".ctx/skills/review"), "Duplicate canonical"),
    "canonical outside .ctx": (_mutate(["resources", 1, "canonical"], "skills/review"), "must be under .ctx/"),
    "canonical in sources": (_mutate(["resources", 1, "canonical"], ".ctx/sources/review"), "outside .ctx/sources/"),
    "hub moved": (_mutate(["resources", 0, "canonical"], ".ctx/HUB.md"), "exactly one instructions resource"),
    "no instructions": (_mutate(["resources", 0, "type"], "reference"), "exactly one instructions resource"),
    "absolute native": (_mutate(["natives", 0, "path"], "/etc/passwd"), "relative POSIX path"),
    "escaping native": (_mutate(["natives", 0, "path"], "a/../../x.md"), "inside the repository"),
    "unnormalized native": (_mutate(["natives", 0, "path"], "./CLAUDE.md"), "normalized path"),
    "dot native": (_mutate(["natives", 0, "path"], "."), "normalized path"),
    "backslash native": (_mutate(["natives", 0, "path"], "a\\b.md"), "relative POSIX path"),
    "native in .ctx": (_mutate(["natives", 0, "path"], ".ctx/CLAUDE.md"), "inside .ctx/"),
    "unknown resource": (_mutate(["natives", 2, "resource"], "nope"), "unknown resource"),
    "unknown mode": (_mutate(["natives", 2, "mode"], "copy"), "unknown mode"),
    "instructions link": (_mutate(["natives", 0, "mode"], "link"), "must use pointer mode"),
    "generated without hash": (_mutate(["natives", 3, "published_hash"], _DELETE), "requires published_hash"),
    "bad hash": (_mutate(["natives", 3, "published_hash"], "sha256:xyz"), "requires published_hash"),
    "hash on link": (_mutate(["natives", 2, "published_hash"], "sha256:" + "b" * 64), "only allowed in generated"),
    "duplicate native": (_mutate(["natives", 1, "path"], "CLAUDE.md"), "collide"),
    "nested native": (_mutate(["natives", 3, "path"], ".claude/skills/review/extra"), "collide"),
    "tools not strings": (_mutate(["natives", 0, "tools"], [1]), "array of strings"),
    "backup not bool": (_mutate(["natives", 0, "backup"], "yes"), "must be a boolean"),
}


@pytest.mark.parametrize("case", list(INVALID))
def test_validate_rejects(case):
    mutate, message = INVALID[case]
    doc = copy.deepcopy(full_doc())
    mutate(doc)
    with pytest.raises(core.SchemaError, match=message):
        manifest.validate(doc)


# --- workspace states -------------------------------------------------------

def test_locate_classifies_every_manifest_combination(tmp_path):
    project = tmp_path / "repo"
    core.ctx_dir(project).mkdir(parents=True)
    sentinel, v2, v1_copy = core.manifest_path(project), core.v2_manifest_path(project), core.v1_backup_path(project)
    v2_text = manifest.dump(full_doc())

    def state(sentinel_text=None, v2_present=False, v1_copy_present=False):
        for path in (sentinel, v2, v1_copy):
            path.unlink(missing_ok=True)
        if sentinel_text is not None:
            sentinel.write_text(sentinel_text, encoding="utf-8")
        if v2_present:
            v2.write_text(v2_text, encoding="utf-8")
        if v1_copy_present:
            v1_copy.write_text(V1_MANIFEST, encoding="utf-8")
        return manifest.locate(project)

    in_progress, complete = manifest.sentinel_text(manifest.IN_PROGRESS), manifest.sentinel_text(manifest.COMPLETE)
    assert state() == "none"
    assert state(V1_MANIFEST) == "v1"
    assert state("garbage = [[[\n") == "v1"
    assert state(in_progress, v1_copy_present=True) == "interrupted"
    assert state(in_progress) == "lost"
    assert state(complete) == "lost"
    assert state(complete, v1_copy_present=True) == "lost"
    assert state(complete, v2_present=True) == "v2"
    assert state(None, v2_present=True) == "v2_unsealed"
    assert state(in_progress, v2_present=True) == "v2_unsealed"
    assert state(V1_MANIFEST, v2_present=True) == "conflict"
    assert state("garbage = [[[\n", v2_present=True) == "conflict"
    # An unknown migration marker never permits a rebuild from the v1 copy.
    assert state(complete.replace('"complete"', '"later"'), v1_copy_present=True) == "lost"


# --- migration through sync -------------------------------------------------

def test_sync_migrates_v1_workspace_and_second_sync_makes_no_changes(tmp_path):
    project = v1_repo(tmp_path)
    shims_before = {rel: (project / rel).read_text(encoding="utf-8") for rel in ("CLAUDE.md", "docs/AGENT.md")}

    first = sync_cmd.run(project)

    assert first["migrated"] is True and first["mutated"] is True
    assert first["final_state"] == "healthy"
    assert manifest.locate(project) == "v2"
    assert core.v1_backup_path(project).read_text(encoding="utf-8") == V1_MANIFEST
    v2 = manifest.load_v2(project)
    assert [(n["path"], n["mode"], n["tools"], n["backup"], n.get("note")) for n in v2["natives"]] == [
        ("CLAUDE.md", "pointer", ["Claude Code"], True, None),
        (".github/copilot-instructions.md", "pointer", ["GitHub Copilot"], False, None),
        ("docs/AGENT.md", "pointer", [], True, "user-confirmed local convention; not verified official path"),
    ]
    assert core.load_manifest(project)["files"] == [
        {"path": "CLAUDE.md", "tools": ["Claude Code"], "backup_required": True},
        {"path": ".github/copilot-instructions.md", "tools": ["GitHub Copilot"], "backup_required": False},
        {"path": "docs/AGENT.md", "tools": [], "backup_required": True,
         "note": "user-confirmed local convention; not verified official path"},
    ]
    assert {rel: (project / rel).read_text(encoding="utf-8") for rel in shims_before} == shims_before

    before = snapshot(project)
    second = sync_cmd.run(project)

    assert "migrated" not in second
    assert second["mutated"] is False
    assert snapshot(project) == before


def test_sync_reseals_a_deleted_sentinel(tmp_path):
    project = v1_repo(tmp_path)
    sync_cmd.run(project)
    core.manifest_path(project).unlink()

    result = sync_cmd.run(project)

    assert result["migrated"] is True
    assert manifest.locate(project) == "v2"
    assert core.manifest_path(project).read_text(encoding="utf-8") == manifest.sentinel_text(manifest.COMPLETE)


def test_init_refuses_when_sentinel_is_deleted(tmp_path):
    """The 0.1.4 hazard (init over a hub when the sentinel is gone) does not exist in this client."""
    project = v1_repo(tmp_path)
    sync_cmd.run(project)
    core.hub_path(project).write_text("hand-written hub\n", encoding="utf-8")
    core.manifest_path(project).unlink()
    before = snapshot(project)

    result = init_cmd.run(project)

    assert result["created"] is False
    assert snapshot(project) == before


@pytest.mark.parametrize("damage", ["conflict", "lost", "unknown-key", "invalid-v1-entry"])
def test_sync_refuses_unsafe_manifest_states_without_writing(tmp_path, damage):
    project = v1_repo(tmp_path)
    if damage == "invalid-v1-entry":
        core.manifest_path(project).write_text(V1_MANIFEST + '\n[[files]]\npath = "CLAUDE.md"\ntools = []\n', encoding="utf-8")
    else:
        sync_cmd.run(project)
        if damage == "conflict":
            core.manifest_path(project).write_text(V1_MANIFEST, encoding="utf-8")
        elif damage == "lost":
            core.v2_manifest_path(project).unlink()
        else:
            text = core.v2_manifest_path(project).read_text(encoding="utf-8")
            core.v2_manifest_path(project).write_text(text.replace("schema = 2\n", "schema = 2\nfuture = true\n"), encoding="utf-8")
    before = snapshot(project)

    result = sync_cmd.run(project)

    assert result["final_state"] == "needs_attention"
    assert result["mutated"] is False
    assert snapshot(project) == before


# --- add --------------------------------------------------------------------

def test_add_migrates_a_v1_workspace_before_adding(tmp_path):
    project = v1_repo(tmp_path)
    (project / "GEMINI.md").write_text("gemini notes\n", encoding="utf-8")

    result = add_cmd.run(project, "GEMINI.md")

    assert result.status == "added"
    assert manifest.locate(project) == "v2"
    natives = manifest.load_v2(project)["natives"]
    assert natives[-1] == manifest.instruction_native("GEMINI.md", result.tools, backup=True)
    assert len(natives) == 4


def test_add_preserves_v2_only_resources(tmp_path):
    project = v1_repo(tmp_path)
    sync_cmd.run(project)
    doc = manifest.load_v2(project)
    doc["resources"].append({"id": "review", "type": "skill", "canonical": ".ctx/skills/review"})
    doc["natives"].append({"resource": "review", "path": ".claude/skills/review", "mode": "link", "tools": [], "backup": False})
    manifest.write(project, doc)
    (project / "GEMINI.md").write_text("gemini notes\n", encoding="utf-8")

    add_cmd.run(project, "GEMINI.md")

    after = manifest.load_v2(project)
    assert after["resources"] == doc["resources"]
    assert after["natives"][:-1] == doc["natives"]


def test_add_refuses_a_path_that_collides_with_a_linked_directory(tmp_path):
    project = v1_repo(tmp_path)
    sync_cmd.run(project)
    doc = manifest.load_v2(project)
    doc["resources"].append({"id": "review", "type": "skill", "canonical": ".ctx/skills/review"})
    doc["natives"].append({"resource": "review", "path": "skills/review", "mode": "link", "tools": [], "backup": False})
    manifest.write(project, doc)
    (project / "skills/review").mkdir(parents=True)
    (project / "skills/review/NOTES.md").write_text("notes\n", encoding="utf-8")
    before = snapshot(project)

    with pytest.raises(add_cmd.AddError, match="collide"):
        add_cmd.run(project, "skills/review/NOTES.md")
    assert snapshot(project) == before
