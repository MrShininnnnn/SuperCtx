"""Prototype v0.1.x -> v2 manifest migration (test-only; not shipped).

Proves an ordering that keeps unpatched 0.1.x clients safe and lets an
interrupted migration resume. The v2 schema here is provisional; the real one
belongs to the ownership/manifest work that follows.

Write order:
  1. copy the v1 manifest to .ctx/manifest.v1.toml
  2. replace .ctx/manifest.toml with the legacy sentinel
  3. write .ctx/superctx.toml

Before step 2 the repository is still a plain v1 repository (old clients may
keep using it, and a resume re-reads the live v1 manifest). From step 2 on,
every 0.1.x loader rejects the sentinel, and a resume rebuilds the v2 manifest
from the step-1 copy.
"""

from __future__ import annotations

import io
import os
from pathlib import Path

from superctx import core, toml_compat

V2_MANIFEST_NAME = "superctx.toml"
V1_BACKUP_NAME = "manifest.v1.toml"

# A string where 0.1.x requires an array of tables: valid TOML for every loader
# (tomllib, tomli, toml_compat's minimal parser), but core.load_manifest raises
# SchemaError, which sends sync/add/init down their no-write branches.
SENTINEL_VALUE = "SuperCtx 0.2+ manages this repository; see .ctx/superctx.toml"
SENTINEL_TEXT = (
    "# SuperCtx 0.2+ manages this repository through .ctx/superctx.toml.\n"
    "# This sentinel is deliberately invalid for SuperCtx 0.1.x so older clients\n"
    "# refuse to modify the repository. Upgrade SuperCtx; do not edit or delete it.\n"
    f"files = {core._toml_str(SENTINEL_VALUE)}\n"
)

# Indirection so tests can simulate a crash around each atomic replace.
_replace = os.replace


class MigrationError(Exception):
    pass


def _parse(text: str) -> dict:
    return toml_compat.load(io.BytesIO(text.encode("utf-8")))


def _atomic_write(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    _replace(tmp, path)


def is_sentinel(path: Path) -> bool:
    try:
        return _parse(path.read_text(encoding="utf-8")).get("files") == SENTINEL_VALUE
    except Exception:
        return False


def render_v2(v1: dict) -> str:
    project = v1.get("project", {})
    lines = [
        "schema = 2",
        "",
        "[project]",
        f"name = {core._toml_str(project.get('name', ''))}",
        "",
        "[[resources]]",
        'id = "instructions"',
        'type = "instructions"',
        f"canonical = {core._toml_str(project.get('hub', f'.ctx/{core.HUB_NAME}'))}",
        'mode = "pointer"',
        "",
    ]
    for entry in v1.get("files", []):
        lines += [
            "[[natives]]",
            'resource = "instructions"',
            f"path = {core._toml_str(entry['path'])}",
            f"tools = {core._toml_array(entry.get('tools', []))}",
            f"backup_required = {core._toml_bool(entry.get('backup_required', True))}",
        ]
        if "note" in entry:
            lines.append(f"note = {core._toml_str(entry['note'])}")
        lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"


def migrate(project_dir: Path) -> bool:
    """Migrate (or resume migrating) a v0.1.x repository. Returns True if anything was written."""
    project_dir = Path(project_dir)
    cdir = core.ctx_dir(project_dir)
    manifest = core.manifest_path(project_dir)
    v2 = cdir / V2_MANIFEST_NAME
    backup = cdir / V1_BACKUP_NAME

    if is_sentinel(manifest):
        if v2.is_file():
            return False
        if not backup.is_file():
            raise MigrationError(
                "Sentinel present but neither .ctx/superctx.toml nor .ctx/manifest.v1.toml exists."
            )
        v1_text = backup.read_text(encoding="utf-8")
    else:
        try:
            core.load_manifest(project_dir)
        except Exception as e:
            raise MigrationError(f"Not a valid SuperCtx 0.1.x manifest: {e}") from e
        v1_text = manifest.read_text(encoding="utf-8")
        _atomic_write(backup, v1_text)
        _atomic_write(manifest, SENTINEL_TEXT)

    _atomic_write(v2, render_v2(_parse(v1_text)))
    return True
