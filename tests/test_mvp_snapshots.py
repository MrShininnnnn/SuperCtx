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
        "centralized": ["CLAUDE.md", "AGENTS.md", "GEMINI.md"],
        "missing": [],
    }
    assert status_rows == [
        {"path": "CLAUDE.md", "state": "synced"},
        {"path": "AGENTS.md", "state": "synced"},
        {"path": "GEMINI.md", "state": "synced"},
    ]
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

    init_result = subprocess.run(
        [sys.executable, "-m", "superctx", "init", str(project)],
        check=True,
        env=env,
        text=True,
        capture_output=True,
    )
    sync_result = subprocess.run(
        [sys.executable, "-m", "superctx", "sync", str(project)],
        check=True,
        env=env,
        text=True,
        capture_output=True,
    )
    status_result = subprocess.run(
        [sys.executable, "-m", "superctx", "status", str(project)],
        check=True,
        env=env,
        text=True,
        capture_output=True,
    )

    assert "initialized" in init_result.stdout
    assert "+ centralized CLAUDE.md" in sync_result.stdout
    assert "synced     CLAUDE.md" in status_result.stdout
    assert "synced     AGENTS.md" in status_result.stdout
    assert "synced     GEMINI.md" in status_result.stdout


def test_generated_sources_are_ignored_inside_ctx(tmp_path):
    project = copy_demo(tmp_path)

    init_cmd.run(project)
    sync_cmd.run(project)

    assert core.normalize(
        (core.ctx_dir(project) / ".gitignore").read_text(encoding="utf-8")
    ) == "# Raw per-tool snapshots are a local drift-detection cache.\nsources/\n"
    assert (core.sources_dir(project) / "CLAUDE.md").is_file()
    assert (core.sources_dir(project) / "AGENTS.md").is_file()
    assert (core.sources_dir(project) / "GEMINI.md").is_file()


def test_repository_local_only_gitignore_entries_are_present():
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")

    for entry in [".claude/", ".codex/", ".agy/", "docs/"]:
        assert entry in gitignore
