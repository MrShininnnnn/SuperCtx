from __future__ import annotations

from pathlib import Path
from . import core, registry, shim

_BANNER = (
    "<!-- Canonical project context hub. Edit this file to update instructions. -->\n"
)

def run(project_dir: Path) -> dict:
    project_dir = Path(project_dir)
    cdir = core.ctx_dir(project_dir)

    discovery = registry.detect_all(project_dir)
    untracked = []
    for key in ["supported_folder_candidate", "legacy_or_uncertain_folder_candidate", "unverified_local_candidate"]:
        for cand in discovery[key]:
            untracked.append(cand["path"])

    if core.manifest_path(project_dir).is_file():
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
            if not shim.is_shim_file(project_dir / rel):
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

    verified = discovery["verified_instruction_file"]

    # 1. Read all original contents
    originals = {}
    for c in verified:
        rel = c["path"]
        live = project_dir / rel
        if live.is_file():
            originals[rel] = live.read_text(encoding="utf-8")
        else:
            originals[rel] = ""

    # 2. Write manifest and hub files
    cdir.mkdir(parents=True, exist_ok=True)
    core.sources_dir(project_dir).mkdir(parents=True, exist_ok=True)

    manifest = {
        "project": {
            "name": project_dir.resolve().name,
            "hub": f"{core.CTX_DIRNAME}/{core.HUB_NAME}",
        },
        "files": [{"path": c["path"], "tools": c.get("tools", [])} for c in verified],
    }
    core.manifest_path(project_dir).write_text(core.dump_manifest(manifest), encoding="utf-8")

    sections = []
    for c in verified:
        rel = c["path"]
        tools = c.get("tools", [])
        suffix = f"  ({', '.join(tools)})" if tools else ""
        sections.append(f"## From: {rel}{suffix}\n\n{originals[rel].strip()}\n")

    name = manifest["project"]["name"]
    body = "\n".join(sections) if sections else "_No tracked files found to centralize._\n"
    hub_content = f"{_BANNER}\n# SUPERCTX — {name}\n\n{body}"
    core.hub_path(project_dir).write_text(hub_content.rstrip() + "\n", encoding="utf-8")

    # 3. Create .gitignore
    gitignore_body = "# Inactive backup storage for original instruction files.\nsources/\n"
    (cdir / ".gitignore").write_text(gitignore_body, encoding="utf-8")

    # 4. Perform backups and replace registered files with shims
    connected = []
    backups = []
    failed_shims = []

    for c in verified:
        rel = c["path"]
        apply_res = shim.apply_shim(project_dir, rel, force_backup=False)
        if apply_res["shimmed"]:
            connected.append(rel)
            if apply_res["backup_path"]:
                backups.append(apply_res["backup_path"])
        else:
            failed_shims.append(rel)

    ret = {
        "created": True,
        "ctx_dir": str(cdir),
        "connected": connected,
        "detected": connected,
        "backups": backups,
        "hub": f"{core.CTX_DIRNAME}/{core.HUB_NAME}",
        "untracked": untracked,
        "discovery": discovery,
    }
    if failed_shims:
        ret["partial_shim_failure"] = True
        ret["failed_shims"] = failed_shims

    return ret
