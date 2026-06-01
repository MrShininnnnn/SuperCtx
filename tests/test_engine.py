"""Unit tests for the SuperCtx engine (init / sync / status) using temp project dirs."""

from importlib import resources
from pathlib import Path

from superctx import core, init as init_cmd, registry, status as status_cmd, sync as sync_cmd


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
    assert set(result["detected"]) == {"CLAUDE.md", "AGENTS.md"}
    assert core.manifest_path(tmp_path).is_file()
    assert core.hub_path(tmp_path).is_file()
    assert (core.ctx_dir(tmp_path) / ".gitignore").read_text().strip().endswith("sources/")

    manifest = core.load_manifest(tmp_path)
    assert {f["path"] for f in manifest["files"]} == {"CLAUDE.md", "AGENTS.md"}
    # tools metadata is carried over from the registry
    claude = next(f for f in manifest["files"] if f["path"] == "CLAUDE.md")
    assert claude["tools"] == ["Claude Code"]


def test_init_ignores_unrelated_files(tmp_path):
    make_repo(tmp_path, {"CLAUDE.md": "x\n", "README.md": "not a tool file\n"})
    result = init_cmd.run(tmp_path)
    assert result["detected"] == ["CLAUDE.md"]


def test_init_detects_hidden_instruction_files(tmp_path):
    make_repo(tmp_path, {
        ".claude/CLAUDE.md": "claude hidden\n",
        ".codex/AGENTS.md": "codex hidden\n",
        ".agy/ANTIGRAVITY.md": "agy hidden\n",
        "AGENTS.md": "root agents\n"
    })
    result = init_cmd.run(tmp_path)
    assert result["created"] is True
    assert set(result["detected"]) == {
        ".claude/CLAUDE.md",
        ".codex/AGENTS.md",
        "AGENTS.md"
    }

    # Run sync to centralize the detected hidden files
    sync_result = sync_cmd.run(tmp_path)
    assert set(sync_result["centralized"]) == {
        ".claude/CLAUDE.md",
        ".codex/AGENTS.md",
        "AGENTS.md"
    }
    assert sync_result["missing"] == []

    # Verify status reports them as synced
    status_rows = [r for r in status_cmd.run(tmp_path) if r["state"] != "untracked_candidate"]
    assert len(status_rows) == 3
    for row in status_rows:
        assert row["state"] == "synced"

    manifest = core.load_manifest(tmp_path)
    files = {entry["path"]: entry for entry in manifest["files"]}
    assert files[".claude/CLAUDE.md"]["tools"] == ["Claude Code"]
    assert files[".codex/AGENTS.md"]["tools"] == ["OpenAI Codex"]
    assert files["AGENTS.md"]["tools"] == [
        "OpenAI Codex", "Cursor", "GitHub Copilot", "Windsurf", "Aider",
        "Zed", "Jules", "Devin", "Gemini CLI (opt-in)"
    ]
    assert ".agy/ANTIGRAVITY.md" not in files

    # Verify the generated hub file includes proper provenance headers and contents
    hub_content = core.hub_path(tmp_path).read_text(encoding="utf-8")
    assert "## From: .claude/CLAUDE.md" in hub_content
    assert "claude hidden" in hub_content
    assert "## From: .codex/AGENTS.md" in hub_content
    assert "codex hidden" in hub_content
    assert "## From: AGENTS.md" in hub_content
    assert "root agents" in hub_content


def test_init_is_idempotent(tmp_path):
    make_repo(tmp_path, {"CLAUDE.md": "x\n"})
    init_cmd.run(tmp_path)
    again = init_cmd.run(tmp_path)
    assert again["created"] is False
    assert again["reason"] == "exists"


# --- sync -------------------------------------------------------------------

def test_sync_centralizes_with_provenance(tmp_path):
    make_repo(tmp_path, {"CLAUDE.md": "# Claude\nhello\n", "AGENTS.md": "# Agents\nworld\n"})
    init_cmd.run(tmp_path)
    result = sync_cmd.run(tmp_path)

    assert set(result["centralized"]) == {"CLAUDE.md", "AGENTS.md"}
    assert (core.sources_dir(tmp_path) / "CLAUDE.md").is_file()

    hub = core.hub_path(tmp_path).read_text()
    assert "## From: CLAUDE.md  (Claude Code)" in hub
    assert "hello" in hub and "world" in hub


def test_sync_reports_missing_tracked_file(tmp_path):
    make_repo(tmp_path, {"CLAUDE.md": "a\n"})
    init_cmd.run(tmp_path)
    (tmp_path / "CLAUDE.md").unlink()
    result = sync_cmd.run(tmp_path)
    assert result["centralized"] == []
    assert result["missing"] == ["CLAUDE.md"]


def test_sync_mirrors_nested_same_basename(tmp_path):
    make_repo(tmp_path, {"CLAUDE.md": "root\n", "packages/foo/CLAUDE.md": "nested\n"})
    init_cmd.run(tmp_path)
    # auto-detect only finds root CLAUDE.md; add the nested path by hand to exercise mirroring
    manifest = core.load_manifest(tmp_path)
    manifest["files"].append({"path": "packages/foo/CLAUDE.md", "tools": ["Claude Code"]})
    core.manifest_path(tmp_path).write_text(core.dump_manifest(manifest), encoding="utf-8")

    sync_cmd.run(tmp_path)
    assert (core.sources_dir(tmp_path) / "CLAUDE.md").read_text().strip() == "root"
    assert (core.sources_dir(tmp_path) / "packages/foo/CLAUDE.md").read_text().strip() == "nested"


# --- status -----------------------------------------------------------------

def states(tmp_path) -> dict[str, str]:
    return {row["path"]: row["state"] for row in status_cmd.run(tmp_path)}


def test_status_synced_then_drifted(tmp_path):
    make_repo(tmp_path, {"CLAUDE.md": "a\n"})
    init_cmd.run(tmp_path)
    sync_cmd.run(tmp_path)
    assert states(tmp_path)["CLAUDE.md"] == "synced"

    (tmp_path / "CLAUDE.md").write_text("a changed\n", encoding="utf-8")
    assert states(tmp_path)["CLAUDE.md"] == "drifted"


def test_status_ignores_cosmetic_whitespace(tmp_path):
    make_repo(tmp_path, {"CLAUDE.md": "a\n"})
    init_cmd.run(tmp_path)
    sync_cmd.run(tmp_path)
    # trailing whitespace + CRLF should normalize away -> still synced
    (tmp_path / "CLAUDE.md").write_text("a   \r\n", encoding="utf-8")
    assert states(tmp_path)["CLAUDE.md"] == "synced"


def test_status_missing_and_untracked(tmp_path):
    make_repo(tmp_path, {"CLAUDE.md": "a\n"})
    init_cmd.run(tmp_path)
    sync_cmd.run(tmp_path)

    (tmp_path / "GEMINI.md").write_text("g\n", encoding="utf-8")  # known convention, not tracked
    (tmp_path / "CLAUDE.md").unlink()  # tracked, now gone

    result = states(tmp_path)
    assert result["CLAUDE.md"] == "missing"
    assert result["GEMINI.md"] == "untracked"


def test_status_drifted_when_never_synced(tmp_path):
    make_repo(tmp_path, {"CLAUDE.md": "a\n"})
    init_cmd.run(tmp_path)  # no sync yet
    assert states(tmp_path)["CLAUDE.md"] == "drifted"


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
