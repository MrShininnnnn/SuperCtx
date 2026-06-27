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


def _converge_policy(project_dir: Path, manifest: dict) -> bool:
    """Non-destructively bring an existing managed repo up to the current edit policy.

    Idempotently: writes .ctx/sources/README.md if missing, prepends the hub policy
    header if absent (preserving user content), and refreshes valid shims that lack
    the current redirect wording. Never rewrites the hub from tool files and never
    touches backup file contents. Returns True if anything changed.
    """
    changed = False

    if core.ensure_sources_readme(project_dir):
        changed = True

    hub_p = core.hub_path(project_dir)
    if hub_p.is_file():
        project_name = manifest.get("project", {}).get("name", project_dir.resolve().name)
        new_hub, hub_changed = core.ensure_hub_policy(
            hub_p.read_text(encoding="utf-8"), project_name
        )
        if hub_changed:
            hub_p.write_text(new_hub, encoding="utf-8")
            changed = True

    for entry in manifest.get("files", []):
        rel = entry["path"]
        live = project_dir / rel
        if live.is_file() and shim.is_shim_file(live):
            if not shim.has_current_policy(live.read_text(encoding="utf-8")):
                apply_res = shim.apply_shim(
                    project_dir,
                    rel,
                    force_backup=False,
                    backup_required=entry.get("backup_required", True),
                )
                if apply_res.get("shimmed"):
                    changed = True

    return changed


def run(project_dir: Path) -> dict:
    project_dir = Path(project_dir)

    from . import status as status_module
    from . import init as init_cmd

    state_info = status_module.detect_repo_state(project_dir)
    state = state_info["state"]
    rec_action = state_info["recommended_action"]

    if state == "not_candidate":
        return {
            "mode": "not_candidate",
            "state": "not_candidate",
            "final_state": "not_candidate",
            "mutated": False,
            "message": "No SuperCtx setup needed (no candidate files found)."
        }

    elif state == "candidate_repo":
        init_res = init_cmd.run(project_dir)
        final_state = "needs_attention" if init_res.get("partial_shim_failure") else "healthy"
        return {
            "mode": "init",
            "state": "candidate_repo",
            "final_state": final_state,
            "mutated": True,
            "init_result": init_res,
            "message": "SuperCtx initialized this repo with some shim failures." if final_state == "needs_attention" else "SuperCtx initialized this repo successfully."
        }

    elif state == "managed_legacy":
        return {
            "mode": "legacy",
            "state": "managed_legacy",
            "final_state": "needs_attention",
            "mutated": False,
            "message": "SuperCtx is present, but some instruction files are legacy."
        }

    elif state == "managed_needs_repair" and rec_action == "inspect":
        reasons = state_info.get("reasons", [])
        if any(reason.startswith("hub_") for reason in reasons):
            msg = "SuperCtx is present, but the configuration manifest or hub is missing or invalid."
        else:
            msg = "SuperCtx is present, but the configuration manifest is missing or invalid."
        return {
            "mode": "inspect",
            "state": "managed_needs_repair",
            "final_state": "needs_attention",
            "mutated": False,
            "message": msg
        }

    elif state == "managed_healthy":
        manifest = core.load_manifest(project_dir)
        healthy_shims = [entry["path"] for entry in manifest.get("files", [])]
        candidates = state_info.get("candidates", [])
        converged = _converge_policy(project_dir, manifest)
        return {
            "mode": "healthy",
            "state": "managed_healthy",
            "final_state": "healthy",
            "mutated": converged,
            "healthy": healthy_shims,
            "candidates": sorted(candidates),
            "message": "All SuperCtx context links are healthy."
        }

    elif state == "managed_needs_repair" and rec_action == "repair":
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
            backup_required = entry.get("backup_required", True)

            if backup_required and not backup.is_file():
                warnings.append({"path": rel, "reason": "missing_backup"})

            if live.is_file() and shim.is_shim_file(live):
                healthy.append(rel)
            else:
                apply_res = shim.apply_shim(project_dir, rel, force_backup=False)
                if apply_res.get("shimmed"):
                    repaired.append(rel)
                else:
                    unresolved.append({
                        "path": rel,
                        "reason": apply_res.get("reason", "unknown")
                    })

        final_state = "needs_attention" if unresolved else "healthy"
        msg = "SuperCtx shims repair complete with some unresolved issues." if unresolved else "SuperCtx shims repaired."
        return {
            "mode": "repair",
            "state": "managed_needs_repair",
            "final_state": final_state,
            "mutated": len(repaired) > 0,
            "healthy": healthy,
            "repaired": repaired,
            "unresolved": unresolved,
            "warnings": warnings,
            "message": msg
        }

    else:
        return {
            "mode": "inspect",
            "state": state,
            "final_state": "needs_attention",
            "mutated": False,
            "message": f"SuperCtx is in state {state}. Recommended action: {rec_action}."
        }
