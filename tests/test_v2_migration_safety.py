"""Migration-safety gate for v0.2: unpatched 0.1.x clients against v2 repositories.

Each test builds a disposable repository, initializes it with the real released
client, migrates it with the v2 migration, puts it into a healthy, conflicting,
missing-file, or interrupted state, and then runs the released client's sync,
add, and internal init paths against it. The whole workspace (contents, modes,
symlink targets, and timestamps) must be unchanged afterwards.

The released client is extracted from its git tag, so CI must fetch tags.
"""

from __future__ import annotations

import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from superctx import core, manifest as manifest_mod, sync as sync_cmd

ROOT = Path(__file__).resolve().parents[1]
LEGACY_TAG = "v0.1.4"

CLAUDE_ORIGINAL = "# Claude\n\nRun `make test` before committing.\n"
AGENTS_ORIGINAL = "# Agents\n\nPrefer small diffs.\n"
GEMINI_UNTRACKED = "# Gemini\n\nWritten after SuperCtx was set up.\n"
SKILL_MD = "---\nname: review\ndescription: Review a diff\n---\n\nRun scripts/run.sh.\n"
RUN_SH = "#!/bin/sh\necho review\n"
RULE_MD = "---\npaths: [\"src/**/*.py\"]\n---\n\nUse type hints.\n"


# --- released client ---------------------------------------------------------

@pytest.fixture(scope="session")
def legacy_scripts(tmp_path_factory) -> Path:
    dest = tmp_path_factory.mktemp(f"superctx-{LEGACY_TAG}")
    archive = dest / "src.tar"
    try:
        subprocess.run(
            ["git", "-C", str(ROOT), "archive", f"--output={archive}", LEGACY_TAG, "scripts/superctx"],
            check=True, capture_output=True,
        )
        subprocess.run(["tar", "-xf", str(archive), "-C", str(dest)], check=True, capture_output=True)
    except (OSError, subprocess.CalledProcessError) as e:
        pytest.fail(f"Cannot extract {LEGACY_TAG} (run `git fetch --tags`): {e}")
    return dest / "scripts"


def _legacy_code(body: str, toml_backend: str) -> str:
    # Setting a module to None in sys.modules makes importing it raise
    # ModuleNotFoundError, which forces toml_compat's minimal parser.
    block = "sys.modules['tomllib'] = None\nsys.modules['tomli'] = None\n" if toml_backend == "minimal" else ""
    return f"import sys\nsys.path.insert(0, sys.argv.pop(1))\n{block}{body}"


def run_legacy(scripts: Path, project: Path, op: str, toml_backend: str = "native") -> subprocess.CompletedProcess:
    if op == "init":
        body = (
            "from pathlib import Path\n"
            "from superctx import init\n"
            "result = init.run(Path(sys.argv[1]))\n"
            "sys.exit(1 if result['created'] else 0)\n"
        )
        args = [str(project)]
    else:
        body = "import runpy\nsys.argv[0] = 'superctx'\nrunpy.run_module('superctx', run_name='__main__')\n"
        args = LEGACY_OPS[op] + [str(project)]
    return subprocess.run(
        [sys.executable, "-I", "-c", _legacy_code(body, toml_backend), str(scripts), *args],
        cwd=project, capture_output=True, text=True,
    )


# Every 0.1.4 entry point that can write. "init" exits 0 only when it refused
# (created=False); the CLI commands must exit non-zero.
LEGACY_OPS = {
    "sync": ["sync"],
    "add-tracked": ["add", "CLAUDE.md"],
    "add-untracked": ["add", "GEMINI.md"],
    "add-create-shim": ["add", "--create-shim", ".github/copilot-instructions.md"],
}
ALL_OPS = [*LEGACY_OPS, "init"]


def assert_refused(result: subprocess.CompletedProcess, op: str) -> None:
    detail = f"{op}: rc={result.returncode}\nstdout={result.stdout}\nstderr={result.stderr}"
    assert "Traceback" not in result.stderr, detail
    if op == "init":
        assert result.returncode == 0, detail
    else:
        assert result.returncode != 0, detail


# --- workspace snapshots -----------------------------------------------------

def snapshot(root: Path, times: bool = True) -> dict:
    """Every path under root: type, mode, contents or link target, and optionally mtime."""
    out = {}
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        for name in dirnames + filenames:
            path = Path(dirpath) / name
            st = os.lstat(path)
            rel = path.relative_to(root).as_posix()
            if stat.S_ISLNK(st.st_mode):
                entry = ("link", os.readlink(path))
            elif stat.S_ISDIR(st.st_mode):
                entry = ("dir", stat.S_IMODE(st.st_mode))
            else:
                entry = ("file", stat.S_IMODE(st.st_mode), path.read_bytes())
            out[rel] = entry + ((st.st_mtime_ns,) if times else ())
    return out


# --- fixtures ----------------------------------------------------------------

def write(project: Path, rel: str, text: str, mode: int | None = None) -> None:
    path = project / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    if mode is not None:
        path.chmod(mode)


def link(project: Path, rel: str, target: str) -> None:
    path = project / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    os.symlink(target, path)


def build_v1(project: Path, scripts: Path) -> Path:
    """A repository initialized by the released client, plus v2-style resources it does not know."""
    project.mkdir()
    write(project, "CLAUDE.md", CLAUDE_ORIGINAL)
    write(project, "AGENTS.md", AGENTS_ORIGINAL)
    result = run_legacy(scripts, project, "sync")
    assert result.returncode == 0, result.stdout + result.stderr
    assert core.load_manifest(project)["files"]

    write(project, "GEMINI.md", GEMINI_UNTRACKED)
    write(project, ".ctx/skills/review/SKILL.md", SKILL_MD)
    write(project, ".ctx/skills/review/scripts/run.sh", RUN_SH, mode=0o755)
    link(project, ".claude/skills/review", "../../.ctx/skills/review")
    write(project, ".agents/skills/review/SKILL.md", SKILL_MD)
    write(project, ".agents/skills/review/scripts/run.sh", RUN_SH, mode=0o755)
    write(project, ".ctx/rules/python.md", RULE_MD)
    link(project, ".cursor/rules/python.mdc", "../../.ctx/rules/python.md")
    return project


def build_v2(project: Path, scripts: Path) -> Path:
    build_v1(project, scripts)
    assert manifest_mod.migrate(project) is True
    return project


def _edit_native(p: Path) -> None:
    (p / "CLAUDE.md").write_text("Hand edit made after SuperCtx took over.\n", encoding="utf-8")


def _drift_generated_copy(p: Path) -> None:
    (p / ".agents/skills/review/SKILL.md").write_text(SKILL_MD + "\nLocal tweak.\n", encoding="utf-8")


def _retarget_link(p: Path) -> None:
    (p / ".claude/skills/review").unlink()
    link(p, ".claude/skills/review", "../../elsewhere/review")


def _replace_link_with_dir(p: Path) -> None:
    (p / ".cursor/rules/python.mdc").unlink()
    write(p, ".cursor/rules/python.mdc", "native copy\n")


V2_STATES = {
    "healthy": lambda p: None,
    "conflict-native-edit": _edit_native,
    "conflict-generated-drift": _drift_generated_copy,
    "conflict-link-retargeted": _retarget_link,
    "conflict-link-replaced": _replace_link_with_dir,
    "missing-shim": lambda p: (p / "AGENTS.md").unlink(),
    "missing-hub": lambda p: core.hub_path(p).unlink(),
    "missing-backup": lambda p: (core.sources_dir(p) / "CLAUDE.md").unlink(),
    "missing-v2-manifest": lambda p: (core.ctx_dir(p) / core.V2_MANIFEST_NAME).unlink(),
    "missing-link-target": lambda p: (p / ".ctx/rules/python.md").unlink(),
}


# --- old clients against v2 repositories -------------------------------------

@pytest.mark.parametrize("toml_backend", ["native", "minimal"])
@pytest.mark.parametrize("op", ALL_OPS)
@pytest.mark.parametrize("state", list(V2_STATES))
def test_legacy_client_refuses_v2_repo_without_writing(tmp_path, legacy_scripts, state, op, toml_backend):
    project = build_v2(tmp_path / "repo", legacy_scripts)
    V2_STATES[state](project)
    before = snapshot(project)

    result = run_legacy(legacy_scripts, project, op, toml_backend)

    assert_refused(result, op)
    assert snapshot(project) == before


@pytest.mark.parametrize("op", list(LEGACY_OPS))
def test_legacy_cli_refuses_when_sentinel_is_deleted(tmp_path, legacy_scripts, op):
    project = build_v2(tmp_path / "repo", legacy_scripts)
    core.manifest_path(project).unlink()
    before = snapshot(project)

    result = run_legacy(legacy_scripts, project, op)

    assert_refused(result, op)
    assert snapshot(project) == before


@pytest.mark.xfail(strict=True, reason=(
    "0.1.4 init.run only checks for manifest.toml, so with the sentinel deleted it "
    "re-initializes over the hub. Not reachable from the 0.1.4 CLI: sync only calls "
    "init when .ctx/ does not exist."
))
def test_legacy_internal_init_refuses_when_sentinel_is_deleted(tmp_path, legacy_scripts):
    project = build_v2(tmp_path / "repo", legacy_scripts)
    core.manifest_path(project).unlink()
    before = snapshot(project)

    result = run_legacy(legacy_scripts, project, "init")

    assert_refused(result, "init")
    assert snapshot(project) == before


# --- migration ---------------------------------------------------------------

def has_sentinel(path: Path) -> bool:
    return manifest_mod._sentinel_state(path) in (manifest_mod.IN_PROGRESS, manifest_mod.COMPLETE)


def test_migration_preserves_everything_but_manifests(tmp_path, legacy_scripts):
    project = build_v1(tmp_path / "repo", legacy_scripts)
    v1_text = core.manifest_path(project).read_text(encoding="utf-8")
    before = snapshot(project, times=False)

    manifest_mod.migrate(project)

    after = snapshot(project, times=False)
    changed = {rel for rel in before.keys() | after.keys() if before.get(rel) != after.get(rel)}
    assert changed == {".ctx/manifest.toml", ".ctx/manifest.v1.toml", ".ctx/superctx.toml"}
    assert (core.ctx_dir(project) / core.V1_BACKUP_NAME).read_text(encoding="utf-8") == v1_text
    assert has_sentinel(core.manifest_path(project))


def test_v2_manifest_carries_every_v1_entry(tmp_path, legacy_scripts):
    project = build_v1(tmp_path / "repo", legacy_scripts)
    v1 = core.load_manifest(project)

    manifest_mod.migrate(project)

    v2 = manifest_mod._parse((core.ctx_dir(project) / core.V2_MANIFEST_NAME).read_text(encoding="utf-8"))
    assert v2["schema"] == 2
    assert v2["project"]["name"] == v1["project"]["name"]
    assert v2["resources"] == [{"id": "instructions", "type": "instructions", "canonical": v1["project"]["hub"]}]
    assert [(n["resource"], n["path"], n["mode"], n["tools"], n["backup"]) for n in v2["natives"]] == [
        ("instructions", f["path"], "pointer", f["tools"], f.get("backup_required", True)) for f in v1["files"]
    ]


def test_migration_second_run_makes_no_changes(tmp_path, legacy_scripts):
    project = build_v2(tmp_path / "repo", legacy_scripts)
    before = snapshot(project)

    assert manifest_mod.migrate(project) is False
    assert snapshot(project) == before


class Crash(Exception):
    pass


# (replace call that crashes, whether the crash happens before or after it)
CRASH_POINTS = [(n, when) for n in range(4) for when in ("before", "after")]


@pytest.mark.parametrize("crash_at,when", CRASH_POINTS)
def test_interrupted_migration_is_safe_and_resumes(tmp_path, legacy_scripts, monkeypatch, crash_at, when):
    # Same directory name: the project name in the manifest comes from it.
    (tmp_path / "reference").mkdir()
    expected = snapshot(build_v2(tmp_path / "reference" / "repo", legacy_scripts), times=False)
    project = build_v1(tmp_path / "repo", legacy_scripts)

    calls = []

    def crashing_replace(src, dst):
        calls.append(dst)
        if len(calls) - 1 == crash_at:
            if when == "after":
                os.replace(src, dst)
            raise Crash(dst)
        os.replace(src, dst)

    monkeypatch.setattr(manifest_mod, "_replace", crashing_replace)
    with pytest.raises(Crash):
        manifest_mod.migrate(project)
    monkeypatch.setattr(manifest_mod, "_replace", os.replace)

    if has_sentinel(core.manifest_path(project)):
        for op in ALL_OPS:
            before = snapshot(project)
            assert_refused(run_legacy(legacy_scripts, project, op), op)
            assert snapshot(project) == before, op
    else:
        # Still a v1 repository: the old client may keep working with it.
        result = run_legacy(legacy_scripts, project, "sync")
        assert result.returncode == 0, result.stdout + result.stderr

    # A crash after the last replace leaves nothing to resume.
    assert manifest_mod.migrate(project) is not (crash_at == 3 and when == "after")
    resumed = snapshot(project, times=False)
    assert resumed == expected, sorted(k for k in resumed.keys() | expected.keys() if resumed.get(k) != expected.get(k))

    before = snapshot(project)
    assert manifest_mod.migrate(project) is False
    assert snapshot(project) == before


def test_resume_rereads_v1_manifest_changed_before_sentinel(tmp_path, legacy_scripts, monkeypatch):
    """An old client adds a file between the backup and the sentinel; the resume must pick it up."""
    project = build_v1(tmp_path / "repo", legacy_scripts)

    def crash_on_sentinel(src, dst):
        if Path(dst) == core.manifest_path(project):
            raise Crash(dst)
        os.replace(src, dst)

    monkeypatch.setattr(manifest_mod, "_replace", crash_on_sentinel)
    with pytest.raises(Crash):
        manifest_mod.migrate(project)
    monkeypatch.setattr(manifest_mod, "_replace", os.replace)

    result = run_legacy(legacy_scripts, project, "add-untracked")
    assert result.returncode == 0, result.stdout + result.stderr

    manifest_mod.migrate(project)

    v2 = manifest_mod._parse((core.ctx_dir(project) / core.V2_MANIFEST_NAME).read_text(encoding="utf-8"))
    assert "GEMINI.md" in [n["path"] for n in v2["natives"]]


@pytest.mark.parametrize("damage", ["v2-lost-after-completion", "v2-and-v1-copy-lost", "garbage-manifest"])
def test_migration_refuses_unrecoverable_states_without_writing(tmp_path, legacy_scripts, damage):
    if damage.startswith("v2-"):
        project = build_v2(tmp_path / "repo", legacy_scripts)
        core.v2_manifest_path(project).unlink()
        if damage == "v2-and-v1-copy-lost":
            core.v1_backup_path(project).unlink()
    else:
        project = build_v1(tmp_path / "repo", legacy_scripts)
        core.manifest_path(project).write_text("files = [[[\n", encoding="utf-8")
    before = snapshot(project)

    with pytest.raises(manifest_mod.MigrationError):
        manifest_mod.migrate(project)
    assert snapshot(project) == before


def test_interrupted_upgrade_resumes_but_lost_v2_manifest_is_refused(tmp_path, legacy_scripts, monkeypatch):
    """Both workspaces lack .ctx/superctx.toml and keep .ctx/manifest.v1.toml; only the interrupted one is rebuilt."""
    (tmp_path / "interrupted").mkdir()
    (tmp_path / "lost").mkdir()
    interrupted = build_v1(tmp_path / "interrupted" / "repo", legacy_scripts)

    def crash_on_v2_write(src, dst):
        if Path(dst) == core.v2_manifest_path(interrupted):
            raise Crash(dst)
        os.replace(src, dst)

    monkeypatch.setattr(manifest_mod, "_replace", crash_on_v2_write)
    with pytest.raises(Crash):
        manifest_mod.migrate(interrupted)
    monkeypatch.setattr(manifest_mod, "_replace", os.replace)

    lost = build_v2(tmp_path / "lost" / "repo", legacy_scripts)
    # A v2-only resource the v1 copy knows nothing about, then the manifest is deleted.
    doc = manifest_mod.load_v2(lost)
    doc["resources"].append({"id": "review", "type": "skill", "canonical": ".ctx/skills/review"})
    doc["natives"].append({"resource": "review", "path": ".claude/skills/review", "mode": "link", "tools": [], "backup": False})
    manifest_mod.write(lost, doc)
    core.v2_manifest_path(lost).unlink()

    for project in (interrupted, lost):
        assert not core.v2_manifest_path(project).exists()
        assert core.v1_backup_path(project).is_file()
    assert manifest_mod.locate(interrupted) == "interrupted"
    assert manifest_mod.locate(lost) == "lost"

    result = sync_cmd.run(interrupted)
    assert result["migrated"] is True
    assert result["final_state"] == "healthy"
    assert manifest_mod.locate(interrupted) == "v2"
    assert [n["path"] for n in manifest_mod.load_v2(interrupted)["natives"]] == ["CLAUDE.md", "AGENTS.md"]

    before = snapshot(lost)
    result = sync_cmd.run(lost)
    assert result["mode"] == "inspect"
    assert result["mutated"] is False
    assert "restore it from version control" in result["message"]
    assert snapshot(lost) == before


@pytest.mark.parametrize("op", ALL_OPS)
def test_legacy_client_refuses_a_workspace_set_up_with_linked_rules_and_skills(tmp_path, legacy_scripts, op):
    project = tmp_path / "repo"
    project.mkdir()
    write(project, "CLAUDE.md", CLAUDE_ORIGINAL)
    write(project, ".claude/rules/python.md", RULE_MD)
    write(project, ".claude/skills/review/SKILL.md", SKILL_MD)
    write(project, ".claude/skills/review/scripts/run.sh", RUN_SH, mode=0o755)
    assert sync_cmd.run(project)["final_state"] == "healthy"
    write(project, "GEMINI.md", GEMINI_UNTRACKED)  # untracked, for the add-untracked op
    assert os.path.islink(project / ".claude/skills/review")
    before = snapshot(project)

    result = run_legacy(legacy_scripts, project, op)

    assert_refused(result, op)
    assert snapshot(project) == before
