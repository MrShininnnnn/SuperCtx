"""Tests for marketplace polish blockers (issue #68)."""

from __future__ import annotations

from pathlib import Path

from superctx import core, init as init_cmd, status as status_cmd


def make_repo(tmp_path: Path, files: dict) -> Path:
    for rel, content in files.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return tmp_path


# ---------------------------------------------------------------------------
# Blocker 2: Python 3.9/3.10 TOML import fallback
# ---------------------------------------------------------------------------

def test_core_load_manifest_roundtrip(tmp_path):
    """Verify manifest loading works (exercises the tomllib/tomli import path)."""
    ctx_dir = core.ctx_dir(tmp_path)
    ctx_dir.mkdir(parents=True)
    core.manifest_path(tmp_path).write_text(
        '[project]\nname = "test"\nhub = ".ctx/SUPERCTX.md"\n',
        encoding="utf-8",
    )
    data = core.load_manifest(tmp_path)
    assert data["project"]["name"] == "test"


def test_registry_load_conventions_uses_toml():
    """Verify registry.load_conventions() works (exercises the tomllib/tomli import path)."""
    from superctx import registry
    convs = registry.load_conventions()
    assert len(convs) > 0
    paths = [c["path"] for c in convs]
    assert "CLAUDE.md" in paths
    assert "GEMINI.md" in paths


def test_source_runtime_works_without_tomllib_or_tomli(tmp_path):
    """The plugin source path must work even when tomllib/tomli are unavailable."""
    import os
    import subprocess
    import sys
    import textwrap

    project = tmp_path / "project"
    ctx_dir = project / ".ctx"
    ctx_dir.mkdir(parents=True)
    (ctx_dir / "manifest.toml").write_text(
        '[project]\nname = "fallback"\nhub = ".ctx/SUPERCTX.md"\n\n'
        '[[files]]\npath = "GEMINI.md"\ntools = ["Gemini CLI"]\n',
        encoding="utf-8",
    )

    sitecustomize_dir = tmp_path / "sitecustomize"
    sitecustomize_dir.mkdir()
    (sitecustomize_dir / "sitecustomize.py").write_text(
        textwrap.dedent(
            """
            import builtins

            _real_import = builtins.__import__

            def _blocked_import(name, globals=None, locals=None, fromlist=(), level=0):
                if name in {"tomllib", "tomli"}:
                    raise ModuleNotFoundError(name)
                return _real_import(name, globals, locals, fromlist, level)

            builtins.__import__ = _blocked_import
            """
        ),
        encoding="utf-8",
    )

    script = textwrap.dedent(
        f"""
        from pathlib import Path
        from superctx import core, registry

        project = Path({str(project)!r})
        manifest = core.load_manifest(project)
        conventions = registry.load_conventions()

        assert manifest["project"]["name"] == "fallback"
        assert manifest["files"][0]["path"] == "GEMINI.md"
        assert any(c["path"] == "GEMINI.md" for c in conventions)
        print("fallback ok")
        """
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join([str(sitecustomize_dir), str(Path.cwd() / "scripts")])

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "fallback ok" in result.stdout


# ---------------------------------------------------------------------------
# Blocker 3: Agent-native hub banner wording
# ---------------------------------------------------------------------------

def test_hub_banner_is_agent_native(tmp_path):
    """Generated hubs must use agent-native wording, not manual-edit wording."""
    make_repo(tmp_path, {"CLAUDE.md": "ctx\n"})
    init_cmd.run(tmp_path)

    hub_text = core.hub_path(tmp_path).read_text(encoding="utf-8")

    assert "managed by SuperCtx" in hub_text
    assert "Edit this file to update instructions" not in hub_text


def test_add_hub_section_uses_agent_native_banner(tmp_path):
    """add command preserves agent-native banner wording when adding sections."""
    from superctx import add as add_cmd
    make_repo(tmp_path, {"CLAUDE.md": "ctx\n"})
    init_cmd.run(tmp_path)

    agy_file = tmp_path / ".agy" / "ANTIGRAVITY.md"
    agy_file.parent.mkdir(parents=True, exist_ok=True)
    agy_file.write_text("rules\n", encoding="utf-8")

    add_cmd.run(tmp_path, ".agy/ANTIGRAVITY.md")
    hub_text = core.hub_path(tmp_path).read_text(encoding="utf-8")

    assert "managed by SuperCtx" in hub_text
    assert "Edit this file to update instructions" not in hub_text


# ---------------------------------------------------------------------------
# Blocker 4: Missing standard tool file (GEMINI.md) handling
# ---------------------------------------------------------------------------

def test_add_missing_file_raises_without_create_shim(tmp_path):
    """add.run raises AddError for non-existent file without create_if_missing."""
    import pytest
    from superctx import add as add_cmd
    init_cmd.run(tmp_path)

    with pytest.raises(add_cmd.AddError) as exc_info:
        add_cmd.run(tmp_path, "GEMINI.md")
    assert "File does not exist" in str(exc_info.value)


def test_add_missing_known_convention_with_create_shim(tmp_path):
    """add.run creates a shim for a non-existent known-convention file."""
    from superctx import add as add_cmd
    from superctx.shim import is_shim_file
    init_cmd.run(tmp_path)

    assert not (tmp_path / "GEMINI.md").is_file()

    res = add_cmd.run(tmp_path, "GEMINI.md", create_if_missing=True)

    assert res.status == "added"
    assert res.path == "GEMINI.md"
    assert "GEMINI.md" in res.message
    # Created (not "backed up") wording for a new shim
    assert "created" in res.message.lower()

    # Shim must exist and be valid
    assert is_shim_file(tmp_path / "GEMINI.md")

    # Manifest must include GEMINI.md with correct tools metadata
    manifest = core.load_manifest(tmp_path)
    entry = next((f for f in manifest.get("files", []) if f["path"] == "GEMINI.md"), None)
    assert entry is not None
    assert "Gemini CLI" in entry["tools"]
    assert entry["backup_required"] is False

    # No backup should be created (nothing to back up)
    assert not (core.sources_dir(tmp_path) / "GEMINI.md").is_file()


def test_add_missing_nested_convention_with_create_shim(tmp_path):
    """add.run creates a shim for a non-existent nested known-convention file."""
    from superctx import add as add_cmd
    from superctx.shim import is_shim_file
    init_cmd.run(tmp_path)

    assert not (tmp_path / ".codex" / "AGENTS.md").is_file()

    res = add_cmd.run(tmp_path, ".codex/AGENTS.md", create_if_missing=True)

    assert res.status == "added"
    assert is_shim_file(tmp_path / ".codex" / "AGENTS.md")

    manifest = core.load_manifest(tmp_path)
    assert any(f["path"] == ".codex/AGENTS.md" for f in manifest.get("files", []))


def test_add_missing_unknown_convention_with_create_shim_raises(tmp_path):
    """add.run raises AddError for create_if_missing on an unknown convention path."""
    import pytest
    from superctx import add as add_cmd
    init_cmd.run(tmp_path)

    with pytest.raises(add_cmd.AddError) as exc_info:
        add_cmd.run(tmp_path, "some-random-file.md", create_if_missing=True)
    assert "not a recognized standard convention" in str(exc_info.value)


def test_add_missing_gemini_status_healthy(tmp_path):
    """After creating GEMINI.md shim, internal status reports Gemini as healthy."""
    from superctx import add as add_cmd
    init_cmd.run(tmp_path)

    add_cmd.run(tmp_path, "GEMINI.md", create_if_missing=True)

    rows = status_cmd.run(tmp_path)
    gemini_shim = next(
        (r for r in rows if r["kind"] == "shim" and r["path"] == "GEMINI.md"), None
    )
    gemini_backup = next(
        (r for r in rows if r["kind"] == "backup" and r.get("source") == "GEMINI.md"), None
    )
    assert gemini_shim is not None
    assert gemini_shim["state"] == "healthy"
    assert gemini_backup is None
    assert not any(r["state"] != "healthy" for r in rows)


def test_cli_add_create_shim_flag(tmp_path):
    """CLI --create-shim flag creates a shim for a non-existent known-convention file."""
    import os
    from superctx.__main__ import main
    from superctx.shim import is_shim_file
    from superctx import sync as sync_cmd

    orig_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        init_cmd.run(tmp_path)
        exit_code = main(["add", "--create-shim", "GEMINI.md"])
        assert exit_code == 0
        assert is_shim_file(tmp_path / "GEMINI.md")
        sync_result = sync_cmd.run(tmp_path)
        assert sync_result["mode"] == "healthy"
        assert "GEMINI.md" in sync_result["healthy"]
        assert "warnings" not in sync_result
    finally:
        os.chdir(orig_cwd)


def test_cli_add_missing_file_without_create_shim_flag_fails(tmp_path):
    """CLI add without --create-shim returns exit code 1 for non-existent file."""
    import os
    import sys
    from io import StringIO
    from superctx.__main__ import main

    orig_cwd = os.getcwd()
    orig_stderr = sys.stderr
    os.chdir(tmp_path)
    try:
        init_cmd.run(tmp_path)
        sys.stderr = StringIO()
        exit_code = main(["add", "GEMINI.md"])
        err = sys.stderr.getvalue()
        assert exit_code == 1
        assert "File does not exist" in err
    finally:
        sys.stderr = orig_stderr
        os.chdir(orig_cwd)


# ---------------------------------------------------------------------------
# Blocker 5: Healthy sync output is concise (no hub/shim internals exposed)
# ---------------------------------------------------------------------------

def test_sync_healthy_output_is_concise(tmp_path):
    """Healthy sync output must be concise — no hub/shim/backup internals on the happy path."""
    import os
    import sys
    from io import StringIO
    from superctx.__main__ import main

    make_repo(tmp_path, {"CLAUDE.md": "ctx\n"})
    orig_cwd = os.getcwd()
    orig_stdout = sys.stdout
    os.chdir(tmp_path)
    try:
        main(["sync"])
        sys.stdout = StringIO()
        exit_code = main(["sync"])
        assert exit_code == 0
        output = sys.stdout.getvalue()
        assert "All SuperCtx context links are healthy." in output
        # Must NOT expose hub/shim/backup internals on the healthy path
        assert "Hub:" not in output
        assert "Registered files:" not in output
        assert "plugin root:" not in output
        assert "SuperCtx diagnostics:" not in output
    finally:
        sys.stdout = orig_stdout
        os.chdir(orig_cwd)
