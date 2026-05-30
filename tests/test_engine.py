"""Unit tests for the SuperCtx engine (init / sync / status) using temp project dirs."""

from pathlib import Path

from superctx import core, init as init_cmd, status as status_cmd, sync as sync_cmd


def make_repo(tmp_path: Path, files: dict[str, str]) -> Path:
    for rel, content in files.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return tmp_path


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
