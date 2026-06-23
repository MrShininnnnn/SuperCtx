"""Read-only hub-and-shim health and detection helpers.

Health states:
  healthy             — all structural integrity checks passed for hub, shim, or backup
  missing_shim        — registered file does not exist in the project
  broken_shim         — registered file is not a valid generated shim pointing to the hub
  missing_backup      — original backup copy under .ctx/sources/ is missing
  missing_hub         — the canonical .ctx/SUPERCTX.md hub does not exist
  empty_hub           — the canonical .ctx/SUPERCTX.md hub is empty
  untracked_candidate — local convention candidate path matches standard convention but is not tracked
"""

from __future__ import annotations

from pathlib import Path
import os
import json

from . import core, registry, shim


class StatusError(Exception):
    """Raised when SuperCtx is not initialized or has configuration errors."""
    pass


def resolve_version(module_path: Path | None = None) -> dict:
    if module_path is None:
        module_path = Path(__file__).resolve()
    else:
        module_path = Path(module_path).resolve()

    # 1. Primary: check env var
    env_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if env_root:
        root_path = Path(env_root).resolve()
        plugin_json = root_path / ".claude-plugin" / "plugin.json"
        if plugin_json.is_file():
            try:
                with open(plugin_json, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if "version" in data:
                        return {
                            "version": data["version"],
                            "plugin_root": str(root_path),
                            "version_source": "env"
                        }
            except Exception:
                pass

    # 2. Fallback: parent path walk
    curr = module_path
    while True:
        candidate = curr / ".claude-plugin" / "plugin.json"
        if candidate.is_file():
            try:
                with open(candidate, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if "version" in data:
                        return {
                            "version": data["version"],
                            "plugin_root": str(curr.resolve()),
                            "version_source": "parent"
                        }
            except Exception:
                pass
        if curr.parent == curr:
            break
        curr = curr.parent

    # 3. Final fallback: shared constant
    from . import __version__
    return {
        "version": __version__,
        "plugin_root": None,
        "version_source": "fallback"
    }


def sanitize_path(path: Path | str | None) -> str:
    if path is None:
        return "None"
    p = Path(path).resolve()
    try:
        home = Path.home().resolve()
        if p.is_relative_to(home):
            rel = p.relative_to(home)
            if str(rel) == ".":
                return "~"
            return f"~/{rel}"
    except Exception:
        pass
    return str(p)


def diagnostics(project_dir: Path, module_path: Path | None = None) -> dict:
    project_dir = Path(project_dir).resolve()
    res_version = resolve_version(module_path)

    conventions = registry.load_conventions()
    supported_paths = {c["path"] for c in conventions}

    claude_supported = ".claude/CLAUDE.md" in supported_paths
    codex_supported = ".codex/AGENTS.md" in supported_paths

    claude_present = (project_dir / ".claude/CLAUDE.md").is_file()
    codex_present = (project_dir / ".codex/AGENTS.md").is_file()

    stale_install = (claude_present and not claude_supported) or (codex_present and not codex_supported)

    return {
        "version": res_version["version"],
        "plugin_root": sanitize_path(res_version["plugin_root"]),
        "version_source": res_version["version_source"],
        "registry": sanitize_path(registry.registry_path()),
        "supports_claude_md": claude_supported,
        "supports_codex_agents": codex_supported,
        "project_has_claude_md": claude_present,
        "project_has_codex_agents": codex_present,
        "stale_install": stale_install
    }


def run(project_dir: Path) -> list[dict]:
    project_dir = Path(project_dir)
    manifest_path = core.manifest_path(project_dir)

    if not manifest_path.is_file():
        raise StatusError(
            "SuperCtx is not initialized in this project. "
            "Please offer to set up SuperCtx (with explicit consent) first."
        )

    results: list[dict] = []

    # 1. Check Hub
    hub_p = core.hub_path(project_dir)
    hub_rel = f"{core.CTX_DIRNAME}/{core.HUB_NAME}"
    if not hub_p.is_file():
        results.append({"kind": "hub", "path": hub_rel, "state": "missing_hub"})
    else:
        hub_content = hub_p.read_text(encoding="utf-8")
        if not hub_content.strip():
            results.append({"kind": "hub", "path": hub_rel, "state": "empty_hub"})
        else:
            results.append({"kind": "hub", "path": hub_rel, "state": "healthy"})

    # 2. Check Registered Files
    manifest = core.load_manifest(project_dir)
    files = manifest.get("files", [])
    tracked = {entry["path"] for entry in files}

    for entry in files:
        rel = entry["path"]
        live = project_dir / rel
        backup = core.sources_dir(project_dir) / rel
        backup_required = entry.get("backup_required", True)

        conv = registry.lookup_known_convention(rel)
        import_syntax = conv.get("import_syntax", "plain-pointer") if conv else "plain-pointer"

        # Check shim
        if not live.is_file():
            results.append({
                "kind": "shim",
                "path": rel,
                "state": "missing_shim",
                "import_syntax": import_syntax
            })
        elif not shim.is_shim_file(live):
            results.append({
                "kind": "shim",
                "path": rel,
                "state": "broken_shim",
                "import_syntax": import_syntax
            })
        else:
            results.append({
                "kind": "shim",
                "path": rel,
                "state": "healthy",
                "import_syntax": import_syntax
            })

        # Check backup
        if not backup_required:
            continue

        backup_rel = f"{core.CTX_DIRNAME}/{core.SOURCES_DIRNAME}/{rel}"
        if not backup.is_file():
            results.append({
                "kind": "backup",
                "path": backup_rel,
                "source": rel,
                "state": "missing_backup"
            })
        else:
            results.append({
                "kind": "backup",
                "path": backup_rel,
                "source": rel,
                "state": "healthy"
            })

    # 3. Check Candidates
    discovery = registry.detect_all(project_dir)
    candidate_keys = [
        "supported_folder_candidate",
        "legacy_or_uncertain_folder_candidate",
        "unverified_local_candidate",
        "verified_instruction_file",
    ]

    for key in candidate_keys:
        for cand in discovery.get(key, []):
            if cand["path"] not in tracked:
                results.append({
                    "kind": "candidate",
                    "path": cand["path"],
                    "state": "untracked_candidate",
                    "label": cand.get("label", "untracked candidate"),
                    "note": cand.get("note", "")
                })

    return results


def detect_repo_state(project_dir: Path) -> dict:
    project_dir = Path(project_dir)
    manifest_p = core.manifest_path(project_dir)
    ctx_dir = core.ctx_dir(project_dir)

    # 1. Managed Repo: `.ctx/` folder exists
    if ctx_dir.is_dir():
        reasons: list[str] = []
        is_legacy = False

        # Check manifest existence
        if not manifest_p.is_file():
            reasons.append("manifest_missing")
            candidates = []
            for entry in registry.instruction_conventions():
                live = project_dir / entry["path"]
                if live.is_file():
                    candidates.append(entry["path"])
                    if not shim.is_shim_file(live):
                        is_legacy = True

            if is_legacy:
                reasons.append("unbacked_live_file")
            state = "managed_legacy" if is_legacy else "managed_needs_repair"
            rec_action = "migrate" if is_legacy else "inspect"
            return {
                "state": state,
                "candidates": sorted(candidates),
                "reasons": sorted(reasons),
                "recommended_action": rec_action,
                "recommended_action_mutates_files": (rec_action == "migrate")
            }

        # Check manifest readability and schema validation
        manifest = None
        manifest_unreadable = False
        manifest_invalid = False

        try:
            manifest = core.load_manifest(project_dir)
        except core.SchemaError:
            manifest_invalid = True
        except Exception:
            manifest_unreadable = True

        if manifest_unreadable or manifest_invalid:
            reasons = ["manifest_unreadable" if manifest_unreadable else "manifest_invalid"]
            candidates = []
            for entry in registry.instruction_conventions():
                live = project_dir / entry["path"]
                if live.is_file():
                    candidates.append(entry["path"])

            return {
                "state": "managed_needs_repair",
                "candidates": sorted(candidates),
                "reasons": reasons,
                "recommended_action": "inspect",
                "recommended_action_mutates_files": False
            }

        # Check hub file
        hub_p = core.hub_path(project_dir)
        hub_unreadable = False
        try:
            if not hub_p.is_file():
                reasons.append("hub_missing")
            elif not hub_p.read_text(encoding="utf-8").strip():
                reasons.append("hub_empty")
        except Exception:
            hub_unreadable = True

        if hub_unreadable:
            reasons = ["hub_unreadable"]
            candidates = []
            for entry in registry.instruction_conventions():
                live = project_dir / entry["path"]
                if live.is_file():
                    candidates.append(entry["path"])

            return {
                "state": "managed_needs_repair",
                "candidates": sorted(candidates),
                "reasons": reasons,
                "recommended_action": "inspect",
                "recommended_action_mutates_files": False
            }

        files = manifest.get("files", [])
        tracked = {entry["path"] for entry in files}

        if "hub_missing" in reasons or "hub_empty" in reasons:
            return {
                "state": "managed_needs_repair",
                "candidates": [],
                "reasons": sorted(reasons),
                "recommended_action": "inspect",
                "recommended_action_mutates_files": False
            }

        for entry in files:
            rel = entry["path"]
            live = project_dir / rel
            backup = core.sources_dir(project_dir) / rel
            backup_required = entry.get("backup_required", True)

            if not live.is_file():
                reasons.append("missing_shim")
            elif not shim.is_shim_file(live):
                if backup_required and not backup.is_file():
                    reasons.append("unbacked_live_file")
                    is_legacy = True
                else:
                    reasons.append("broken_shim")

            if backup_required and not backup.is_file():
                reasons.append("missing_backup")

        # Include candidate files in reasons/candidates list
        discovery = registry.detect_all(project_dir)
        untracked = []
        for key in ["supported_folder_candidate", "legacy_or_uncertain_folder_candidate", "unverified_local_candidate", "verified_instruction_file"]:
            for cand in discovery.get(key, []):
                if cand["path"] not in tracked:
                    untracked.append(cand["path"])

        if untracked:
            reasons.append("untracked_candidates_found")

        critical_reasons = [r for r in reasons if r != "untracked_candidates_found"]

        if is_legacy:
            reasons.append("unbacked_live_file")
            state = "managed_legacy"
            rec_action = "migrate"
        elif critical_reasons:
            state = "managed_needs_repair"
            rec_action = "repair"
        else:
            state = "managed_healthy"
            rec_action = "none"

        return {
            "state": state,
            "candidates": sorted(untracked),
            "reasons": sorted(list(set(reasons))),
            "recommended_action": rec_action,
            "recommended_action_mutates_files": (rec_action != "none")
        }

    # 2. Unmanaged Repo: `.ctx/` does not exist
    else:
        detected = registry.detect(project_dir)
        if detected:
            candidates = sorted([c["path"] for c in detected])
            return {
                "state": "candidate_repo",
                "candidates": candidates,
                "reasons": ["known_instruction_files_found"],
                "recommended_action": "setup",
                "recommended_action_mutates_files": True
            }
        else:
            return {
                "state": "not_candidate",
                "candidates": [],
                "reasons": ["no_known_instruction_files"],
                "recommended_action": "none",
                "recommended_action_mutates_files": False
            }
