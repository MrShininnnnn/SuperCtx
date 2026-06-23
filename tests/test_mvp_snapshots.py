import os
import shutil
import subprocess
import sys
from pathlib import Path

from superctx import core, init as init_cmd, status as status_cmd, sync as sync_cmd

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "examples" / "demo-python-project"
SNAPSHOTS = ROOT / "tests" / "snapshots" / "demo-python-project"


def copy_demo(tmp_path: Path) -> Path:
    project = tmp_path / "demo-python-project"
    shutil.copytree(DEMO, project)
    return project


def test_demo_project_generates_expected_manifest_and_hub(tmp_path):
    project = copy_demo(tmp_path)

    init_result = init_cmd.run(project)
    sync_result = sync_cmd.run(project)
    status_rows = status_cmd.run(project)

    assert init_result["created"] is True
    assert init_result["detected"] == ["CLAUDE.md", "AGENTS.md", "GEMINI.md"]
    assert sync_result == {
        "mode": "healthy",
        "state": "managed_healthy",
        "final_state": "healthy",
        "mutated": False,
        "healthy": ["CLAUDE.md", "AGENTS.md", "GEMINI.md"],
        "candidates": [],
        "message": "All SuperCtx context links are healthy."
    }
    # Assert status rows matches new schema
    assert next(r for r in status_rows if r["kind"] == "hub") == {
        "kind": "hub",
        "path": ".ctx/SUPERCTX.md",
        "state": "healthy",
    }
    assert next(r for r in status_rows if r["kind"] == "shim" and r["path"] == "CLAUDE.md") == {
        "kind": "shim",
        "path": "CLAUDE.md",
        "state": "healthy",
        "import_syntax": "claude-at-import",
    }
    assert next(r for r in status_rows if r["kind"] == "backup" and r["source"] == "CLAUDE.md") == {
        "kind": "backup",
        "path": ".ctx/sources/CLAUDE.md",
        "source": "CLAUDE.md",
        "state": "healthy",
    }
    assert core.normalize(core.manifest_path(project).read_text(encoding="utf-8")) == (
        core.normalize((SNAPSHOTS / "manifest.toml").read_text(encoding="utf-8"))
    )
    assert core.normalize(core.hub_path(project).read_text(encoding="utf-8")) == (
        core.normalize((SNAPSHOTS / "SUPERCTX.md").read_text(encoding="utf-8"))
    )


def test_demo_project_cli_round_trip(tmp_path):
    project = copy_demo(tmp_path)
    env = {
        **os.environ,
        "PYTHONPATH": str(ROOT / "scripts"),
    }

    setup_result = subprocess.run(
        [sys.executable, "-m", "superctx", "sync", str(project)],
        check=True,
        env=env,
        text=True,
        capture_output=True,
    )
    healthy_result = subprocess.run(
        [sys.executable, "-m", "superctx", "sync", str(project)],
        check=True,
        env=env,
        text=True,
        capture_output=True,
    )

    assert "initialized" in setup_result.stdout
    assert "All SuperCtx context links are healthy" in healthy_result.stdout
    assert "Already healthy shims:" not in healthy_result.stdout
    assert "Hub:" not in healthy_result.stdout
    assert "Registered files:" not in healthy_result.stdout
    assert "SuperCtx diagnostics:" not in healthy_result.stdout
    assert "plugin root:" not in healthy_result.stdout


def test_generated_sources_are_ignored_inside_ctx(tmp_path):
    project = copy_demo(tmp_path)

    init_cmd.run(project)
    sync_cmd.run(project)

    assert core.normalize(
        (core.ctx_dir(project) / ".gitignore").read_text(encoding="utf-8")
    ) == "# Inactive backup storage for original instruction files.\nsources/\n"
    assert (core.sources_dir(project) / "CLAUDE.md").is_file()
    assert (core.sources_dir(project) / "AGENTS.md").is_file()
    assert (core.sources_dir(project) / "GEMINI.md").is_file()


def test_repository_local_only_gitignore_entries_are_present():
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")

    for entry in [".claude/", ".codex/", ".agy/", ".ctx/", "docs/"]:
        assert entry in gitignore
