"""`superctx sync` — hub-preserving shim repair and recovery command.

Verifies the integrity of registered shims, repairs missing or broken shims,
and warns if original backups are missing. Never modifies .ctx/SUPERCTX.md.
"""

from __future__ import annotations

from pathlib import Path

from . import core, shim


class SyncError(Exception):
    """Raised when sync/repair cannot be executed due to configuration or initialization issues."""
    pass


def run(project_dir: Path) -> dict:
    project_dir = Path(project_dir)
    manifest_path = core.manifest_path(project_dir)
    if not manifest_path.is_file():
        raise SyncError(
            "SuperCtx is not initialized in this project. "
            "Please offer to set up SuperCtx (with explicit consent) first."
        )

    try:
        manifest = core.load_manifest(project_dir)
    except core.SchemaError as e:
        raise SyncError(f"manifest.toml is invalid: {e}")
    except Exception as e:
        raise SyncError(f"manifest.toml is unreadable: {e}")

    healthy: list[str] = []
    repaired: list[str] = []
    unresolved: list[dict] = []
    warnings: list[dict] = []

    for entry in manifest.get("files", []):
        rel = entry["path"]
        live = project_dir / rel
        backup = core.sources_dir(project_dir) / rel

        # 1. Check if backup is missing
        if not backup.is_file():
            warnings.append({"path": rel, "reason": "missing_backup"})

        # 2. Check live file health
        if live.is_file() and shim.is_shim_file(live):
            healthy.append(rel)
        else:
            # 3. Missing or broken shim, try to repair/apply shim
            # force_backup=False prevents overwriting live edits if backup exists
            apply_res = shim.apply_shim(project_dir, rel, force_backup=False)
            if apply_res.get("shimmed"):
                repaired.append(rel)
            else:
                unresolved.append({
                    "path": rel,
                    "reason": apply_res.get("reason", "unknown")
                })

    return {
        "mode": "repair",
        "healthy": healthy,
        "repaired": repaired,
        "unresolved": unresolved,
        "warnings": warnings
    }
