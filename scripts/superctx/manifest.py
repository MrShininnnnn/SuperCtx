"""v2 manifest (.ctx/superctx.toml): schema, workspace state, and v1 migration.

See architecture/v2-manifest-and-ownership.md for the ownership model and the
migration state table.
"""

from __future__ import annotations

import io
import os
import re
import tempfile
from pathlib import Path, PurePosixPath, PureWindowsPath

from . import core, toml_compat

SCHEMA = 2
TYPES = ("instructions", "rule", "skill", "reference", "planning")
MODES = ("pointer", "link", "generated")
INSTRUCTIONS_ID = "instructions"

SENTINEL_VALUE = "SuperCtx 0.2+ manages this repository; see .ctx/superctx.toml"
IN_PROGRESS = "in-progress"
COMPLETE = "complete"

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_ROOT_KEYS = {"schema", "project", "resources", "natives"}
_PROJECT_KEYS = {"name"}
_RESOURCE_KEYS = {"id", "type", "canonical"}
_NATIVE_KEYS = {"resource", "path", "mode", "tools", "backup", "note", "published_hash"}
_RESERVED_CANONICALS = {
    f"{core.CTX_DIRNAME}/{name}" for name in (core.MANIFEST_NAME, core.V2_MANIFEST_NAME, core.V1_BACKUP_NAME)
}

# Indirection so tests can simulate a crash around each atomic replace.
_replace = os.replace


class MigrationError(Exception):
    """Raised when a workspace cannot be migrated without risking data loss."""
    pass


def sentinel_text(migration: str) -> str:
    return (
        "# SuperCtx 0.2+ manages this repository through .ctx/superctx.toml.\n"
        "# This sentinel is deliberately invalid for SuperCtx 0.1.x so older clients\n"
        "# refuse to modify the repository. Upgrade SuperCtx; do not edit or delete it.\n"
        f"files = {core._toml_str(SENTINEL_VALUE)}\n"
        f"migration = {core._toml_str(migration)}\n"
    )


def _parse(text: str) -> dict:
    return toml_compat.load(io.BytesIO(text.encode("utf-8")))


def _atomic_write(path: Path, text: str) -> None:
    # mkstemp creates a new file exclusively (O_CREAT | O_EXCL), so a symlink or
    # file already sitting at a predictable temp name is never followed or reused.
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            if hasattr(os, "fchmod"):
                # mkstemp creates 0600; give the manifest the usual umask-based mode.
                umask = os.umask(0)
                os.umask(umask)
                os.fchmod(fh.fileno(), 0o666 & ~umask)
            fh.write(text)
        _replace(tmp, path)
    finally:
        if os.path.lexists(tmp):
            os.unlink(tmp)


def _sentinel_state(path: Path) -> str | None:
    """None if absent, IN_PROGRESS or COMPLETE for a sentinel, "other" for anything else."""
    if not os.path.lexists(path):
        return None
    if not path.is_file():
        # A directory or dangling symlink is not absent; never write over it.
        return "other"
    try:
        data = _parse(path.read_text(encoding="utf-8"))
    except Exception:
        return "other"
    if data.get("files") != SENTINEL_VALUE:
        return "other"
    # Anything but an explicit in-progress marker counts as complete, so an
    # unknown value never allows a rebuild from the v1 copy.
    return IN_PROGRESS if data.get("migration") == IN_PROGRESS else COMPLETE


def locate(project_dir: Path) -> str:
    """Classify the workspace's manifest files (see the state table in the ADR)."""
    has_v2 = core.v2_manifest_path(project_dir).is_file()
    sentinel = _sentinel_state(core.manifest_path(project_dir))

    if has_v2:
        if sentinel == COMPLETE:
            return "v2"
        if sentinel in (None, IN_PROGRESS):
            return "v2_unsealed"
        return "conflict"
    if sentinel is None:
        # Without either manifest, any surviving .ctx/ content (hub, backups, v1
        # copy, canonical resources) still marks an existing workspace.
        cdir = core.ctx_dir(project_dir)
        if cdir.is_dir() and any(cdir.iterdir()):
            return "orphaned"
        return "none"
    if sentinel == "other":
        return "v1"
    if sentinel == IN_PROGRESS and core.v1_backup_path(project_dir).is_file():
        return "interrupted"
    return "lost"


# --- schema -----------------------------------------------------------------

def _check_rel_path(value, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise core.SchemaError(f"{label} must be a non-empty string")
    # PurePosixPath treats "C:/x" and "C:x" as relative; Windows would not.
    if "\\" in value or PurePosixPath(value).is_absolute() or PureWindowsPath(value).drive:
        raise core.SchemaError(f"{label} must be a relative POSIX path: {value}")
    parts = PurePosixPath(value).parts
    if not parts or ".." in parts or PurePosixPath(*parts).as_posix() != value:
        raise core.SchemaError(f"{label} must be a normalized path inside the repository: {value}")
    return value


def _check_keys(table, allowed: set, label: str) -> None:
    if not isinstance(table, dict):
        raise core.SchemaError(f"{label} must be a table")
    unknown = sorted(set(table) - allowed)
    if unknown:
        raise core.SchemaError(f"{label} has unknown keys: {', '.join(unknown)}")


def validate(doc: dict) -> dict:
    _check_keys(doc, _ROOT_KEYS, "Manifest")
    if doc.get("schema") != SCHEMA or isinstance(doc.get("schema"), bool):
        raise core.SchemaError(f"Manifest 'schema' must be {SCHEMA}")
    _check_keys(doc.get("project", {}), _PROJECT_KEYS, "Manifest [project]")
    if not isinstance(doc.get("project", {}).get("name", ""), str):
        raise core.SchemaError("Manifest [project] 'name' must be a string")

    resources = doc.get("resources", [])
    natives = doc.get("natives", [])
    if not isinstance(resources, list) or not isinstance(natives, list):
        raise core.SchemaError("Manifest 'resources' and 'natives' must be arrays of tables")

    types: dict[str, str] = {}
    canonicals: set[str] = set()
    for res in resources:
        _check_keys(res, _RESOURCE_KEYS, "Manifest [[resources]] entry")
        rid = res.get("id")
        if not isinstance(rid, str) or not _ID_RE.match(rid):
            raise core.SchemaError(f"Resource id is invalid: {rid!r}")
        if rid in types:
            raise core.SchemaError(f"Duplicate resource id: {rid}")
        if res.get("type") not in TYPES:
            raise core.SchemaError(f"Resource {rid} has unknown type: {res.get('type')!r}")
        canonical = _check_rel_path(res.get("canonical"), f"Resource {rid} 'canonical'")
        sources = f"{core.CTX_DIRNAME}/{core.SOURCES_DIRNAME}"
        if not canonical.startswith(f"{core.CTX_DIRNAME}/") or canonical == sources or canonical.startswith(sources + "/"):
            raise core.SchemaError(f"Resource {rid} 'canonical' must be under .ctx/ and outside .ctx/sources/: {canonical}")
        if canonical in _RESERVED_CANONICALS:
            raise core.SchemaError(f"Resource {rid} 'canonical' is a reserved manifest path: {canonical}")
        if canonical in canonicals:
            raise core.SchemaError(f"Duplicate canonical path: {canonical}")
        types[rid] = res["type"]
        canonicals.add(canonical)

    hub = f"{core.CTX_DIRNAME}/{core.HUB_NAME}"
    instructions = [r for r in resources if r["type"] == "instructions"]
    if len(instructions) != 1 or instructions[0]["id"] != INSTRUCTIONS_ID or instructions[0]["canonical"] != hub:
        raise core.SchemaError(f"Manifest must have exactly one instructions resource, id '{INSTRUCTIONS_ID}', canonical {hub}")

    paths: list[str] = []
    for nat in natives:
        _check_keys(nat, _NATIVE_KEYS, "Manifest [[natives]] entry")
        path = _check_rel_path(nat.get("path"), "Native 'path'")
        if PurePosixPath(path).parts[0] == core.CTX_DIRNAME:
            raise core.SchemaError(f"Native path cannot be inside .ctx/: {path}")
        rid = nat.get("resource")
        if rid not in types:
            raise core.SchemaError(f"Native {path} references unknown resource: {rid!r}")
        mode = nat.get("mode")
        if mode not in MODES:
            raise core.SchemaError(f"Native {path} has unknown mode: {mode!r}")
        if types[rid] == "instructions" and mode != "pointer":
            raise core.SchemaError(f"Native {path}: instructions natives must use pointer mode")
        tools = nat.get("tools", [])
        if not isinstance(tools, list) or not all(isinstance(t, str) for t in tools):
            raise core.SchemaError(f"Native {path} 'tools' must be an array of strings")
        if not isinstance(nat.get("backup", True), bool):
            raise core.SchemaError(f"Native {path} 'backup' must be a boolean")
        if "note" in nat and not isinstance(nat["note"], str):
            raise core.SchemaError(f"Native {path} 'note' must be a string")
        if mode == "generated":
            if not isinstance(nat.get("published_hash"), str) or not _HASH_RE.match(nat["published_hash"]):
                raise core.SchemaError(f"Native {path}: generated mode requires published_hash = \"sha256:<64 hex>\"")
        elif "published_hash" in nat:
            raise core.SchemaError(f"Native {path}: published_hash is only allowed in generated mode")
        for other in paths:
            if path == other or path.startswith(other + "/") or other.startswith(path + "/"):
                raise core.SchemaError(f"Native paths collide: {other} and {path}")
        paths.append(path)

    return doc


def load_v2(project_dir: Path) -> dict:
    with core.v2_manifest_path(project_dir).open("rb") as fh:
        data = toml_compat.load(fh)
    doc = validate(data)
    # TOML has no syntax for an empty array of tables.
    doc.setdefault("resources", [])
    doc.setdefault("natives", [])
    return doc


def dump(doc: dict) -> str:
    lines = [
        f"schema = {SCHEMA}",
        "",
        "[project]",
        f"name = {core._toml_str(doc.get('project', {}).get('name', ''))}",
        "",
    ]
    for res in doc.get("resources", []):
        lines += [
            "[[resources]]",
            f"id = {core._toml_str(res['id'])}",
            f"type = {core._toml_str(res['type'])}",
            f"canonical = {core._toml_str(res['canonical'])}",
            "",
        ]
    for nat in doc.get("natives", []):
        lines += [
            "[[natives]]",
            f"resource = {core._toml_str(nat['resource'])}",
            f"path = {core._toml_str(nat['path'])}",
            f"mode = {core._toml_str(nat['mode'])}",
            f"tools = {core._toml_array(nat.get('tools', []))}",
            f"backup = {core._toml_bool(nat.get('backup', True))}",
        ]
        if "note" in nat:
            lines.append(f"note = {core._toml_str(nat['note'])}")
        if "published_hash" in nat:
            lines.append(f"published_hash = {core._toml_str(nat['published_hash'])}")
        lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"


def new_doc(project_name: str) -> dict:
    return {
        "schema": SCHEMA,
        "project": {"name": project_name},
        "resources": [{
            "id": INSTRUCTIONS_ID,
            "type": "instructions",
            "canonical": f"{core.CTX_DIRNAME}/{core.HUB_NAME}",
        }],
        "natives": [],
    }


def instruction_native(path: str, tools: list, backup: bool = True, note: str | None = None) -> dict:
    native = {"resource": INSTRUCTIONS_ID, "path": path, "mode": "pointer", "tools": list(tools), "backup": backup}
    if note is not None:
        native["note"] = note
    return native


def from_v1(v1: dict) -> dict:
    doc = new_doc(v1.get("project", {}).get("name", ""))
    for entry in v1.get("files", []):
        doc["natives"].append(instruction_native(
            entry["path"], entry.get("tools", []), entry.get("backup_required", True), entry.get("note"),
        ))
    return validate(doc)


def view(doc: dict) -> dict:
    """The {project, files} shape the shim engine works with: instruction pointers only."""
    files = []
    for nat in doc.get("natives", []):
        if nat["resource"] != INSTRUCTIONS_ID:
            continue
        entry = {"path": nat["path"], "tools": nat.get("tools", []), "backup_required": nat.get("backup", True)}
        if "note" in nat:
            entry["note"] = nat["note"]
        files.append(entry)
    return {
        "project": {"name": doc.get("project", {}).get("name", ""), "hub": f"{core.CTX_DIRNAME}/{core.HUB_NAME}"},
        "files": files,
    }


def load_view(project_dir: Path) -> dict:
    kind = locate(project_dir)
    if kind in ("v2", "v2_unsealed"):
        return view(load_v2(project_dir))
    if kind == "v1":
        return core.load_v1_manifest(core.manifest_path(project_dir))
    if kind in ("none", "orphaned"):
        raise FileNotFoundError(f"No SuperCtx manifest in {core.ctx_dir(project_dir)}")
    raise core.SchemaError(f"SuperCtx manifest state is {kind}")


# --- writing ----------------------------------------------------------------

def write(project_dir: Path, doc: dict) -> None:
    """Write a v2 manifest, then seal it with the complete sentinel."""
    _atomic_write(core.v2_manifest_path(project_dir), dump(validate(doc)))
    _atomic_write(core.manifest_path(project_dir), sentinel_text(COMPLETE))


def migrate(project_dir: Path) -> bool:
    """Migrate a v1 workspace, resume an interrupted migration, or seal an unsealed v2 manifest.

    Returns True if anything was written, False if the workspace is already v2 or
    not set up. Raises MigrationError for states that need a person: a lost v2
    manifest, conflicting manifest files, or an invalid v1 manifest.
    """
    project_dir = Path(project_dir)
    kind = locate(project_dir)
    manifest_p = core.manifest_path(project_dir)
    backup_p = core.v1_backup_path(project_dir)

    if kind in ("v2", "none", "orphaned"):
        return False

    if kind == "v2_unsealed":
        load_v2(project_dir)
        _atomic_write(manifest_p, sentinel_text(COMPLETE))
        return True

    if kind == "lost":
        raise MigrationError(
            ".ctx/superctx.toml is missing from a migrated workspace. It is not rebuilt from "
            ".ctx/manifest.v1.toml because that would drop v2-only resources; restore it from version control."
        )
    if kind == "conflict":
        raise MigrationError(
            ".ctx/superctx.toml exists but .ctx/manifest.toml is not a SuperCtx 0.2 sentinel; inspect both files."
        )

    source_p = backup_p if kind == "interrupted" else manifest_p
    source = f"{core.CTX_DIRNAME}/{source_p.name}"
    try:
        v1_text = source_p.read_text(encoding="utf-8")
        doc = from_v1(core.validate_v1(_parse(v1_text)))
    except Exception as e:
        raise MigrationError(f"{source} is not a valid SuperCtx 0.1.x manifest: {e}") from e

    if kind == "v1":
        _atomic_write(backup_p, v1_text)
        _atomic_write(manifest_p, sentinel_text(IN_PROGRESS))
    _atomic_write(core.v2_manifest_path(project_dir), dump(doc))
    _atomic_write(manifest_p, sentinel_text(COMPLETE))
    return True
