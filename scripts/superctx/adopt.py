"""Linked resources: rules and skills that live under .ctx/ with a symlink at their native path.

Adoption backs up the native resource, moves it to its canonical path, and leaves a
relative symlink behind. Every step can be repeated, so an interrupted adoption is
finished by the next sync. See architecture/v2-manifest-and-ownership.md.
"""

from __future__ import annotations

import os
import re
import shutil
import stat
from pathlib import Path
from urllib.parse import unquote

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


# Where a rule can name another file. A destination is either <...> (may contain spaces)
# or a run without spaces in which parentheses are balanced one level deep.
_DEST = r"(?:<([^<>\n]*)>|((?:[^\s()<]|\([^\s()]*\))+))"
_REFERENCES = [
    re.compile(r"\]\(\s*" + _DEST),                         # [text](dest), ![alt](dest)
    re.compile(r"^ {0,3}\[[^\]\n]+\]:[ \t]*" + _DEST, re.M),  # [label]: dest
    re.compile(r"""\b(?:href|src)\s*=\s*(?:"([^"]*)"|'([^']*)')"""),  # HTML
    re.compile(r"(?:^|\s)@([^\s`]+)"),  # @path imports, resolved relative to the file
]
_ESCAPED = re.compile(r"\\([!-/:-@\[-`{-~])")


def _destinations(text: str) -> set[str]:
    """Every file path a rule may refer to, in each spelling a reader could resolve."""
    found = set()
    for pattern in _REFERENCES:
        for match in pattern.finditer(text):
            dest = next(g for g in match.groups() if g is not None).split("#", 1)[0]
            unescaped = _ESCAPED.sub(r"\1", dest)
            found |= {dest, unescaped, unquote(unescaped)}
    found.discard("")  # a link to a heading in the rule itself
    return found


def breaks_reference(project_dir: Path, native: str, canonical: str) -> bool:
    """True if a relative reference in the rule reaches an existing file from the native
    path but would reach a different path once the rule is read from its canonical path.

    References that leave both folders (like ../../docs/guide.md) resolve the same from
    either path because canonical paths keep the native depth; references to siblings in
    the rules folder do not.
    """
    root = Path(project_dir)
    try:
        text = (root / native).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return True
    native_dir, canonical_dir = os.path.dirname(native), os.path.dirname(canonical)
    for ref in _destinations(text):
        from_native = os.path.normpath(os.path.join(native_dir, ref))
        if (os.path.normpath(os.path.join(canonical_dir, ref)) != from_native
                and os.path.lexists(root / from_native)):
            return True
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
            elif c["type"] == "rule" and breaks_reference(root, c["path"], c["canonical"]):
                reason = "breaks_reference"
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
    native = {"resource": cand["id"], "path": cand["path"], "mode": "link", "tools": list(cand["tools"]),
              "backup": True, "published": False}  # until manifest.mark_published
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


def _tree(path: Path) -> dict | None:
    """A file or folder as {relative path: (kind, executable bits, bytes or link target)}."""
    def entry(p: Path) -> tuple:
        if p.is_symlink():
            return ("link", os.readlink(p))
        if p.is_dir():
            return ("dir",)
        return ("file", stat.S_IMODE(os.lstat(p).st_mode) & 0o111, p.read_bytes())

    if not os.path.lexists(path):
        return None
    if path.is_symlink() or not path.is_dir():
        return {".": entry(path)}
    tree = {".": ("dir",)}

    def fail(error: OSError) -> None:
        # By default os.walk skips a directory it cannot read, which would make an
        # unreadable edit look identical to the backup. Fail the comparison instead.
        raise error

    for dirpath, dirnames, filenames in os.walk(path, onerror=fail):
        for name in dirnames + filenames:
            item = Path(dirpath) / name
            tree[item.relative_to(path).as_posix()] = entry(item)
    return tree


def matches_backup(project_dir: Path, native: str) -> bool:
    """True only if the native resource is identical to its backup: same paths, bytes,
    and executable bits. A missing backup or a failed comparison is not a match."""
    root = Path(project_dir).resolve()
    try:
        backup = _tree(core.sources_dir(root) / native)
        return backup is not None and _tree(root / native) == backup
    except OSError:
        return False


def link_state(project_dir: Path, native: str, canonical: str, published: bool = True) -> str:
    """healthy, missing (link absent), pending (resource not moved yet), or a conflict reason.

    pending is only possible before the native's first publication is recorded, and only
    while the native is still identical to the backup setup took; anything changed since
    is native_edited. After publication, a real file or folder at the native path with
    no canonical copy is someone else's content, never a resource to adopt, so it is
    canonical_missing.
    """
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
        if has_canonical:
            return "native_replaced"
        if published:
            return "canonical_missing"
        return "pending" if matches_backup(root, native) else "native_edited"
    return "missing" if has_canonical else "canonical_missing"


def publish_link(project_dir: Path, native: str, canonical: str, published: bool = True) -> tuple[str, str | None]:
    """Bring one linked native to healthy. Returns (healthy|repaired, None) or (conflict, reason).

    Nothing is ever deleted or overwritten: a pending resource is moved (not copied),
    and any state but missing or pending is reported as a conflict.
    """
    state = link_state(project_dir, native, canonical, published)
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
