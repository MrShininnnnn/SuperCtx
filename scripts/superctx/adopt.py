"""Linked resources: rules and skills that live under .ctx/ with a symlink at their native path.

Adoption backs up the native resource, moves it to its canonical path, and leaves a
relative symlink behind. Every step can be repeated, so an interrupted adoption is
finished by the next sync. See architecture/v2-manifest-and-ownership.md.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from . import core, registry

# Indirection so tests can simulate a crash between moving a resource and linking it.
_symlink = os.symlink


def _no_symlinked_parent(root: Path, rel: str) -> bool:
    """True if no directory between the repository root and rel is a symlink."""
    parent = (root / rel).parent
    try:
        return parent.resolve() == parent
    except (OSError, RuntimeError):
        return False


def link_target(native: str, canonical: str) -> str:
    """The relative symlink target that points native at canonical."""
    return os.path.relpath(canonical, os.path.dirname(native) or ".").replace("\\", "/")


def plan(project_dir: Path, doc: dict | None = None) -> tuple[list[dict], list[dict]]:
    """Split discovered, untracked rules and skills into (adoptable, left in place with a reason)."""
    root = Path(project_dir).resolve()
    tracked = {n["path"] for n in doc.get("natives", [])} if doc else set()
    taken_ids = {r["id"] for r in doc.get("resources", [])} if doc else set()
    taken_canonicals = {r["canonical"].lower() for r in doc.get("resources", [])} if doc else set()

    found = [c for c in registry.detect_resources(root) if c["path"] not in tracked]
    ids: dict[str, int] = {}
    canonicals: dict[str, int] = {}
    for c in found:
        if c["reason"] is None:
            ids[c["id"]] = ids.get(c["id"], 0) + 1
            # Lowercased: on a case-insensitive file system these would be one path.
            canonicals[c["canonical"].lower()] = canonicals.get(c["canonical"].lower(), 0) + 1

    adoptable, left = [], []
    for c in found:
        reason = c["reason"]
        if reason is None:
            backup = f"{core.CTX_DIRNAME}/{core.SOURCES_DIRNAME}/{c['path']}"
            if (ids[c["id"]] > 1 or canonicals[c["canonical"].lower()] > 1
                    or c["id"] in taken_ids or c["canonical"].lower() in taken_canonicals):
                reason = "name_collision"
            elif not all(_no_symlinked_parent(root, p) for p in (c["path"], c["canonical"], backup)):
                reason = "unsafe_path"
            elif os.path.lexists(root / c["canonical"]):
                reason = "canonical_exists"
            elif os.path.lexists(root / backup):
                reason = "backup_exists"
        if reason is None:
            adoptable.append(c)
        else:
            left.append({"path": c["path"], "type": c["type"], "reason": reason})
    return adoptable, left


def manifest_entries(cand: dict) -> tuple[dict, dict]:
    """The [[resources]] and [[natives]] entries for an adopted candidate."""
    resource = {"id": cand["id"], "type": cand["type"], "canonical": cand["canonical"]}
    native = {"resource": cand["id"], "path": cand["path"], "mode": "link", "tools": list(cand["tools"]), "backup": True}
    return resource, native


def backup(project_dir: Path, native: str, dest_root: Path) -> str:
    """Copy a native file or directory to dest_root's .ctx/sources/, preserving modes."""
    src = Path(project_dir) / native
    dst = core.sources_dir(dest_root) / native
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.is_dir():
        shutil.copytree(src, dst, symlinks=True)
    else:
        shutil.copy2(src, dst)
    return f"{core.CTX_DIRNAME}/{core.SOURCES_DIRNAME}/{native}"


def link_state(project_dir: Path, native: str, canonical: str) -> str:
    """healthy, missing (link absent), pending (resource not moved yet), or a conflict reason."""
    root = Path(project_dir).resolve()
    if not (_no_symlinked_parent(root, native) and _no_symlinked_parent(root, canonical)):
        return "unsafe_path"
    nat, can = root / native, root / canonical
    if can.is_symlink():
        return "unsafe_path"
    has_canonical = os.path.lexists(can)
    if nat.is_symlink():
        if os.readlink(nat) != link_target(native, canonical):
            return "link_retargeted"
        return "healthy" if has_canonical else "canonical_missing"
    if os.path.lexists(nat):
        return "native_replaced" if has_canonical else "pending"
    return "missing" if has_canonical else "canonical_missing"


def publish_link(project_dir: Path, native: str, canonical: str) -> tuple[str, str | None]:
    """Bring one linked native to healthy. Returns (healthy|repaired, None) or (conflict, reason).

    Nothing is ever deleted or overwritten: a pending resource is moved (not copied),
    and any state but missing or pending is reported as a conflict.
    """
    state = link_state(project_dir, native, canonical)
    if state == "healthy":
        return "healthy", None
    if state not in ("missing", "pending"):
        return "conflict", state
    root = Path(project_dir).resolve()
    nat, can = root / native, root / canonical
    if state == "pending":
        can.parent.mkdir(parents=True, exist_ok=True)
        os.rename(nat, can)
    nat.parent.mkdir(parents=True, exist_ok=True)
    _symlink(link_target(native, canonical), nat)
    return "repaired", None
