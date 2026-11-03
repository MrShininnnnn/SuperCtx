from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from . import adopt, core, manifest as manifest_mod, registry, shim


def run(project_dir: Path) -> dict:
    project_dir = Path(project_dir)
    cdir = core.ctx_dir(project_dir)

    discovery = registry.detect_all(project_dir)
    untracked = []
    for key in ["supported_folder_candidate", "legacy_or_uncertain_folder_candidate", "unverified_local_candidate"]:
        for cand in discovery[key]:
            untracked.append(cand["path"])

    links = core.symlinked_ctx_entries(project_dir)
    if links:
        return {
            "created": False,
            "reason": "unsafe_path",
            "ctx_dir": str(cdir),
            "partially_migrated": True,
            "manifest_error": core.symlinked_ctx_message(links),
            "connected": [],
            "detected": [],
            "hub": f"{core.CTX_DIRNAME}/{core.HUB_NAME}",
            "untracked": untracked,
        }

    if manifest_mod.locate(project_dir) != "none":
        manifest_error = None
        try:
            manifest = core.load_manifest(project_dir)
            files = manifest.get("files", [])
        except Exception as e:
            files = []
            manifest_error = str(e)

        if manifest_error:
            return {
                "created": False,
                "reason": "exists",
                "ctx_dir": str(cdir),
                "partially_migrated": True,
                "manifest_error": manifest_error,
                "connected": [],
                "detected": [],
                "hub": f"{core.CTX_DIRNAME}/{core.HUB_NAME}",
                "untracked": untracked,
            }

        broken_shims = []
        for entry in files:
            rel = entry["path"]
            if not shim.is_generated_pointer_file(project_dir, rel, entry.get("backup_required", True)):
                broken_shims.append(rel)

        return {
            "created": False,
            "reason": "exists",
            "ctx_dir": str(cdir),
            "partially_migrated": len(broken_shims) > 0,
            "broken_shims": broken_shims,
            "connected": [entry["path"] for entry in files],
            "detected": [entry["path"] for entry in files],
            "hub": f"{core.CTX_DIRNAME}/{core.HUB_NAME}",
            "untracked": untracked,
        }

    # 1. Plan: instruction pointers and linkable rules and skills; everything else stays put.
    left_in_place = []
    pointers = []
    for c in discovery["verified_instruction_file"]:
        if shim._is_safe_target(project_dir, c["path"]):
            pointers.append(c)
        else:
            left_in_place.append({"path": c["path"], "type": "instructions", "reason": "unsafe_path"})
    resources, left = adopt.plan(project_dir)
    left_in_place += left

    # 2. Build the whole .ctx/ (backups, hub, manifest) in a staging directory and
    #    install it with one rename, so a failure here leaves the repository untouched.
    _remove_stale_staging(project_dir)
    staging = Path(tempfile.mkdtemp(prefix=STAGING_PREFIX, dir=project_dir))
    try:
        (staging / STAGING_MARKER).write_text("", encoding="utf-8")
        core.ctx_dir(staging).mkdir()
        backups = [adopt.backup(project_dir, item["path"], staging) for item in pointers + resources]
        core.ensure_sources_readme(staging)

        doc = manifest_mod.new_doc(project_dir.resolve().name)
        doc["natives"] = [manifest_mod.instruction_native(c["path"], c.get("tools", []), published=False)
                          for c in pointers]
        for cand in resources:
            resource, native = adopt.manifest_entries(cand)
            doc["resources"].append(resource)
            doc["natives"].append(native)

        sections = []
        for c in pointers:
            rel = c["path"]
            tools = c.get("tools", [])
            suffix = f"  ({', '.join(tools)})" if tools else ""
            original = (project_dir / rel).read_text(encoding="utf-8")
            sections.append(f"## From: {rel}{suffix}\n\n{original.strip()}\n")
        header = core.hub_policy_header(doc["project"]["name"])
        body = "\n".join(sections) if sections else "_No tracked files found to centralize._\n"
        core.hub_path(staging).write_text(f"{header}\n{body}".rstrip() + "\n", encoding="utf-8")

        gitignore_body = "# Inactive backup storage for original instruction files, rules, and skills.\nsources/\n"
        (core.ctx_dir(staging) / ".gitignore").write_text(gitignore_body, encoding="utf-8")
        manifest_mod.write(staging, doc)

        _install_staged_ctx(staging, project_dir)
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    # 3. Publish each native. Every step can be repeated, so sync finishes an interrupted run.
    connected, linked, failed_reasons = _publish(project_dir, pointers, resources)
    manifest_mod.mark_published(project_dir, set(connected) | set(linked))

    ret = {
        "created": True,
        "ctx_dir": str(cdir),
        "connected": connected,
        "detected": connected,
        "linked": linked,
        "left_in_place": left_in_place,
        "backups": backups,
        "hub": f"{core.CTX_DIRNAME}/{core.HUB_NAME}",
        "untracked": untracked,
        "discovery": discovery,
    }
    if failed_reasons:
        ret["partial_shim_failure"] = True
        ret["failed_shims"] = list(failed_reasons)
        ret["failed_reasons"] = failed_reasons

    return ret


STAGING_PREFIX = ".superctx-staging-"
STAGING_MARKER = ".superctx-staging"


def _remove_stale_staging(project_dir: Path) -> None:
    """Remove staging directories a crashed setup left behind (only ones carrying our marker)."""
    for path in Path(project_dir).glob(f"{STAGING_PREFIX}*"):
        if path.is_dir() and not path.is_symlink() and (path / STAGING_MARKER).is_file():
            shutil.rmtree(path)


def _install_staged_ctx(staging: Path, project_dir: Path) -> None:
    # Replaces a missing or empty .ctx/ in one step.
    os.rename(core.ctx_dir(staging), core.ctx_dir(project_dir))


def _publish(project_dir: Path, pointers: list[dict], resources: list[dict]) -> tuple[list, list, dict]:
    connected, linked, failed = [], [], {}
    for c in pointers:
        res = shim.publish_pointer(project_dir, c["path"], published=False)
        if res["shimmed"]:
            connected.append(c["path"])
        else:
            failed[c["path"]] = res["reason"]
    for cand in resources:
        status, reason = adopt.publish_link(project_dir, cand["path"], cand["canonical"], published=False)
        if status == "conflict":
            failed[cand["path"]] = reason
        else:
            linked.append(cand["path"])
    return connected, linked, failed
