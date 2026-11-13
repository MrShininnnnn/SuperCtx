"""`superctx sync` — hub-preserving shim repair and recovery command.

Verifies the integrity of registered shims, repairs missing or broken shims,
and warns if original backups are missing. Never rebuilds .ctx/SUPERCTX.md from
tool files; may add missing edit-policy scaffolding while preserving user content.
"""

from __future__ import annotations

from pathlib import Path

from . import adopt, core, manifest as manifest_mod, registry, shim


class SyncError(Exception):
    """Raised when sync/repair cannot be executed due to configuration or initialization issues."""
    pass


def _converge_policy(project_dir: Path, manifest: dict, skip: set[str] = frozenset()) -> bool:
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
        if rel in skip:
            continue
        live = project_dir / rel
        backup_required = entry.get("backup_required", True)
        if shim.is_generated_pointer_file(project_dir, rel, backup_required):
            current = shim.generated_pointers(rel, backup_required)[0]
            if live.read_text(encoding="utf-8").replace("\r\n", "\n") != current:
                # An older SuperCtx rendering; refresh it to the current wording.
                live.write_text(current, encoding="utf-8")
                changed = True

    return changed


def _unreadable(e: Exception) -> dict:
    return {
        "mode": "inspect",
        "state": "managed_needs_repair",
        "final_state": "needs_attention",
        "mutated": False,
        "message": (
            f"tool_folder_unreadable: SuperCtx could not read {e}, so it cannot tell which "
            "paths are tool configuration and changed nothing. Make the folder readable "
            "and run sync again."
        ),
    }


def run(project_dir: Path) -> dict:
    project_dir = Path(project_dir)
    where = core.unreadable_ctx_entry(project_dir)
    if where:
        return {
            "mode": "inspect",
            "state": "managed_needs_repair",
            "final_state": "needs_attention",
            "mutated": False,
            "message": (
                f"ctx_unreadable: SuperCtx could not read {where}, so it cannot check its own "
                "files and changed nothing. Make the folder readable and run sync again."
            ),
        }
    links = core.symlinked_ctx_entries(project_dir)
    if links:
        return {
            "mode": "inspect",
            "state": "managed_needs_repair",
            "final_state": "needs_attention",
            "mutated": False,
            "message": core.symlinked_ctx_message(links)
        }
    try:
        registry.check_readable(project_dir)
    except registry.ScanError as e:
        return _unreadable(e)
    try:
        migrated = _migrate(project_dir)
    except manifest_mod.MigrationError as e:
        return {
            "mode": "inspect",
            "state": "managed_needs_repair",
            "final_state": "needs_attention",
            "mutated": False,
            "message": f"SuperCtx could not migrate the manifest: {e}"
        }
    result = _run(project_dir)
    if result["mode"] in ("healthy", "repair"):
        # Report standing reasons for rules and skills that stay where they are.
        result["left_in_place"] = adopt.plan(project_dir, manifest_mod.load_v2(project_dir))[1]
    if migrated:
        result["migrated"] = True
        result["mutated"] = True
    return result


def _migrate(project_dir: Path) -> bool:
    """Bring a v1, interrupted, or unsealed workspace to a sealed v2 manifest first.

    Lost or conflicting manifests and unreadable or invalid manifest files are left
    untouched for detect_repo_state to report. Raises MigrationError when a valid
    v1 manifest cannot be migrated.
    """
    kind = manifest_mod.locate(project_dir)
    if kind not in ("v1", "interrupted", "v2_unsealed"):
        return False
    try:
        if kind == "v1":
            core.load_v1_manifest(core.manifest_path(project_dir))
        elif kind == "v2_unsealed":
            manifest_mod.load_v2(project_dir)
    except Exception:
        return False
    return manifest_mod.migrate(project_dir)


def _run(project_dir: Path) -> dict:
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
        created = init_res["created"]
        final_state = "needs_attention" if init_res.get("partial_shim_failure") or not created else "healthy"
        return {
            "mode": "init",
            "state": "candidate_repo",
            "final_state": final_state,
            "mutated": created,
            "init_result": init_res,
            "message": ("SuperCtx did not set up this repo." if not created
                        else "SuperCtx initialized this repo with some shim failures." if final_state == "needs_attention"
                        else "SuperCtx initialized this repo successfully.")
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
        if "manifest_lost" in reasons:
            msg = (
                "SuperCtx is present, but .ctx/superctx.toml is missing from a migrated workspace. "
                "It is not rebuilt from .ctx/manifest.v1.toml because that would drop v2-only resources; "
                "restore it from version control."
            )
        elif "manifest_conflict" in reasons:
            msg = (
                "SuperCtx is present, but .ctx/manifest.toml is not a SuperCtx 0.2 sentinel "
                "while .ctx/superctx.toml exists. Inspect both files."
            )
        elif any(reason.startswith("hub_") for reason in reasons):
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
        healthy_shims = [entry["path"] for entry in manifest.get("files", []) + manifest.get("links", [])]
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
        # Tool configuration an earlier version turned into a pointer: reported, never written.
        try:
            tool_config = registry.adopted_tool_config(project_dir, [e["path"] for e in manifest.get("files", [])])
        except registry.ScanError as e:
            return _unreadable(e)

        for entry in manifest.get("files", []):
            rel = entry["path"]
            live = project_dir / rel
            backup = core.sources_dir(project_dir) / rel
            backup_required = entry.get("backup_required", True)

            if backup_required and not backup.is_file():
                warnings.append({"path": rel, "reason": "missing_backup"})
            if rel in tool_config:
                unresolved.append({"path": rel, "reason": "tool_config_adopted"})
                continue

            pub = shim.publish_pointer(
                project_dir, rel, backup_required=backup_required, published=entry.get("published", True)
            )
            if not pub["shimmed"]:
                unresolved.append({"path": rel, "reason": pub["reason"]})
            elif pub.get("already_shim"):
                healthy.append(rel)
            else:
                repaired.append(rel)

        for link in manifest.get("links", []):
            status, reason = adopt.publish_link(project_dir, link["path"], link["canonical"], link["published"])
            if status == "healthy":
                healthy.append(link["path"])
            elif status == "repaired":
                repaired.append(link["path"])
            else:
                unresolved.append({"path": link["path"], "reason": reason})

        # Natives whose first publication is now complete are only ever repaired from here on.
        unpublished = {e["path"] for e in manifest.get("files", []) + manifest.get("links", [])
                       if not e.get("published", True)}
        newly_published = unpublished & (set(healthy) | set(repaired))
        if newly_published:
            manifest_mod.mark_published(project_dir, newly_published)

        # Bring policy surfaces up to date in the same run (README, hub header,
        # stale shim wording), conservatively and idempotently.
        converged = _converge_policy(project_dir, manifest, tool_config)

        final_state = "needs_attention" if unresolved else "healthy"
        msg = "SuperCtx shims repair complete with some unresolved issues." if unresolved else "SuperCtx shims repaired."
        return {
            "mode": "repair",
            "state": "managed_needs_repair",
            "final_state": final_state,
            "mutated": len(repaired) > 0 or converged or bool(newly_published),
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
