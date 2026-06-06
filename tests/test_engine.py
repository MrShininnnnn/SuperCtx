"""Unit tests for the SuperCtx engine (init / sync / status) using temp project dirs."""

from importlib import resources
from pathlib import Path

from superctx import core, init as init_cmd, registry, shim, status as status_cmd, sync as sync_cmd


def make_repo(tmp_path: Path, files: dict[str, str]) -> Path:
    for rel, content in files.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return tmp_path


def test_conventions_registry_is_packaged_with_module():
    assert (resources.files("superctx") / "conventions.toml").is_file()
    assert registry.load_conventions()[0]["path"] == "CLAUDE.md"


# --- init -------------------------------------------------------------------

def test_init_detects_and_scaffolds(tmp_path):
    make_repo(tmp_path, {"CLAUDE.md": "claude ctx\n", "AGENTS.md": "agents ctx\n"})
    result = init_cmd.run(tmp_path)

    assert result["created"] is True
    assert set(result["connected"]) == {"CLAUDE.md", "AGENTS.md"}
    assert core.manifest_path(tmp_path).is_file()
    assert core.hub_path(tmp_path).is_file()

    # gitignore check
    gitignore_text = (core.ctx_dir(tmp_path) / ".gitignore").read_text()
    assert gitignore_text.strip().endswith("sources/")
    assert "Inactive backup storage" in gitignore_text

    manifest = core.load_manifest(tmp_path)
    assert {f["path"] for f in manifest["files"]} == {"CLAUDE.md", "AGENTS.md"}
    # tools metadata is carried over from the registry
    claude = next(f for f in manifest["files"] if f["path"] == "CLAUDE.md")
    assert claude["tools"] == ["Claude Code"]

    # Verify shims exist and are valid shims
    from superctx.shim import is_shim_file
    assert is_shim_file(tmp_path / "CLAUDE.md") is True
    assert is_shim_file(tmp_path / "AGENTS.md") is True

    # Verify backups are stored with original content
    assert (core.sources_dir(tmp_path) / "CLAUDE.md").read_text() == "claude ctx\n"
    assert (core.sources_dir(tmp_path) / "AGENTS.md").read_text() == "agents ctx\n"


def test_init_ignores_unrelated_files(tmp_path):
    make_repo(tmp_path, {"CLAUDE.md": "x\n", "README.md": "not a tool file\n"})
    result = init_cmd.run(tmp_path)
    assert result["connected"] == ["CLAUDE.md"]


def test_init_detects_hidden_instruction_files(tmp_path):
    make_repo(tmp_path, {
        ".claude/CLAUDE.md": "claude hidden\n",
        ".codex/AGENTS.md": "codex hidden\n",
        ".agy/ANTIGRAVITY.md": "agy hidden\n",
        "AGENTS.md": "root agents\n"
    })
    result = init_cmd.run(tmp_path)
    assert result["created"] is True
    assert set(result["connected"]) == {
        ".claude/CLAUDE.md",
        ".codex/AGENTS.md",
        "AGENTS.md"
    }

    # Verify the generated hub file includes proper provenance headers and contents
    hub_content = core.hub_path(tmp_path).read_text(encoding="utf-8")
    assert "## From: .claude/CLAUDE.md" in hub_content
    assert "claude hidden" in hub_content
    assert "## From: .codex/AGENTS.md" in hub_content
    assert "codex hidden" in hub_content
    assert "## From: AGENTS.md" in hub_content
    assert "root agents" in hub_content

    # Since they are shims now, run sync to ensure it treats them as healthy and does not rewrite the hub.
    sync_result = sync_cmd.run(tmp_path)
    assert sync_result["mode"] == "repair"
    assert set(sync_result["healthy"]) == {
        ".claude/CLAUDE.md",
        ".codex/AGENTS.md",
        "AGENTS.md"
    }
    assert sync_result["repaired"] == []
    assert sync_result["unresolved"] == []
    assert sync_result["warnings"] == []

    # Verify status reports connected files as healthy shims with healthy inactive backups.
    status_rows = status_cmd.run(tmp_path)
    assert len(status_rows) == 8
    assert next(r for r in status_rows if r["kind"] == "hub")["state"] == "healthy"
    assert len([r for r in status_rows if r["kind"] == "shim" and r["state"] == "healthy"]) == 3
    assert len([r for r in status_rows if r["kind"] == "backup" and r["state"] == "healthy"]) == 3
    assert len([r for r in status_rows if r["kind"] == "candidate"]) == 1


def test_init_is_idempotent(tmp_path):
    make_repo(tmp_path, {"CLAUDE.md": "x\n"})
    init_cmd.run(tmp_path)
    again = init_cmd.run(tmp_path)
    assert again["created"] is False
    assert again["reason"] == "exists"
    assert again["partially_migrated"] is False


def test_init_broken_shims(tmp_path):
    make_repo(tmp_path, {"CLAUDE.md": "x\n"})
    init_cmd.run(tmp_path)

    # Manually break CLAUDE.md shim
    (tmp_path / "CLAUDE.md").write_text("broken shim content", encoding="utf-8")

    again = init_cmd.run(tmp_path)
    assert again["created"] is False
    assert again["reason"] == "exists"
    assert again["partially_migrated"] is True
    assert again["broken_shims"] == ["CLAUDE.md"]


def test_init_backup_collision_reports_failure(tmp_path):
    # Pre-create backup and a modified live file to trigger backup collision
    make_repo(tmp_path, {
        "CLAUDE.md": "modified content\n",
        ".ctx/sources/CLAUDE.md": "original backup\n"
    })
    result = init_cmd.run(tmp_path)
    assert result["created"] is True
    assert result.get("partial_shim_failure") is True
    assert result["failed_shims"] == ["CLAUDE.md"]
    assert "CLAUDE.md" not in result["connected"]

    # Verify live is NOT shimmed (original content preserved)
    assert (tmp_path / "CLAUDE.md").read_text() == "modified content\n"


# --- sync -------------------------------------------------------------------

def test_sync_never_modifies_hub(tmp_path):
    make_repo(tmp_path, {"CLAUDE.md": "a\n"})
    init_cmd.run(tmp_path)

    hub_p = core.hub_path(tmp_path)
    hub_p.write_text("custom user hub edits\n", encoding="utf-8")

    # Intentionally corrupt the shim to trigger a repair
    (tmp_path / "CLAUDE.md").write_text("corrupted content\n", encoding="utf-8")

    result = sync_cmd.run(tmp_path)

    # Hub content must remain completely unchanged
    assert hub_p.read_text(encoding="utf-8") == "custom user hub edits\n"
    assert result["mode"] == "repair"


def test_sync_healthy_shims_are_untouched(tmp_path):
    import time
    make_repo(tmp_path, {"CLAUDE.md": "a\n", "AGENTS.md": "b\n"})
    init_cmd.run(tmp_path)

    live_c = tmp_path / "CLAUDE.md"
    live_a = tmp_path / "AGENTS.md"

    content_c_before = live_c.read_text(encoding="utf-8")
    content_a_before = live_a.read_text(encoding="utf-8")

    mtime_c_before = live_c.stat().st_mtime
    mtime_a_before = live_a.stat().st_mtime

    # Small sleep to ensure time has passed if mtimes are updated
    time.sleep(0.01)

    result = sync_cmd.run(tmp_path)

    assert set(result["healthy"]) == {"CLAUDE.md", "AGENTS.md"}
    assert result["repaired"] == []
    assert result["unresolved"] == []

    assert live_c.read_text(encoding="utf-8") == content_c_before
    assert live_a.read_text(encoding="utf-8") == content_a_before
    assert live_c.stat().st_mtime == mtime_c_before
    assert live_a.stat().st_mtime == mtime_a_before


def test_sync_missing_shim_with_existing_backup(tmp_path):
    make_repo(tmp_path, {"CLAUDE.md": "a\n"})
    init_cmd.run(tmp_path)

    live_file = tmp_path / "CLAUDE.md"
    backup_file = core.sources_dir(tmp_path) / "CLAUDE.md"

    # Remove the live file (shim)
    live_file.unlink()

    backup_content_before = backup_file.read_text(encoding="utf-8")

    result = sync_cmd.run(tmp_path)

    assert result["healthy"] == []
    assert result["repaired"] == ["CLAUDE.md"]
    assert result["unresolved"] == []

    # Shim must be regenerated correctly
    assert shim.is_shim_file(live_file)
    # Backup must remain completely unchanged
    assert backup_file.read_text(encoding="utf-8") == backup_content_before


def test_sync_broken_shim_with_existing_backup(tmp_path):
    make_repo(tmp_path, {"CLAUDE.md": "a\n"})
    init_cmd.run(tmp_path)

    live_file = tmp_path / "CLAUDE.md"
    backup_file = core.sources_dir(tmp_path) / "CLAUDE.md"

    # Overwrite live file with non-shim edits
    live_file.write_text("user edits here\n", encoding="utf-8")

    backup_content_before = backup_file.read_text(encoding="utf-8")

    result = sync_cmd.run(tmp_path)

    assert result["healthy"] == []
    assert result["repaired"] == []
    assert result["unresolved"] == [{"path": "CLAUDE.md", "reason": "backup_exists_and_live_has_edits"}]

    # Overwritten non-shim text and backup must NOT be changed
    assert live_file.read_text(encoding="utf-8") == "user edits here\n"
    assert backup_file.read_text(encoding="utf-8") == backup_content_before


def test_sync_missing_backup_warning(tmp_path):
    make_repo(tmp_path, {"CLAUDE.md": "a\n"})
    init_cmd.run(tmp_path)

    live_file = tmp_path / "CLAUDE.md"
    backup_file = core.sources_dir(tmp_path) / "CLAUDE.md"

    # Delete backup
    backup_file.unlink()

    # Delete shim as well to force repair
    live_file.unlink()

    result = sync_cmd.run(tmp_path)

    assert result["healthy"] == []
    assert result["repaired"] == ["CLAUDE.md"]
    assert result["unresolved"] == []
    assert result["warnings"] == [{"path": "CLAUDE.md", "reason": "missing_backup"}]

    # Live file is still repaired successfully (safe because it was missing)
    assert shim.is_shim_file(live_file)


def test_sync_uninitialized_repo(tmp_path):
    import pytest
    with pytest.raises(sync_cmd.SyncError) as exc_info:
        sync_cmd.run(tmp_path)
    assert "not initialized" in str(exc_info.value)


def test_sync_empty_manifest_reports_no_registered_files(tmp_path):
    core.ctx_dir(tmp_path).mkdir(parents=True)
    core.manifest_path(tmp_path).write_text(
        core.dump_manifest({
            "project": {"name": "empty", "hub": ".ctx/SUPERCTX.md"},
            "files": [],
        }),
        encoding="utf-8",
    )
    core.hub_path(tmp_path).write_text("# SUPERCTX - empty\n", encoding="utf-8")

    result = sync_cmd.run(tmp_path)

    assert result == {
        "mode": "repair",
        "healthy": [],
        "repaired": [],
        "unresolved": [],
        "warnings": [],
    }


def test_sync_legacy_mode_is_not_available(tmp_path):
    import pytest
    from superctx import __main__ as cli

    make_repo(tmp_path, {"CLAUDE.md": "a\n"})
    init_cmd.run(tmp_path)
    hub_before = core.hub_path(tmp_path).read_text(encoding="utf-8")

    with pytest.raises(SystemExit) as exc_info:
        cli.main(["sync", "--legacy", str(tmp_path)])

    assert exc_info.value.code == 2
    assert core.hub_path(tmp_path).read_text(encoding="utf-8") == hub_before


# --- status -----------------------------------------------------------------

def test_status_healthy_shims(tmp_path):
    make_repo(tmp_path, {"CLAUDE.md": "a\n", "AGENTS.md": "b\n"})
    init_cmd.run(tmp_path)

    rows = status_cmd.run(tmp_path)

    # Assert Hub
    hub_row = next(r for r in rows if r["kind"] == "hub")
    assert hub_row["path"] == ".ctx/SUPERCTX.md"
    assert hub_row["state"] == "healthy"

    # Assert Shims
    claude_shim = next(r for r in rows if r["kind"] == "shim" and r["path"] == "CLAUDE.md")
    assert claude_shim["state"] == "healthy"
    assert claude_shim["import_syntax"] == "claude-at-import"

    agents_shim = next(r for r in rows if r["kind"] == "shim" and r["path"] == "AGENTS.md")
    assert agents_shim["state"] == "healthy"
    assert agents_shim["import_syntax"] == "plain-pointer"

    # Assert Backups
    claude_backup = next(r for r in rows if r["kind"] == "backup" and r["source"] == "CLAUDE.md")
    assert claude_backup["path"] == ".ctx/sources/CLAUDE.md"
    assert claude_backup["state"] == "healthy"

    agents_backup = next(r for r in rows if r["kind"] == "backup" and r["source"] == "AGENTS.md")
    assert agents_backup["path"] == ".ctx/sources/AGENTS.md"
    assert agents_backup["state"] == "healthy"


def test_status_broken_and_missing_shims(tmp_path):
    make_repo(tmp_path, {"CLAUDE.md": "a\n", "AGENTS.md": "b\n"})
    init_cmd.run(tmp_path)

    # Break CLAUDE.md (overwrite shim)
    (tmp_path / "CLAUDE.md").write_text("manual edit\n", encoding="utf-8")
    # Delete AGENTS.md
    (tmp_path / "AGENTS.md").unlink()

    rows = status_cmd.run(tmp_path)

    claude_shim = next(r for r in rows if r["kind"] == "shim" and r["path"] == "CLAUDE.md")
    assert claude_shim["state"] == "broken_shim"

    agents_shim = next(r for r in rows if r["kind"] == "shim" and r["path"] == "AGENTS.md")
    assert agents_shim["state"] == "missing_shim"


def test_status_missing_backup(tmp_path):
    make_repo(tmp_path, {"CLAUDE.md": "a\n"})
    init_cmd.run(tmp_path)

    # Delete backup
    (core.sources_dir(tmp_path) / "CLAUDE.md").unlink()

    rows = status_cmd.run(tmp_path)

    backup_row = next(r for r in rows if r["kind"] == "backup" and r["source"] == "CLAUDE.md")
    assert backup_row["state"] == "missing_backup"


def test_status_missing_or_empty_hub(tmp_path):
    make_repo(tmp_path, {"CLAUDE.md": "a\n"})
    init_cmd.run(tmp_path)

    # Empty the hub
    core.hub_path(tmp_path).write_text("", encoding="utf-8")
    rows1 = status_cmd.run(tmp_path)
    hub_row1 = next(r for r in rows1 if r["kind"] == "hub")
    assert hub_row1["state"] == "empty_hub"

    # Delete the hub
    core.hub_path(tmp_path).unlink()
    rows2 = status_cmd.run(tmp_path)
    hub_row2 = next(r for r in rows2 if r["kind"] == "hub")
    assert hub_row2["state"] == "missing_hub"


def test_status_untracked_candidate(tmp_path):
    make_repo(tmp_path, {"CLAUDE.md": "a\n"})
    init_cmd.run(tmp_path)

    # Create an untracked local candidate
    agy_file = tmp_path / ".agy/ANTIGRAVITY.md"
    agy_file.parent.mkdir(parents=True, exist_ok=True)
    agy_file.write_text("rules\n", encoding="utf-8")

    rows = status_cmd.run(tmp_path)

    cand_row = next(r for r in rows if r["kind"] == "candidate" and r["path"] == ".agy/ANTIGRAVITY.md")
    assert cand_row["state"] == "untracked_candidate"
    assert cand_row["label"] == "local convention candidate"


def test_status_uninitialized_repo(tmp_path):
    import pytest
    from superctx.status import StatusError

    with pytest.raises(StatusError) as exc_info:
        status_cmd.run(tmp_path)
    assert "SuperCtx is not initialized in this project" in str(exc_info.value)


def test_status_is_read_only(tmp_path):
    make_repo(tmp_path, {"CLAUDE.md": "a\n"})
    init_cmd.run(tmp_path)

    # Record mtimes
    manifest_mtime = core.manifest_path(tmp_path).stat().st_mtime
    hub_mtime = core.hub_path(tmp_path).stat().st_mtime
    shim_mtime = (tmp_path / "CLAUDE.md").stat().st_mtime
    backup_mtime = (core.sources_dir(tmp_path) / "CLAUDE.md").stat().st_mtime

    # Run status multiple times
    status_cmd.run(tmp_path)
    status_cmd.run(tmp_path)

    # Verify no changes/mutation
    assert core.manifest_path(tmp_path).stat().st_mtime == manifest_mtime
    assert core.hub_path(tmp_path).stat().st_mtime == hub_mtime
    assert (tmp_path / "CLAUDE.md").stat().st_mtime == shim_mtime
    assert (core.sources_dir(tmp_path) / "CLAUDE.md").stat().st_mtime == backup_mtime


def test_status_shim_target_semantics(tmp_path):
    make_repo(tmp_path, {"CLAUDE.md": "a\n", "AGENTS.md": "b\n"})
    init_cmd.run(tmp_path)

    # Verify Claude Code shim has @ import targeting the hub
    claude_shim_text = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
    assert "@.ctx/SUPERCTX.md" in claude_shim_text.replace(" ", "")

    # Verify plain-pointer shim does not have @ import and points to the hub
    agents_shim_text = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert "@" not in agents_shim_text
    assert ".ctx/SUPERCTX.md" in agents_shim_text


def test_resolve_version_cases(tmp_path, monkeypatch):
    import json
    from superctx.status import resolve_version
    from superctx import __version__

    # Case 1: env var points to a temp plugin root with plugin.json
    env_root = tmp_path / "env_root"
    plugin_dir = env_root / ".claude-plugin"
    plugin_dir.mkdir(parents=True)
    plugin_json = plugin_dir / "plugin.json"
    plugin_json.write_text(json.dumps({"version": "0.1.2-env"}), encoding="utf-8")

    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(env_root))
    res = resolve_version()
    assert res["version"] == "0.1.2-env"
    assert res["version_source"] == "env"
    assert Path(res["plugin_root"]).resolve() == env_root.resolve()

    # Clear env var to test other cases
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)

    # Case 2: env var absent, parent-path discovery works
    parent_root = tmp_path / "parent_root"
    plugin_dir_parent = parent_root / ".claude-plugin"
    plugin_dir_parent.mkdir(parents=True)
    plugin_json_parent = plugin_dir_parent / "plugin.json"
    plugin_json_parent.write_text(json.dumps({"version": "0.1.3-parent"}), encoding="utf-8")

    # Call resolve_version with a deeply nested path inside parent_root
    deep_path = parent_root / "scripts" / "superctx" / "status.py"
    deep_path.parent.mkdir(parents=True, exist_ok=True)

    res = resolve_version(module_path=deep_path)
    assert res["version"] == "0.1.3-parent"
    assert res["version_source"] == "parent"
    assert Path(res["plugin_root"]).resolve() == parent_root.resolve()

    # Case 3: neither exists, fallback version is used
    empty_root = tmp_path / "empty_root"
    empty_root.mkdir()
    res = resolve_version(module_path=empty_root)
    assert res["version"] == __version__
    assert res["version_source"] == "fallback"
    assert res["plugin_root"] is None


def test_status_diagnostics_reports_correctly(tmp_path, monkeypatch):
    from superctx.status import diagnostics
    from superctx import __version__

    # Let's set up a project_dir with .claude/CLAUDE.md and .codex/AGENTS.md
    project_dir = tmp_path / "project"
    project_dir.mkdir()

    (project_dir / ".claude").mkdir(parents=True, exist_ok=True)
    (project_dir / ".claude" / "CLAUDE.md").write_text("claude file", encoding="utf-8")

    (project_dir / ".codex").mkdir(parents=True, exist_ok=True)
    (project_dir / ".codex" / "AGENTS.md").write_text("codex file", encoding="utf-8")

    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
    diag = diagnostics(project_dir, module_path=project_dir)

    assert diag["version"] == __version__
    assert diag["version_source"] == "fallback"
    assert "conventions.toml" in diag["registry"]
    assert diag["supports_claude_md"] is True
    assert diag["supports_codex_agents"] is True
    assert diag["project_has_claude_md"] is True
    assert diag["project_has_codex_agents"] is True
    assert diag["stale_install"] is False


def test_path_sanitization_with_home(tmp_path, monkeypatch):
    from superctx.status import sanitize_path

    home_dir = (tmp_path / "mock_home").resolve()
    home_dir.mkdir()

    # We patch Path.home to return home_dir
    monkeypatch.setattr(Path, "home", lambda: home_dir)

    nested_path = home_dir / "projects" / "superctx"
    sanitized = sanitize_path(nested_path)
    assert sanitized == "~/projects/superctx"

    # Test sibling path with matching string prefix is not rewritten
    sibling_path = (tmp_path / "mock_home_sibling" / "projects").resolve()
    sibling_path.parent.mkdir(parents=True, exist_ok=True)
    sanitized_sibling = sanitize_path(sibling_path)
    assert not sanitized_sibling.startswith("~")
    assert sanitized_sibling == str(sibling_path)

    # Test exact home directory
    assert sanitize_path(home_dir) == "~"


def test_status_diagnostics_warns_on_stale_install(tmp_path, monkeypatch):
    from superctx.status import diagnostics
    from superctx import registry

    # Case A: .claude/CLAUDE.md present but unsupported
    project_dir_claude = tmp_path / "project_claude"
    project_dir_claude.mkdir()
    (project_dir_claude / ".claude").mkdir(parents=True, exist_ok=True)
    (project_dir_claude / ".claude" / "CLAUDE.md").write_text("claude file", encoding="utf-8")

    monkeypatch.setattr(registry, "load_conventions", lambda *args, **kwargs: [
        {"path": "CLAUDE.md", "tools": ["Claude Code"], "kind": "instruction-file"}
    ])

    diag = diagnostics(project_dir_claude, module_path=project_dir_claude)
    assert diag["supports_claude_md"] is False
    assert diag["project_has_claude_md"] is True
    assert diag["stale_install"] is True

    # Case B: .codex/AGENTS.md present but unsupported
    project_dir_codex = tmp_path / "project_codex"
    project_dir_codex.mkdir()
    (project_dir_codex / ".codex").mkdir(parents=True, exist_ok=True)
    (project_dir_codex / ".codex" / "AGENTS.md").write_text("codex file", encoding="utf-8")

    diag_codex = diagnostics(project_dir_codex, module_path=project_dir_codex)
    assert diag_codex["supports_codex_agents"] is False
    assert diag_codex["project_has_codex_agents"] is True
    assert diag_codex["stale_install"] is True


def test_candidate_detection_and_reporting(tmp_path):
    make_repo(tmp_path, {
        ".claude/CLAUDE.md": "claude instructions\n",
        ".codex/AGENTS.md": "codex instructions\n",
        ".agents/rules/project.md": "rules\n",
        "agents/skills/my-skill/SKILL.md": "skills\n",
        ".agent/rules/legacy.md": "legacy\n",
        ".agy/ANTIGRAVITY.md": "agy file\n",
    })

    # Run init
    result = init_cmd.run(tmp_path)
    assert result["created"] is True
    assert set(result["detected"]) == {".claude/CLAUDE.md", ".codex/AGENTS.md"}

    disc = result["discovery"]
    assert len(disc["verified_instruction_file"]) == 2

    # Verify folder candidates
    supported_paths = {cand["path"] for cand in disc["supported_folder_candidate"]}
    assert ".agents/rules" in supported_paths
    assert "agents/skills" in supported_paths

    # Verify legacy candidates
    legacy_paths = {cand["path"] for cand in disc["legacy_or_uncertain_folder_candidate"]}
    assert ".agent/rules" in legacy_paths

    # Verify unverified candidate check selects file (.agy/ANTIGRAVITY.md) over directory (.agy)
    unverified_paths = {cand["path"] for cand in disc["unverified_local_candidate"]}
    assert ".agy/ANTIGRAVITY.md" in unverified_paths

    # Verify manifest only contains verified instruction files
    manifest = core.load_manifest(tmp_path)
    tracked_paths = {f["path"] for f in manifest["files"]}
    assert tracked_paths == {".claude/CLAUDE.md", ".codex/AGENTS.md"}

    # Run status and verify candidates are returned
    status_rows = status_cmd.run(tmp_path)
    candidates = [r for r in status_rows if r["state"] == "untracked_candidate"]
    assert len(candidates) >= 4
    cand_map = {c["path"]: c for c in candidates}

    assert cand_map[".agents/rules"]["label"] == "Antigravity workspace rules"
    assert cand_map[".agy/ANTIGRAVITY.md"]["label"] == "local convention candidate"
    assert cand_map[".agy/ANTIGRAVITY.md"]["note"] == "not verified official support"


def test_init_with_candidates_only(tmp_path):
    make_repo(tmp_path, {
        ".agy/ANTIGRAVITY.md": "agy file\n",
    })

    result = init_cmd.run(tmp_path)
    assert result["created"] is True
    assert result["detected"] == []
    assert len(result["discovery"]["unverified_local_candidate"]) == 1

    manifest = core.load_manifest(tmp_path)
    assert manifest.get("files", []) == []


def test_lookup_known_convention():
    # Test known convention matching
    conv = registry.lookup_known_convention(".github/copilot-instructions.md")
    assert conv is not None
    assert conv["tools"] == ["GitHub Copilot"]

    # Test unmatched convention
    assert registry.lookup_known_convention(".agy/ANTIGRAVITY.md") is None
    assert registry.lookup_known_convention("nonexistent.md") is None


def test_add_validates_manifest_exists(tmp_path):
    import pytest
    from superctx import add as add_cmd
    # Without init, add should raise AddError
    with pytest.raises(add_cmd.AddError) as exc_info:
        add_cmd.run(tmp_path, "somefile.md")
    assert "SuperCtx is not initialized in this project" in str(exc_info.value)


def test_add_validations_missing_and_directories(tmp_path):
    import pytest
    from superctx import add as add_cmd
    init_cmd.run(tmp_path)

    # Missing path validation
    with pytest.raises(add_cmd.AddError) as exc_info:
        add_cmd.run(tmp_path, "missing.md")
    assert "File does not exist" in str(exc_info.value)

    # Directory path validation
    folder_path = tmp_path / "folder"
    folder_path.mkdir()
    with pytest.raises(add_cmd.AddError) as exc_info:
        add_cmd.run(tmp_path, "folder")
    assert "Directories are not supported" in str(exc_info.value)

    # Outside project validation
    outside = tmp_path.parent / "outside.md"
    outside.write_text("x", encoding="utf-8")
    with pytest.raises(add_cmd.AddError) as exc_info:
        add_cmd.run(tmp_path, "../outside.md")
    assert "Path must be inside the project root" in str(exc_info.value)

    # Inside .ctx/ sources validation
    ctx_file = core.ctx_dir(tmp_path) / "sources" / "somefile.md"
    ctx_file.parent.mkdir(parents=True, exist_ok=True)
    ctx_file.write_text("x", encoding="utf-8")
    with pytest.raises(add_cmd.AddError) as exc_info:
        add_cmd.run(tmp_path, ".ctx/sources/somefile.md")
    assert "Cannot add files inside the .ctx directory" in str(exc_info.value)

    # Legit nested coincidental .ctx path (docs/.ctx/notes.md) should NOT be rejected
    nested_ctx_file = tmp_path / "docs" / ".ctx" / "notes.md"
    nested_ctx_file.parent.mkdir(parents=True, exist_ok=True)
    nested_ctx_file.write_text("notes\n", encoding="utf-8")
    res = add_cmd.run(tmp_path, "docs/.ctx/notes.md")
    assert res.status == "added"
    assert res.path == "docs/.ctx/notes.md"


def test_add_local_candidate_and_convention(tmp_path):
    from superctx import add as add_cmd
    from superctx.shim import is_shim_file
    init_cmd.run(tmp_path)

    # Add unrecognized candidate (.agy/ANTIGRAVITY.md)
    agy_file = tmp_path / ".agy/ANTIGRAVITY.md"
    agy_file.parent.mkdir(parents=True, exist_ok=True)
    agy_file.write_text("agy\n", encoding="utf-8")

    res = add_cmd.run(tmp_path, ".agy/ANTIGRAVITY.md")
    assert res.status == "added"
    assert res.tools == []
    assert ".agy/ANTIGRAVITY.md" in res.message
    assert "Edit .ctx/SUPERCTX.md directly to update instructions" not in res.message
    assert "backed up" in res.message and "shim" in res.message

    # Check manifest
    manifest = core.load_manifest(tmp_path)
    entry_agy = next(f for f in manifest["files"] if f["path"] == ".agy/ANTIGRAVITY.md")
    assert entry_agy["tools"] == []
    assert entry_agy["note"] == "user-confirmed local convention; not verified official path"

    # Check that it got shimmed and backed up
    assert is_shim_file(agy_file) is True
    assert (core.sources_dir(tmp_path) / ".agy/ANTIGRAVITY.md").read_text() == "agy\n"

    # Check hub has the incorporated content
    hub_content = core.hub_path(tmp_path).read_text(encoding="utf-8")
    assert "## From: .agy/ANTIGRAVITY.md\n\nagy" in hub_content

    # Add known convention (.github/copilot-instructions.md)
    copilot_file = tmp_path / ".github/copilot-instructions.md"
    copilot_file.parent.mkdir(parents=True, exist_ok=True)
    copilot_file.write_text("copilot\n", encoding="utf-8")

    res_conv = add_cmd.run(tmp_path, ".github/copilot-instructions.md")
    assert res_conv.status == "added"
    assert res_conv.tools == ["GitHub Copilot"]

    manifest2 = core.load_manifest(tmp_path)
    entry_copilot = next(f for f in manifest2["files"] if f["path"] == ".github/copilot-instructions.md")
    assert entry_copilot["tools"] == ["GitHub Copilot"]
    assert "note" not in entry_copilot

    assert is_shim_file(copilot_file) is True
    assert (core.sources_dir(tmp_path) / ".github/copilot-instructions.md").read_text() == "copilot\n"

    hub_content2 = core.hub_path(tmp_path).read_text(encoding="utf-8")
    assert "## From: .github/copilot-instructions.md  (GitHub Copilot)\n\ncopilot" in hub_content2

    # Duplicate add check (should be idempotent, shouldn't append section again or modify backup)
    res_dup = add_cmd.run(tmp_path, ".agy/ANTIGRAVITY.md")
    assert res_dup.status == "already_tracked"
    assert res_dup.tools == []
    assert "is already tracked" in res_dup.message

    # Verify no duplicate section in hub (should only appear once)
    hub_content_final = core.hub_path(tmp_path).read_text(encoding="utf-8")
    assert hub_content_final.count("## From: .agy/ANTIGRAVITY.md") == 1
    # Verify backup is still correct
    assert (core.sources_dir(tmp_path) / ".agy/ANTIGRAVITY.md").read_text() == "agy\n"


def test_add_backup_collision(tmp_path):
    import pytest
    from superctx import add as add_cmd
    init_cmd.run(tmp_path)

    # Create pre-existing backup
    backup_file = core.sources_dir(tmp_path) / "somefile.md"
    backup_file.parent.mkdir(parents=True, exist_ok=True)
    backup_file.write_text("backup content\n", encoding="utf-8")

    # Create live file (not a shim)
    live_file = tmp_path / "somefile.md"
    live_file.write_text("live content\n", encoding="utf-8")

    # Try to add it -> should raise AddError
    with pytest.raises(add_cmd.AddError) as exc_info:
        add_cmd.run(tmp_path, "somefile.md")
    assert "backup already exists" in str(exc_info.value).lower()
    assert "manually remove or rename the pre-existing backup file" not in str(exc_info.value)
    assert "inspect the conflict" in str(exc_info.value)


def test_add_already_shimmed_with_backup(tmp_path):
    from superctx import add as add_cmd
    from superctx.shim import is_shim_file, generate_shim
    init_cmd.run(tmp_path)

    # Set up an untracked, already-shimmed file
    # (Since it's not tracked, it is not in manifest.toml)
    live_file = tmp_path / "somefile.md"
    live_file.write_text(generate_shim("somefile.md", "plain-pointer"), encoding="utf-8")

    # Setup the backup file (original content)
    backup_file = core.sources_dir(tmp_path) / "somefile.md"
    backup_file.parent.mkdir(parents=True, exist_ok=True)
    backup_file.write_text("original non-shim content\n", encoding="utf-8")

    # Call add -> should succeed
    res = add_cmd.run(tmp_path, "somefile.md")
    assert res.status == "added"

    # Check that manifest is updated
    manifest = core.load_manifest(tmp_path)
    assert any(f["path"] == "somefile.md" for f in manifest["files"])

    # Check that the shim was regenerated
    assert is_shim_file(live_file) is True

    # Check that the hub incorporated the content from the BACKUP, not the SHIM text
    hub_content = core.hub_path(tmp_path).read_text(encoding="utf-8")
    assert "original non-shim content" in hub_content
    assert "Generated by SuperCtx" not in hub_content  # shouldn't have shim text in hub


def test_add_already_shimmed_no_backup(tmp_path):
    from superctx import add as add_cmd
    from superctx.shim import is_shim_file, generate_shim
    init_cmd.run(tmp_path)

    live_file = tmp_path / "somefile.md"
    live_file.write_text(generate_shim("somefile.md", "plain-pointer"), encoding="utf-8")

    # No backup exists
    res = add_cmd.run(tmp_path, "somefile.md")
    assert res.status == "added"

    # Check that manifest is updated
    manifest = core.load_manifest(tmp_path)
    assert any(f["path"] == "somefile.md" for f in manifest["files"])

    # Check that the shim is present
    assert is_shim_file(live_file) is True

    # Check that SUPERCTX.md does NOT have any new section for it (since original content is empty)
    hub_content = core.hub_path(tmp_path).read_text(encoding="utf-8")
    assert "## From: somefile.md" not in hub_content


def test_add_transactional_rollback(tmp_path, monkeypatch):
    import pytest
    from superctx import add as add_cmd
    from superctx import shim
    init_cmd.run(tmp_path)

    live_file = tmp_path / "somefile.md"
    live_file.write_text("some original content\n", encoding="utf-8")

    # Save original manifest and hub content
    orig_manifest = core.manifest_path(tmp_path).read_text(encoding="utf-8")
    orig_hub = core.hub_path(tmp_path).read_text(encoding="utf-8")

    # Mock apply_shim to raise an exception or fail
    def mock_apply_shim(*args, **kwargs):
        return {"shimmed": False, "reason": "mocked failure"}
    monkeypatch.setattr(shim, "apply_shim", mock_apply_shim)

    # Call add -> should fail and roll back manifest and hub
    with pytest.raises(add_cmd.AddError) as exc_info:
        add_cmd.run(tmp_path, "somefile.md")
    assert "Failed to apply shim: mocked failure" in str(exc_info.value)

    # Assert rollback
    assert core.manifest_path(tmp_path).read_text(encoding="utf-8") == orig_manifest
    assert core.hub_path(tmp_path).read_text(encoding="utf-8") == orig_hub

    # Live file is untouched (not shimmed)
    assert live_file.read_text(encoding="utf-8") == "some original content\n"


def test_add_transactional_rollback_restores_files_after_shim_write(tmp_path, monkeypatch):
    import pytest
    from superctx import add as add_cmd
    from superctx import shim
    init_cmd.run(tmp_path)

    live_file = tmp_path / "somefile.md"
    live_file.write_text("some original content\n", encoding="utf-8")
    backup_file = core.sources_dir(tmp_path) / "somefile.md"

    orig_manifest = core.manifest_path(tmp_path).read_text(encoding="utf-8")
    orig_hub = core.hub_path(tmp_path).read_text(encoding="utf-8")
    original_apply_shim = shim.apply_shim

    def apply_then_fail(*args, **kwargs):
        original_apply_shim(*args, **kwargs)
        raise RuntimeError("failure after shim write")

    monkeypatch.setattr(shim, "apply_shim", apply_then_fail)

    with pytest.raises(add_cmd.AddError) as exc_info:
        add_cmd.run(tmp_path, "somefile.md")
    assert "failure after shim write" in str(exc_info.value)

    assert core.manifest_path(tmp_path).read_text(encoding="utf-8") == orig_manifest
    assert core.hub_path(tmp_path).read_text(encoding="utf-8") == orig_hub
    assert live_file.read_text(encoding="utf-8") == "some original content\n"
    assert not backup_file.exists()


def test_init_manifest_decode_error(tmp_path):
    make_repo(tmp_path, {
        "CLAUDE.md": "x\n",
        ".ctx/manifest.toml": "invalid toml syntax = {broken\n"
    })
    result = init_cmd.run(tmp_path)
    assert result["created"] is False
    assert result["reason"] == "exists"
    assert result["partially_migrated"] is True
    assert "manifest_error" in result


# --- detect_repo_state ------------------------------------------------------

def test_detect_repo_state_not_candidate(tmp_path):
    from superctx.status import detect_repo_state
    # Empty directory
    res = detect_repo_state(tmp_path)
    assert res["state"] == "not_candidate"
    assert res["candidates"] == []
    assert res["reasons"] == ["no_known_instruction_files"]
    assert res["recommended_action"] == "none"
    assert res["recommended_action_mutates_files"] is False


def test_detect_repo_state_candidate_repo(tmp_path):
    from superctx.status import detect_repo_state
    # CLAUDE.md exists
    (tmp_path / "CLAUDE.md").write_text("context", encoding="utf-8")
    res = detect_repo_state(tmp_path)
    assert res["state"] == "candidate_repo"
    assert "CLAUDE.md" in res["candidates"]
    assert res["reasons"] == ["known_instruction_files_found"]
    assert res["recommended_action"] == "setup"
    assert res["recommended_action_mutates_files"] is True


def test_detect_repo_state_managed_healthy(tmp_path):
    from superctx.status import detect_repo_state
    from superctx import core, shim
    core.manifest_path(tmp_path).parent.mkdir(parents=True, exist_ok=True)
    core.manifest_path(tmp_path).write_text('[[files]]\npath = "CLAUDE.md"\ntools = ["Claude"]\n', encoding="utf-8")
    core.hub_path(tmp_path).write_text("# Shared Context", encoding="utf-8")

    # Write a valid generated shim
    shim_content = shim.generate_shim("CLAUDE.md", "claude-at-import")
    (tmp_path / "CLAUDE.md").write_text(shim_content, encoding="utf-8")

    (core.sources_dir(tmp_path) / "CLAUDE.md").parent.mkdir(parents=True, exist_ok=True)
    (core.sources_dir(tmp_path) / "CLAUDE.md").write_text("original content", encoding="utf-8")

    res = detect_repo_state(tmp_path)
    assert res["state"] == "managed_healthy"
    assert res["reasons"] == []
    assert res["recommended_action"] == "none"
    assert res["recommended_action_mutates_files"] is False


def test_detect_repo_state_managed_needs_repair(tmp_path):
    from superctx.status import detect_repo_state
    from superctx import core
    core.manifest_path(tmp_path).parent.mkdir(parents=True, exist_ok=True)
    core.manifest_path(tmp_path).write_text('[[files]]\npath = "CLAUDE.md"\ntools = ["Claude"]\n', encoding="utf-8")
    core.hub_path(tmp_path).write_text("# Shared Context", encoding="utf-8")
    # Live file is missing
    (core.sources_dir(tmp_path) / "CLAUDE.md").parent.mkdir(parents=True, exist_ok=True)
    (core.sources_dir(tmp_path) / "CLAUDE.md").write_text("original content", encoding="utf-8")

    res = detect_repo_state(tmp_path)
    assert res["state"] == "managed_needs_repair"
    assert "missing_shim" in res["reasons"]
    assert res["recommended_action"] == "repair"
    assert res["recommended_action_mutates_files"] is True


def test_detect_repo_state_managed_legacy(tmp_path):
    from superctx.status import detect_repo_state
    from superctx import core
    core.manifest_path(tmp_path).parent.mkdir(parents=True, exist_ok=True)
    core.manifest_path(tmp_path).write_text('[[files]]\npath = "CLAUDE.md"\ntools = ["Claude"]\n', encoding="utf-8")
    core.hub_path(tmp_path).write_text("# Shared Context", encoding="utf-8")
    # Live file is not a shim, and backup does NOT exist
    (tmp_path / "CLAUDE.md").write_text("full instructions text", encoding="utf-8")

    res = detect_repo_state(tmp_path)
    assert res["state"] == "managed_legacy"
    assert "unbacked_live_file" in res["reasons"]
    assert res["recommended_action"] == "migrate"
    assert res["recommended_action_mutates_files"] is True


def test_detect_repo_state_is_read_only(tmp_path):
    from superctx.status import detect_repo_state
    from superctx import core, shim

    (tmp_path / "CLAUDE.md").write_text("context", encoding="utf-8")

    def snapshot(dir_path):
        state = {}
        for path in sorted(dir_path.rglob("*")):
            if path.is_file():
                state[str(path.relative_to(dir_path))] = (path.read_bytes(), path.stat().st_mtime_ns)
            else:
                state[str(path.relative_to(dir_path))] = "dir"
        return state

    # Test candidate_repo path
    before_cand = snapshot(tmp_path)
    res_cand = detect_repo_state(tmp_path)
    assert res_cand["state"] == "candidate_repo"
    after_cand = snapshot(tmp_path)
    assert before_cand == after_cand

    # Setup healthy managed repo
    core.manifest_path(tmp_path).parent.mkdir(parents=True, exist_ok=True)
    core.manifest_path(tmp_path).write_text('[[files]]\npath = "CLAUDE.md"\ntools = ["Claude"]\n', encoding="utf-8")
    core.hub_path(tmp_path).write_text("# Shared Context", encoding="utf-8")
    shim_content = shim.generate_shim("CLAUDE.md", "claude-at-import")
    (tmp_path / "CLAUDE.md").write_text(shim_content, encoding="utf-8")
    (core.sources_dir(tmp_path) / "CLAUDE.md").parent.mkdir(parents=True, exist_ok=True)
    (core.sources_dir(tmp_path) / "CLAUDE.md").write_text("original content", encoding="utf-8")

    # Test managed_healthy path
    before_managed = snapshot(tmp_path)
    res_managed = detect_repo_state(tmp_path)
    assert res_managed["state"] == "managed_healthy"
    after_managed = snapshot(tmp_path)
    assert before_managed == after_managed



def test_cli_status_detect(tmp_path):
    from superctx.__main__ import main
    import sys
    import json
    from io import StringIO

    orig_argv = sys.argv
    orig_stdout = sys.stdout
    try:
        sys.argv = ["superctx", "status", "--detect"]
        sys.stdout = StringIO()
        import os
        orig_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            exit_code = main()
            assert exit_code == 0
            output = sys.stdout.getvalue()
            data = json.loads(output)
            assert data["state"] == "not_candidate"
        finally:
            os.chdir(orig_cwd)
    finally:
        sys.argv = orig_argv
        sys.stdout = orig_stdout


def test_detect_repo_state_managed_legacy_manifest_missing(tmp_path):
    from superctx.status import detect_repo_state
    from superctx import core

    # Create .ctx directory but no manifest
    core.ctx_dir(tmp_path).mkdir(parents=True, exist_ok=True)

    # Create unbacked live file
    (tmp_path / "CLAUDE.md").write_text("live content", encoding="utf-8")

    res = detect_repo_state(tmp_path)
    assert res["state"] == "managed_legacy"
    assert "manifest_missing" in res["reasons"]
    assert "unbacked_live_file" in res["reasons"]
    assert res["recommended_action"] == "migrate"


def test_detect_repo_state_managed_needs_repair_missing_both(tmp_path):
    from superctx.status import detect_repo_state
    from superctx import core
    core.manifest_path(tmp_path).parent.mkdir(parents=True, exist_ok=True)
    core.manifest_path(tmp_path).write_text('[[files]]\npath = "CLAUDE.md"\ntools = ["Claude"]\n', encoding="utf-8")
    core.hub_path(tmp_path).write_text("# Shared Context", encoding="utf-8")

    # Live shim CLAUDE.md is not created, and backup is not created either.
    res = detect_repo_state(tmp_path)
    assert res["state"] == "managed_needs_repair"
    assert "missing_shim" in res["reasons"]
    assert "missing_backup" in res["reasons"]
    assert res["recommended_action"] == "repair"


def test_detect_repo_state_managed_unreadable_manifest(tmp_path):
    from superctx.status import detect_repo_state
    from superctx import core
    core.ctx_dir(tmp_path).mkdir(parents=True, exist_ok=True)
    # Write syntactically invalid TOML
    core.manifest_path(tmp_path).write_text("invalid toml syntax = {broken\n", encoding="utf-8")

    # Create unbacked live file to see if it lists as candidate
    (tmp_path / "CLAUDE.md").write_text("live content", encoding="utf-8")

    res = detect_repo_state(tmp_path)
    assert res["state"] == "managed_needs_repair"
    assert res["reasons"] == ["manifest_unreadable"]
    assert "CLAUDE.md" in res["candidates"]
    assert res["recommended_action"] == "inspect"
    assert res["recommended_action_mutates_files"] is False


def test_detect_repo_state_managed_invalid_manifest(tmp_path):
    from superctx.status import detect_repo_state
    from superctx import core
    core.ctx_dir(tmp_path).mkdir(parents=True, exist_ok=True)

    # Case A: files is not a list
    core.manifest_path(tmp_path).write_text("files = 'not a list'\n", encoding="utf-8")
    res = detect_repo_state(tmp_path)
    assert res["state"] == "managed_needs_repair"
    assert res["reasons"] == ["manifest_invalid"]
    assert res["recommended_action"] == "inspect"
    assert res["recommended_action_mutates_files"] is False

    # Case B: file entry lacks a valid path
    core.manifest_path(tmp_path).write_text("[[files]]\npath = ''\n", encoding="utf-8")
    res = detect_repo_state(tmp_path)
    assert res["state"] == "managed_needs_repair"
    assert res["reasons"] == ["manifest_invalid"]
    assert res["recommended_action"] == "inspect"
    assert res["recommended_action_mutates_files"] is False

    # Case C: tools is not a list
    core.manifest_path(tmp_path).write_text("[[files]]\npath = 'CLAUDE.md'\ntools = 'not a list'\n", encoding="utf-8")
    res = detect_repo_state(tmp_path)
    assert res["state"] == "managed_needs_repair"
    assert res["reasons"] == ["manifest_invalid"]
    assert res["recommended_action"] == "inspect"
    assert res["recommended_action_mutates_files"] is False


def test_cli_status_detect_manifest_errors(tmp_path):
    from superctx.__main__ import main
    import sys
    import json
    from io import StringIO
    from superctx import core

    orig_argv = sys.argv
    orig_stdout = sys.stdout
    try:
        sys.argv = ["superctx", "status", "--detect"]
        sys.stdout = StringIO()
        import os
        orig_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            core.ctx_dir(tmp_path).mkdir(parents=True, exist_ok=True)

            # 1. Malformed TOML
            core.manifest_path(tmp_path).write_text("invalid toml syntax = {broken\n", encoding="utf-8")
            sys.stdout = StringIO()
            exit_code = main()
            assert exit_code == 0
            data = json.loads(sys.stdout.getvalue())
            assert data["state"] == "managed_needs_repair"
            assert data["reasons"] == ["manifest_unreadable"]
            assert data["recommended_action"] == "inspect"
            assert data["recommended_action_mutates_files"] is False

            # 2. Schema-invalid TOML
            core.manifest_path(tmp_path).write_text("files = 'not a list'\n", encoding="utf-8")
            sys.stdout = StringIO()
            exit_code = main()
            assert exit_code == 0
            data = json.loads(sys.stdout.getvalue())
            assert data["state"] == "managed_needs_repair"
            assert data["reasons"] == ["manifest_invalid"]
            assert data["recommended_action"] == "inspect"
            assert data["recommended_action_mutates_files"] is False
        finally:
            os.chdir(orig_cwd)
    finally:
        sys.argv = orig_argv
        sys.stdout = orig_stdout


def test_cli_status_manifest_errors_no_detect(tmp_path):
    from superctx.__main__ import main
    import sys
    from io import StringIO
    from superctx import core

    orig_argv = sys.argv
    orig_stdout = sys.stdout
    try:
        sys.argv = ["superctx", "status"]
        sys.stdout = StringIO()
        import os
        orig_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            core.ctx_dir(tmp_path).mkdir(parents=True, exist_ok=True)

            # 1. Malformed TOML
            core.manifest_path(tmp_path).write_text("invalid toml syntax = {broken\n", encoding="utf-8")
            sys.stdout = StringIO()
            exit_code = main()
            assert exit_code == 0
            output = sys.stdout.getvalue()
            assert "configuration manifest or hub is missing or invalid" in output
            assert "offer to inspect the setup" in output

            # 2. Schema-invalid TOML
            core.manifest_path(tmp_path).write_text("files = 'not a list'\n", encoding="utf-8")
            sys.stdout = StringIO()
            exit_code = main()
            assert exit_code == 0
            output = sys.stdout.getvalue()
            assert "configuration manifest is invalid" in output
            assert "offer to inspect the setup" in output
        finally:
            os.chdir(orig_cwd)
    finally:
        sys.argv = orig_argv
        sys.stdout = orig_stdout


def test_cli_status_agent_guided_output_paths(tmp_path):
    from superctx.__main__ import main
    import sys
    from io import StringIO
    from superctx import core

    orig_argv = sys.argv
    orig_stdout = sys.stdout
    try:
        import os
        orig_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            # 1. Candidate repo
            d_cand = tmp_path / "cand"
            d_cand.mkdir()
            (d_cand / ".claude").mkdir()
            (d_cand / ".claude" / "CLAUDE.md").write_text("# Instructions", encoding="utf-8")

            os.chdir(d_cand)
            sys.argv = ["superctx", "status"]
            sys.stdout = StringIO()
            exit_code = main()
            assert exit_code == 0
            output = sys.stdout.getvalue()
            assert "Detected candidate instruction files" in output
            assert "Recommended action: Offer to set up SuperCtx (with explicit consent)." in output
            assert "/superctx:init" not in output

            # 2. Broken shim
            d_broken = tmp_path / "broken"
            d_broken.mkdir()
            (d_broken / ".claude").mkdir()
            (d_broken / ".claude" / "CLAUDE.md").write_text("# Instructions", encoding="utf-8")
            os.chdir(d_broken)
            main(["init"])
            # Break shim
            (d_broken / ".claude" / "CLAUDE.md").write_text("broken shim content", encoding="utf-8")

            sys.argv = ["superctx", "status"]
            sys.stdout = StringIO()
            exit_code = main()
            assert exit_code == 0
            output = sys.stdout.getvalue()
            assert "Shim issues" in output
            assert "Recommended action: Offer to repair shims (with explicit consent)." in output
            assert "/superctx:sync" not in output

            # 3. Untracked candidate
            d_untracked = tmp_path / "untracked"
            d_untracked.mkdir()
            (d_untracked / ".claude").mkdir()
            (d_untracked / ".claude" / "CLAUDE.md").write_text("# Instructions", encoding="utf-8")
            os.chdir(d_untracked)
            main(["init"])
            # Create untracked local convention candidate
            (d_untracked / ".agy").mkdir()
            (d_untracked / ".agy" / "ANTIGRAVITY.md").write_text("# Instructions", encoding="utf-8")

            sys.argv = ["superctx", "status"]
            sys.stdout = StringIO()
            exit_code = main()
            assert exit_code == 0
            output = sys.stdout.getvalue()
            assert "Untracked candidates" in output
            assert "Recommended action: Offer to connect this file (with explicit consent)." in output
            assert "/superctx:add" not in output

            # 4. Missing hub
            d_mishub = tmp_path / "mishub"
            d_mishub.mkdir()
            (d_mishub / ".claude").mkdir()
            (d_mishub / ".claude" / "CLAUDE.md").write_text("# Instructions", encoding="utf-8")
            os.chdir(d_mishub)
            main(["init"])
            # Delete hub
            core.hub_path(d_mishub).unlink()

            sys.argv = ["superctx", "status"]
            sys.stdout = StringIO()
            exit_code = main()
            assert exit_code == 0
            output = sys.stdout.getvalue()
            assert "Hub missing" in output
            assert "Recommended action: Explain the problem and offer to inspect the setup (automatic recovery not supported)." in output
            assert "/superctx:init" not in output

            # 5. Legacy state
            d_legacy = tmp_path / "legacy"
            d_legacy.mkdir()
            os.chdir(d_legacy)
            core.ctx_dir(d_legacy).mkdir()
            core.manifest_path(d_legacy).write_text('[[files]]\npath = "CLAUDE.md"\ntools = ["Claude"]\n', encoding="utf-8")
            (d_legacy / "CLAUDE.md").write_text("unbacked legacy contents", encoding="utf-8")

            sys.argv = ["superctx", "status"]
            sys.stdout = StringIO()
            exit_code = main()
            assert exit_code == 0
            output = sys.stdout.getvalue()
            assert "SuperCtx is present, but some instruction files are legacy" in output
            assert "Recommended action: Offer to migrate/recover the legacy SuperCtx setup (with explicit consent)." in output
        finally:
            os.chdir(orig_cwd)
    finally:
        sys.argv = orig_argv
        sys.stdout = orig_stdout


def test_cli_status_corrupt_non_utf8_hub_no_traceback(tmp_path):
    from superctx.__main__ import main
    import sys
    from io import StringIO
    from superctx import core

    orig_argv = sys.argv
    orig_stdout = sys.stdout
    try:
        sys.argv = ["superctx", "status"]
        sys.stdout = StringIO()
        import os
        orig_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            core.ctx_dir(tmp_path).mkdir(parents=True, exist_ok=True)
            core.manifest_path(tmp_path).write_text('[[files]]\npath = "CLAUDE.md"\ntools = ["Claude"]\n', encoding="utf-8")
            # Write invalid UTF-8 bytes to SUPERCTX.md
            core.hub_path(tmp_path).write_bytes(b"\x80\xff\xfe")

            sys.stdout = StringIO()
            exit_code = main()
            assert exit_code == 0
            output = sys.stdout.getvalue()
            assert "configuration manifest or hub is missing or invalid" in output
            assert "offer to inspect the setup" in output
        finally:
            os.chdir(orig_cwd)
    finally:
        sys.argv = orig_argv
        sys.stdout = orig_stdout





def test_sync_manifest_errors(tmp_path):
    import pytest
    from superctx.sync import run, SyncError
    from superctx import core
    core.ctx_dir(tmp_path).mkdir(parents=True, exist_ok=True)

    # 1. Malformed TOML syntax
    core.manifest_path(tmp_path).write_text("invalid toml syntax = {broken\n", encoding="utf-8")
    with pytest.raises(SyncError) as exc:
        run(tmp_path)
    assert "unreadable" in str(exc.value)

    # 2. Schema-invalid manifest (files is not a list)
    core.manifest_path(tmp_path).write_text("files = 'not a list'\n", encoding="utf-8")
    with pytest.raises(SyncError) as exc:
        run(tmp_path)
    assert "invalid" in str(exc.value)


def test_detect_repo_state_managed_needs_repair_manifest_missing(tmp_path):
    from superctx.status import detect_repo_state
    from superctx import core

    # Create .ctx directory but no manifest
    core.ctx_dir(tmp_path).mkdir(parents=True, exist_ok=True)

    # No live files exist

    res = detect_repo_state(tmp_path)
    assert res["state"] == "managed_needs_repair"
    assert "manifest_missing" in res["reasons"]
    assert res["recommended_action"] == "inspect"
    assert res["recommended_action_mutates_files"] is False


def test_manifest_path_traversal_validation(tmp_path):
    import pytest
    from superctx import core
    from superctx.core import SchemaError

    core.ctx_dir(tmp_path).mkdir(parents=True, exist_ok=True)

    # 1. Absolute path traversal
    core.manifest_path(tmp_path).write_text("[[files]]\npath = '/etc/passwd'\n", encoding="utf-8")
    with pytest.raises(SchemaError) as exc:
        core.load_manifest(tmp_path)
    assert "absolute" in str(exc.value)

    # 2. Relative path traversal (escaping root)
    core.manifest_path(tmp_path).write_text("[[files]]\npath = '../outside.md'\n", encoding="utf-8")
    with pytest.raises(SchemaError) as exc:
        core.load_manifest(tmp_path)
    assert "escapes repository root" in str(exc.value)

    # 3. Double dot traversal resolving outside
    core.manifest_path(tmp_path).write_text("[[files]]\npath = 'a/../../outside.md'\n", encoding="utf-8")
    with pytest.raises(SchemaError) as exc:
        core.load_manifest(tmp_path)
    assert "escapes repository root" in str(exc.value)

    # 4. Healthy path in manifest loads successfully
    core.manifest_path(tmp_path).write_text("[[files]]\npath = 'a/b/healthy.md'\n", encoding="utf-8")
    data = core.load_manifest(tmp_path)
    assert data["files"][0]["path"] == "a/b/healthy.md"


def test_hook_session_start_states(tmp_path):
    import subprocess
    import os
    from superctx import core, shim

    import sys
    hook_path = Path(__file__).resolve().parent.parent / "hooks" / "session-start"
    assert hook_path.is_file()

    env = os.environ.copy()
    env["CLAUDE_PLUGIN_ROOT"] = str(Path(__file__).resolve().parent.parent)
    env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + env.get("PATH", "")

    # 1. Unreadable/Invalid manifest -> state managed_needs_repair, action inspect
    d1 = tmp_path / "case1"
    core.ctx_dir(d1).mkdir(parents=True, exist_ok=True)
    core.manifest_path(d1).write_text("invalid toml syntax = {broken\n", encoding="utf-8")

    res1 = subprocess.run(
        ["bash", str(hook_path)],
        cwd=d1,
        env=env,
        capture_output=True,
        text=True
    )
    assert res1.returncode == 0
    assert "configuration manifest is missing or invalid" in res1.stdout
    assert "/superctx:status" not in res1.stdout
    assert "offer to inspect" in res1.stdout

    # 2. Healthy setup -> state managed_healthy, action none
    d2 = tmp_path / "case2"
    core.ctx_dir(d2).mkdir(parents=True, exist_ok=True)
    core.manifest_path(d2).write_text('[[files]]\npath = "CLAUDE.md"\ntools = ["Claude"]\n', encoding="utf-8")
    core.hub_path(d2).write_text("# Shared Context", encoding="utf-8")
    shim_content = shim.generate_shim("CLAUDE.md", "claude-at-import")
    (d2 / "CLAUDE.md").write_text(shim_content, encoding="utf-8")
    (core.sources_dir(d2) / "CLAUDE.md").parent.mkdir(parents=True, exist_ok=True)
    (core.sources_dir(d2) / "CLAUDE.md").write_text("original content", encoding="utf-8")

    res2 = subprocess.run(
        ["bash", str(hook_path)],
        cwd=d2,
        env=env,
        capture_output=True,
        text=True
    )
    assert res2.returncode == 0
    assert "SuperCtx is active" in res2.stdout
    assert "canonical shared project context" in res2.stdout

    # 3. Needs repair (broken shim) -> state managed_needs_repair, action repair
    d3 = tmp_path / "case3"
    core.ctx_dir(d3).mkdir(parents=True, exist_ok=True)
    core.manifest_path(d3).write_text('[[files]]\npath = "CLAUDE.md"\ntools = ["Claude"]\n', encoding="utf-8")
    core.hub_path(d3).write_text("# Shared Context", encoding="utf-8")
    (d3 / "CLAUDE.md").write_text("broken content", encoding="utf-8")  # Not a shim
    (core.sources_dir(d3) / "CLAUDE.md").parent.mkdir(parents=True, exist_ok=True)
    (core.sources_dir(d3) / "CLAUDE.md").write_text("original content", encoding="utf-8")

    res3 = subprocess.run(
        ["bash", str(hook_path)],
        cwd=d3,
        env=env,
        capture_output=True,
        text=True
    )
    assert res3.returncode == 0
    assert "installation has broken or missing shims" in res3.stdout
    assert "/superctx:status" not in res3.stdout
    assert "offer to repair the shims" in res3.stdout

    # 4. Candidate repo -> state candidate_repo, consent-based offer with file list
    d4 = tmp_path / "case4"
    d4.mkdir()
    # Write a known instruction file so detection fires
    claude_dir = d4 / ".claude"
    claude_dir.mkdir()
    (claude_dir / "CLAUDE.md").write_text("# Instructions", encoding="utf-8")

    res4 = subprocess.run(
        ["bash", str(hook_path)],
        cwd=d4,
        env=env,
        capture_output=True,
        text=True
    )
    assert res4.returncode == 0
    assert "setup opportunity" in res4.stdout
    assert ".claude/CLAUDE.md" in res4.stdout
    assert "explicit consent" in res4.stdout
    assert "`.ctx/SUPERCTX.md`" in res4.stdout
    assert "`.ctx/sources/`" in res4.stdout
    assert "generated shims" in res4.stdout
    # Must NOT mention /superctx:init at all — user should not need to type a command
    assert "/superctx:init" not in res4.stdout


def test_version_consistency():
    import json
    from pathlib import Path
    from superctx import __version__

    root = Path(__file__).parent.parent
    # 1. pyproject.toml
    pyproject = root / "pyproject.toml"
    assert f'version = "{__version__}"' in pyproject.read_text(encoding="utf-8")
    # 2. plugin.json
    plugin_j = root / ".claude-plugin" / "plugin.json"
    assert json.loads(plugin_j.read_text(encoding="utf-8"))["version"] == __version__
    # 3. marketplace.json
    market_j = root / ".claude-plugin" / "marketplace.json"
    market_data = json.loads(market_j.read_text(encoding="utf-8"))
    assert market_data["plugins"][0]["version"] == __version__
