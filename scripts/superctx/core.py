"""Shared, deterministic helpers: paths, content normalization, hashing, manifest I/O."""

from __future__ import annotations

import hashlib
from pathlib import Path

from . import toml_compat

CTX_DIRNAME = ".ctx"
HUB_NAME = "SUPERCTX.md"
SOURCES_DIRNAME = "sources"
MANIFEST_NAME = "manifest.toml"


# --- paths ------------------------------------------------------------------

def ctx_dir(project_dir: Path) -> Path:
    return Path(project_dir) / CTX_DIRNAME


def sources_dir(project_dir: Path) -> Path:
    return ctx_dir(project_dir) / SOURCES_DIRNAME


def hub_path(project_dir: Path) -> Path:
    return ctx_dir(project_dir) / HUB_NAME


def manifest_path(project_dir: Path) -> Path:
    return ctx_dir(project_dir) / MANIFEST_NAME


# --- generated policy text --------------------------------------------------

def hub_policy_header(project_name: str) -> str:
    """Render the canonical-editable-hub policy banner + shared-context section.

    This is the top of a freshly generated hub. It must clearly tell agents that
    this file is the place to author shared context.
    """
    return (
        "# SuperCtx\n"
        "<!-- SuperCtx: AUTHOR HERE\n\n"
        "This is the canonical editable context hub for this repository.\n"
        "Edit this file to update shared project instructions.\n"
        "Generated tool files point here.\n"
        "`/superctx:sync` preserves edits in this file.\n"
        "-->\n\n"
        f"# SUPERCTX — {project_name}\n\n"
        "## Shared Project Context\n\n"
        "Write repo-wide instructions here. This section is not tied to any one "
        "assistant.\nIt is preserved by `/superctx:sync`.\n"
    )


_LEGACY_HUB_BANNER = "<!-- Canonical project context hub managed by SuperCtx. -->"


def ensure_hub_policy(text: str, project_name: str) -> tuple[str, bool]:
    """Prepend the canonical-editable-hub policy header to a hub that lacks it.

    Idempotent: if the hub already carries the policy (the AUTHOR HERE marker),
    returns (text, False) unchanged. Otherwise strips the legacy banner line and a
    leading duplicate ``# SUPERCTX — <name>`` title, prepends the policy header, and
    preserves all remaining user-authored content. Returns (new_text, True).
    """
    if "AUTHOR HERE" in text:
        return text, False

    body = text.replace("\r\n", "\n")
    lines = body.split("\n")
    # Drop the legacy banner line if present.
    lines = [ln for ln in lines if ln.strip() != _LEGACY_HUB_BANNER]
    # Drop a leading duplicate title; the policy header supplies its own.
    title = f"# SUPERCTX — {project_name}"
    pruned: list[str] = []
    removed_title = False
    for ln in lines:
        if not removed_title and ln.strip() == title:
            removed_title = True
            continue
        pruned.append(ln)
    remaining = "\n".join(pruned).strip("\n")

    header = hub_policy_header(project_name)
    new_text = header if not remaining else f"{header}\n{remaining}\n"
    return new_text, True


def sources_readme_text() -> str:
    """Render the backup-only README placed inside .ctx/sources/."""
    return (
        "# SuperCtx Backups\n\n"
        "<!-- SuperCtx: BACKUP DIRECTORY - DO NOT EDIT LIVE CONTEXT HERE -->\n\n"
        "This directory contains inactive backups of original pre-SuperCtx "
        "instruction files.\n\n"
        "Do not edit these files as live project context.\n"
        "Edit `../SUPERCTX.md` instead.\n\n"
        "These files are kept for recovery and audit only.\n"
    )


def ensure_sources_readme(project_dir: Path) -> bool:
    """Write .ctx/sources/README.md if the sources dir exists and the README is absent.

    Returns True if it wrote the README, False if it was already present or the
    sources dir does not exist. Idempotent.
    """
    sdir = sources_dir(project_dir)
    if not sdir.is_dir():
        return False
    readme = sdir / "README.md"
    if readme.is_file():
        return False
    readme.write_text(sources_readme_text(), encoding="utf-8")
    return True


# --- content ----------------------------------------------------------------

def normalize(text: str) -> str:
    """Normalize newlines to \\n, strip trailing whitespace per line, ensure one trailing \\n.

    Keeps health checks from firing on cosmetic whitespace/EOL differences.
    """
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    out = "\n".join(line.rstrip() for line in lines).rstrip("\n")
    return out + "\n" if out else ""


def content_hash(text: str) -> str:
    return hashlib.sha256(normalize(text).encode("utf-8")).hexdigest()


def read_text(path: Path) -> str:
    return Path(path).read_text(encoding="utf-8")


import os


class SchemaError(ValueError):
    """Raised when the manifest schema is invalid or has unsafe paths."""
    pass


# --- manifest ---------------------------------------------------------------

def load_manifest(project_dir: Path) -> dict:
    with manifest_path(project_dir).open("rb") as fh:
        data = toml_compat.load(fh)

    if not isinstance(data, dict):
        raise SchemaError("Manifest root must be a table")

    if "files" in data:
        if not isinstance(data["files"], list):
            raise SchemaError("Manifest 'files' must be an array")
        for entry in data["files"]:
            if not isinstance(entry, dict):
                raise SchemaError("Manifest 'files' entry must be a table")
            if "path" not in entry:
                raise SchemaError("Manifest 'files' entry is missing required 'path'")
            path_str = entry["path"]
            if not isinstance(path_str, str) or not path_str.strip():
                raise SchemaError("Manifest 'files' entry 'path' must be a non-empty string")

            # Safety check: Reject absolute paths or paths escaping the project root
            if Path(path_str).is_absolute():
                raise SchemaError(f"Manifest 'files' path cannot be absolute: {path_str}")
            norm = os.path.normpath(path_str)
            if norm.startswith("..") or norm.startswith("/") or norm == "..":
                raise SchemaError(f"Manifest 'files' path escapes repository root: {path_str}")

            if "tools" in entry and not isinstance(entry["tools"], list):
                raise SchemaError("Manifest 'files' entry 'tools' must be an array")
            if "backup_required" in entry and not isinstance(entry["backup_required"], bool):
                raise SchemaError("Manifest 'files' entry 'backup_required' must be a boolean")

    return data


def _toml_str(value: str) -> str:
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'


def _toml_array(items) -> str:
    return "[" + ", ".join(_toml_str(item) for item in items) + "]"


def _toml_bool(value: bool) -> str:
    return "true" if value else "false"


def dump_manifest(data: dict) -> str:
    """Serialize the small SuperCtx manifest schema to TOML (stdlib has no TOML writer).

    WARNING: This serializer is schema-rigid and only writes the [project] table and
    the [[files]] array. Unrecognized fields or custom keys in data will not be preserved.
    """
    project = data.get("project", {})
    lines = [
        "[project]",
        f'name = {_toml_str(project.get("name", ""))}',
        f'hub = {_toml_str(project.get("hub", f".ctx/{HUB_NAME}"))}',
        "",
    ]
    for entry in data.get("files", []):
        lines.append("[[files]]")
        lines.append(f'path = {_toml_str(entry["path"])}')
        lines.append(f'tools = {_toml_array(entry.get("tools", []))}')
        if "backup_required" in entry:
            lines.append(f'backup_required = {_toml_bool(entry["backup_required"])}')
        if "note" in entry:
            lines.append(f'note = {_toml_str(entry["note"])}')
        lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"
