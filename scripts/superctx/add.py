from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import core, registry, shim


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
    manifest_path = core.manifest_path(project_dir)
    hub_path = core.hub_path(project_dir)

    # 1. Validate manifest exists
    if not manifest_path.exists():
        raise AddError("SuperCtx is not initialized in this project. Run 'superctx init' first.")

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

    # 3. Detect duplicate/tracked state
    manifest = core.load_manifest(project_dir)
    tracked_files = manifest.setdefault("files", [])

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
        is_live_shim = shim.is_shim(live_content)

        if not is_live_shim and backup_file.is_file():
            raise AddError(
                f"A backup already exists at {backup_file.relative_to(project_dir)}. "
                f"To resolve, remove the conflicting backup file in .ctx/sources/ and run /superctx:add <path> again."
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
    new_entry = {
        "path": rel_path_str,
        "tools": tools
    }
    if not file_exists:
        new_entry["backup_required"] = False
    if note:
        new_entry["note"] = note
    tracked_files.append(new_entry)
    new_manifest_content = core.dump_manifest(manifest)

    # 8. Prepare updated hub
    new_hub_content = None
    if original_content.strip():
        # Ensure we have the hub file
        if hub_path.is_file():
            orig_hub_text = hub_path.read_text(encoding="utf-8")
        else:
            orig_hub_text = f"# SUPERCTX — {manifest.get('project', {}).get('name', 'Project')}\n"

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
