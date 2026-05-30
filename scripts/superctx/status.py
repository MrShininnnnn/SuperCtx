"""`superctx status` — read-only drift report comparing live tool files to their snapshots.

States per path:
  synced    — live file matches its .ctx/sources/ snapshot
  drifted   — live file differs from snapshot (or has never been synced)
  missing   — tracked in the manifest but the live file is gone
  untracked — a known instruction-file convention exists in the repo but isn't in the manifest
"""

from __future__ import annotations

from pathlib import Path

from . import core, registry


def run(project_dir: Path) -> list[dict]:
    project_dir = Path(project_dir)
    manifest = core.load_manifest(project_dir)
    files = manifest.get("files", [])
    tracked = {entry["path"] for entry in files}
    results: list[dict] = []

    for entry in files:
        rel = entry["path"]
        live = project_dir / rel
        snapshot = core.sources_dir(project_dir) / rel
        if not live.is_file():
            state = "missing"
        elif not snapshot.is_file():
            state = "drifted"  # tracked but never centralized
        elif core.content_hash(core.read_text(live)) == core.content_hash(core.read_text(snapshot)):
            state = "synced"
        else:
            state = "drifted"
        results.append({"path": rel, "state": state})

    for conv in registry.detect(project_dir):
        if conv["path"] not in tracked:
            results.append({"path": conv["path"], "state": "untracked"})

    return results
