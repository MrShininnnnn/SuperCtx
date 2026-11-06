from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from . import adopt, core, manifest as manifest_mod, registry, shim


class AddError(Exception):
    """Raised for command-level errors (missing files, invalid paths)."""
    pass


@dataclass(frozen=True)
class AddResult:
    path: str
    status: str    # "added" | "already_tracked"
    tools: list[str]
    message: str


def run(project_dir: Path, input_path: str, create_if_missing: bool = False) -> AddResult:
    project_dir = Path(project_dir).resolve()
    manifest_path = core.v2_manifest_path(project_dir)
    hub_path = core.hub_path(project_dir)

    # 1. Require the global sync flow to bootstrap repositories.
    ctx_dir = core.ctx_dir(project_dir)
    if not ctx_dir.is_dir():
        raise AddError(
            "SuperCtx is not set up for this repository. "
            "Use superctx sync to set up/check/repair the shared context before adding a specific file."
        )
    links = core.symlinked_ctx_entries(project_dir)
    if links:
        raise AddError(core.symlinked_ctx_message(links))
    if manifest_mod.locate(project_dir) in ("none", "orphaned"):
        raise AddError(
            "SuperCtx is present, but the configuration manifest is missing or invalid. "
            "Please inspect the setup."
        )

    # Rules, skills, and folders are adopted as links (matched on the path as given, not resolved).
    native = Path(input_path).as_posix().rstrip("/")
    resource = next((c for c in registry.detect_resources(project_dir) if c["path"] == native), None)
    if resource is not None:
        return _add_resource(project_dir, resource)
    # A connected folder is a link by now; _add_resource finds it in the manifest first.
    if (project_dir / native).is_dir():
        rel = os.path.normpath(native).replace(os.sep, "/")
        if rel in (".", "") or rel.startswith("../") or os.path.isabs(rel):
            raise AddError(f"Folder must be inside the project root and not the root itself: {input_path}")
        if rel.split("/")[0] in (core.CTX_DIRNAME, ".git"):
            raise AddError(f"Cannot add {rel}: SuperCtx and Git own this folder.")
        return _add_resource(project_dir, registry.folder_candidate(project_dir, rel, "reference"))

    file_path = Path(input_path)
    resolved_file_path = (project_dir / file_path).resolve()

    # 2. Validate path constraints
    file_exists = resolved_file_path.exists()
    if not file_exists and not create_if_missing:
        raise AddError(f"File does not exist: {input_path}")

    if file_exists and not resolved_file_path.is_file():
        raise AddError(f"Directories are not supported by add yet: {input_path}")

    try:
        rel_path = resolved_file_path.relative_to(project_dir)
    except ValueError:
        raise AddError(f"Path must be inside the project root: {input_path}")

    rel_path_str = rel_path.as_posix()

    if rel_path.parts and rel_path.parts[0] == core.CTX_DIRNAME:
        raise AddError("Cannot add files inside the .ctx directory.")
    # Tool configuration, hooks, and plugins must never become pointers: check the path as
    # given (normalized, links not followed), the file it resolves to, and links to it from tool folders.
    given_rel = Path(os.path.relpath(os.path.abspath(project_dir / file_path), project_dir)).as_posix()
    try:
        adopted = registry.adopted_tool_config(project_dir, [rel_path_str])
    except registry.ScanError as e:
        raise AddError(f"Cannot add {given_rel}: tool_folder_unreadable ({e}); SuperCtx cannot tell "
                       "whether a tool reads this file, so it changed nothing")
    if registry.in_tool_folder(given_rel) or registry.in_tool_folder(rel_path_str) or adopted:
        raise AddError(f"Cannot add {given_rel}: tool_folder")

    # 3. Detect duplicate/tracked state
    try:
        manifest_mod.migrate(project_dir)
        doc = manifest_mod.load_v2(project_dir)
    except (core.SchemaError, manifest_mod.MigrationError) as e:
        raise AddError(f"SuperCtx configuration manifest is invalid: {e}. Please inspect the setup.")
    except Exception as e:
        raise AddError(f"SuperCtx configuration manifest is unreadable: {e}. Please inspect the setup.")
    manifest = manifest_mod.view(doc)
    tracked_files = manifest["files"]

    for entry in tracked_files:
        if entry["path"] == rel_path_str:
            return AddResult(
                path=rel_path_str,
                status="already_tracked",
                tools=entry.get("tools", []),
                message=f"{rel_path_str} is already tracked."
            )

    # 4. Check backup collision and read content
    backup_file = core.sources_dir(project_dir) / rel_path_str

    if not file_exists:
        # Creating a new shim for a non-existent known convention file
        conv_check = registry.lookup_known_convention(rel_path_str)
        if not conv_check:
            raise AddError(
                f"File does not exist and '{input_path}' is not a recognized standard convention path. "
                f"Only known standard files (like GEMINI.md, .claude/CLAUDE.md) can be created as new shims."
            )
        original_content = ""
        is_live_shim = False
    else:
        live_content = resolved_file_path.read_text(encoding="utf-8")
        is_live_shim = shim.is_any_generated_pointer(live_content, rel_path_str)

        if not is_live_shim and backup_file.is_file():
            raise AddError(
                f"A backup already exists at {backup_file.relative_to(project_dir)}. "
                f"Please inspect the conflict between the backup file and your local version before connecting it."
            )

        # 5. Read original content
        if is_live_shim:
            # Read from backup if it exists, otherwise empty
            if backup_file.is_file():
                original_content = backup_file.read_text(encoding="utf-8")
            else:
                original_content = ""
        else:
            original_content = live_content

    # 6. Lookup known convention
    conv = registry.lookup_known_convention(rel_path_str)
    if conv:
        tools = conv.get("tools", [])
        note = None
    else:
        tools = []
        note = "user-confirmed local convention; not verified official path"

    # 7. Prepare updated manifest
    doc["natives"].append(manifest_mod.instruction_native(rel_path_str, tools, backup=file_exists, note=note,
                                                          published=False))
    try:
        new_manifest_content = manifest_mod.dump(manifest_mod.validate(doc))
    except core.SchemaError as e:
        raise AddError(f"Cannot add {rel_path_str}: {e}")

    # 8. Prepare updated hub
    new_hub_content = None
    if original_content.strip():
        # Ensure we have the hub file
        if hub_path.is_file():
            orig_hub_text = hub_path.read_text(encoding="utf-8")
        else:
            project_name = manifest.get("project", {}).get("name", "Project")
            orig_hub_text = core.hub_policy_header(project_name)

        suffix = f"  ({', '.join(tools)})" if tools else ""
        section = f"\n## From: {rel_path_str}{suffix}\n\n{core.normalize(original_content).strip()}\n"
        new_hub_content = orig_hub_text.rstrip() + "\n" + section

    # 9. Write with transactional rollback on failure
    orig_manifest_content = manifest_path.read_text(encoding="utf-8")
    orig_hub_content = hub_path.read_text(encoding="utf-8") if hub_path.is_file() else None
    live_existed_before = resolved_file_path.is_file()
    orig_live_content = resolved_file_path.read_text(encoding="utf-8") if live_existed_before else None
    backup_existed_before = backup_file.is_file()
    orig_backup_content = backup_file.read_text(encoding="utf-8") if backup_existed_before else None

    try:
        if new_hub_content is not None:
            hub_path.write_text(new_hub_content, encoding="utf-8")

        manifest_path.write_text(new_manifest_content, encoding="utf-8")

        apply_res = shim.apply_shim(
            project_dir,
            rel_path_str,
            force_backup=False,
            backup_required=file_exists,
        )
        if not apply_res.get("shimmed"):
            raise AddError(f"Failed to apply shim: {apply_res.get('reason')}")

    except Exception as e:
        # Rollback manifest
        manifest_path.write_text(orig_manifest_content, encoding="utf-8")
        # Rollback hub
        if orig_hub_content is not None:
            hub_path.write_text(orig_hub_content, encoding="utf-8")
        elif hub_path.is_file():
            hub_path.unlink()

        # Rollback live file and backup side effects from apply_shim.
        if live_existed_before:
            resolved_file_path.write_text(orig_live_content or "", encoding="utf-8")
        elif resolved_file_path.is_file():
            resolved_file_path.unlink()

        if backup_existed_before:
            backup_file.parent.mkdir(parents=True, exist_ok=True)
            backup_file.write_text(orig_backup_content or "", encoding="utf-8")
        elif backup_file.is_file():
            backup_file.unlink()

        if isinstance(e, AddError):
            raise e
        raise AddError(str(e)) from e

    manifest_mod.mark_published(project_dir, {rel_path_str})

    if not file_exists:
        msg = (
            f"Created {rel_path_str} as a generated shim pointing to "
            f".ctx/{core.HUB_NAME}. "
            f"Agents read the hub through their shims automatically."
        )
    else:
        msg = (
            f"Added {rel_path_str}. Original content backed up, incorporated into "
            f".ctx/{core.HUB_NAME}, and replaced with a generated shim. "
            f"Agents read the hub through their shims automatically."
        )

    return AddResult(
        path=rel_path_str,
        status="added",
        tools=tools,
        message=msg
    )


def _add_resource(project_dir: Path, cand: dict) -> AddResult:
    """Adopt one rule or skill: back it up, record it, then move it and link it."""
    try:
        manifest_mod.migrate(project_dir)
        doc = manifest_mod.load_v2(project_dir)
    except (core.SchemaError, manifest_mod.MigrationError) as e:
        raise AddError(f"SuperCtx configuration manifest is invalid: {e}. Please inspect the setup.")
    except Exception as e:
        raise AddError(f"SuperCtx configuration manifest is unreadable: {e}. Please inspect the setup.")

    if any(n["path"] == cand["path"] for n in doc["natives"]):
        return AddResult(path=cand["path"], status="already_tracked", tools=cand["tools"],
                         message=f"{cand['path']} is already tracked.")
    extra = [] if any(c["path"] == cand["path"] for c in registry.detect_resources(project_dir)) else [cand]
    adoptable, left = adopt.plan(project_dir, doc, explicit=True, extra=extra)
    reason = next((item["reason"] for item in left if item["path"] == cand["path"]), None)
    if reason is None and not adopt.links_supported(project_dir):
        reason = "links_unsupported"
    if reason is not None:
        raise AddError(f"Cannot add {cand['path']}: {reason}")

    backup_rel = adopt.backup(project_dir, cand["path"], project_dir)
    resource, native = adopt.manifest_entries(cand)
    doc["resources"].append(resource)
    doc["natives"].append(native)
    try:
        manifest_mod.write(project_dir, doc)
    except Exception as e:
        # The backup did not exist before this call (plan checked), so it is ours to remove.
        backup_path = project_dir / backup_rel
        shutil.rmtree(backup_path) if backup_path.is_dir() else backup_path.unlink()
        raise AddError(f"Failed to record {cand['path']}: {e}") from e

    status, reason = adopt.publish_link(project_dir, cand["path"], cand["canonical"], published=False)
    if status == "conflict":
        msg = f"Recorded {cand['path']}, but could not link it ({reason}); sync will report it."
    else:
        manifest_mod.mark_published(project_dir, {cand["path"]})
        msg = (f"Added {cand['path']}. Original backed up to {backup_rel}, moved to "
               f"{cand['canonical']}, and linked back to its original path.")
    return AddResult(path=cand["path"], status="added", tools=cand["tools"], message=msg)
