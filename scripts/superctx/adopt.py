"""Linked resources: rules and skills that live under .ctx/ with a symlink at their native path.

Adoption backs up the native resource, moves it to its canonical path, and leaves a
relative symlink behind. Every step can be repeated, so an interrupted adoption is
finished by the next sync. See architecture/v2-manifest-and-ownership.md.
"""

from __future__ import annotations

import html
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


# Where a rule can name another file. Each kind has an anchor that marks a reference
# and a full pattern for its destination; an anchor the full pattern cannot account for
# is a reference whose destination is unclear. A Markdown destination is either <...>
# (may contain spaces) or a run without spaces in which parentheses are balanced one
# level deep. Each full pattern must reach where its destination ends, so a partial
# match never counts as parsed; an empty inline destination needs its closing ).
# A backslash escapes only ASCII punctuation; before anything else it is literal.
_DEST = r"(?:<([^<>\n]*)>|((?:[^\s()<\\]|\\[!-/:-@\[-`{-~]?|\([^\s()]*\))+))"
_REFERENCES = [
    # [text](dest), ![alt](dest), [text]()
    (re.compile(r"\]\("), re.compile(r"(?P<a>\]\()\s*(?:\)|" + _DEST + r"(?=\s|\)))")),
    # [label]: dest, with the destination on the same or the next line
    (re.compile(r"\]:"), re.compile(r"^ {0,3}\[[^\]]+(?P<a>\]:)[ \t]*(?:\n[ \t]*)?" + _DEST + r"(?=\s|$)", re.M)),
    # HTML attributes, quoted or not; attribute names are case-insensitive
    (re.compile(r"\b(?:href|src)\s*=", re.I),
     re.compile(r"""\b(?P<a>href|src)\s*=\s*(?:"[^"]*"|'[^']*'|[^\s"'=<>`]+(?=[\s>]|$))""", re.I)),
]

# Where a destination may start: after a link, a definition, an HTML attribute, an
# @path import (resolved relative to the file), or an autolink's <; and at every ../,
# whatever precedes it. A path that climbs out of a skill must, just before its last
# step out, be at the folder it is resolved from (the skill's root or the file's
# folder), so the candidate starting at that ../ reaches the same place however the
# path began: ./../x, dir/../../x, or an unresolvable "$(dirname "$0")/../x.
_STARTS = re.compile(r"""\]\(|\]:|\b(?:href|src)\s*=|(?:^|(?<=\s))@|<|(?=\.\./)""", re.I | re.M)
_END = re.compile(r"""[\s)>"'`<]""")
_SPACE = re.compile(r"\s*")
# The scan reads at most _WINDOW characters of a line from each start. A destination
# that may still be open where the window ends was not fully checked. What closes it
# depends on how it opened: <...> after a link or definition may contain spaces and
# closes at >; a quoted HTML value closes at its quote; an autolink closes at > or
# whitespace; anything else closes at the first unescaped whitespace.
_WINDOW = 512
_CLOSE_ANGLE, _CLOSE_AUTOLINK = re.compile(r">"), re.compile(r"[\s>]")
_CLOSE_QUOTE = {'"': re.compile('"'), "'": re.compile("'")}
_CLOSE_BARE = re.compile(r"(?<!\\)\s")
_ESCAPE = re.compile(r"\\(.)")
# CommonMark decodes in one pass: a backslash escapes ASCII punctuation (so `\&amp;`
# stays literal), and entities are replaced.
_COMMONMARK = re.compile(r"\\([!-/:-@\[-`{-~])|(&(?:#[0-9]{1,7}|#[xX][0-9a-fA-F]{1,6}|[A-Za-z][A-Za-z0-9]{0,31});)")


def _commonmark(text: str) -> str:
    return _COMMONMARK.sub(lambda m: m.group(1) if m.group(1) is not None else html.unescape(m.group(2)), text)


def _unclear(text: str) -> bool:
    """True if a recognized reference has no complete destination."""
    for anchor, pattern in _REFERENCES:
        parsed = {m.start("a") for m in pattern.finditer(text)}
        if any(a.start() not in parsed for a in anchor.finditer(text)):
            return True
    return False


def _candidates(text: str) -> tuple[set[str], bool]:
    """Every path a reference in the rule could name, whatever parser reads it, and
    whether the scan window cut off a destination before it could close.

    Parsers disagree on details (which characters a backslash escapes, where an
    autolink ends), so instead of one grammar this takes, after every place a
    destination may start, each prefix of the rest of that line that ends where a
    destination can end, in every spelling a reader could decode it to.
    """
    raws, cut_off = set(), False
    for start in _STARTS.finditer(text):
        # The destination may start right away, after whitespace (a definition's may
        # be on the next line), or after an opening < or quote.
        anchor, first = start.group(), _SPACE.match(text, start.end()).end()
        opener = text[first:first + 1]
        if anchor == "<":
            starts = {start.end(): _CLOSE_AUTOLINK}
        else:
            starts = {start.end(): _CLOSE_BARE, first: _CLOSE_BARE}
            if opener == "<" and anchor in ("](", "]:"):
                starts[first + 1] = _CLOSE_ANGLE
            elif opener in _CLOSE_QUOTE and anchor[0] in "hHsS":  # a quoted HTML attribute
                starts[first + 1] = _CLOSE_QUOTE[opener]
            elif opener in ("<", '"', "'"):
                starts[first + 1] = _CLOSE_BARE
        for pos, close in starts.items():
            newline = text.find("\n", pos, pos + _WINDOW + 1)
            line = text[pos:newline] if newline != -1 else text[pos:pos + _WINDOW + 1]
            if len(line) > _WINDOW:
                line = line[:_WINDOW]
                cut_off = cut_off or not close.search(line)
            prefixes = {line[:m.start()] for m in _END.finditer(line)} | {line}
            raws |= prefixes | {p.strip() for p in prefixes}  # some readers trim inside <...>
    found = set()
    for raw in raws:
        # As written; decoded exactly as CommonMark does; with entities decoded but
        # backslashes literal (HTML attributes); with every backslash escape removed
        # (`@team\ guide.md` imports).
        for spelling in {raw, _commonmark(raw), html.unescape(raw), _ESCAPE.sub(r"\1", raw)}:
            path = re.split(r"[?#]", spelling, maxsplit=1)[0]  # the URL's path component
            found |= {spelling, path, unquote(path)}
    found.discard("")  # a link to a heading in the rule itself, or an empty link
    return found, cut_off


def _files(path: Path) -> list[str]:
    """The resource's files relative to it ("" when the resource is a single file)."""
    if not path.is_dir():
        return [""]

    def fail(error: OSError) -> None:
        raise error

    return sorted(os.path.relpath(os.path.join(dirpath, name), path).replace(os.sep, "/")
                  for dirpath, _, names in os.walk(path, onerror=fail) for name in names)


def reference_problem(project_dir: Path, native: str, canonical: str) -> str | None:
    """Why moving a rule or skill could break a relative reference in it, or None.

    breaks_reference: something a file in the resource could name reaches an existing
    path from the native location but a different one after the move. A resource moves
    as a whole, so a reference into itself follows it, and one that leaves the tool's
    folder (like ../../docs/guide.md) resolves the same because canonical paths keep the
    native depth; a reference to a sibling (another rule or skill, or ../shared.md) does
    not. Each file's references are resolved from its own folder and, in a skill, also
    from the skill's root, where its scripts usually run.
    unclear_reference: a recognized Markdown reference has no complete destination, one
    was too long to check completely, or the resource could not be read, so it stays in
    place rather than risk breaking a reference.
    """
    root = Path(project_dir)
    is_dir = (root / native).is_dir()

    def inside(base: str, rel: str) -> str:
        return f"{base}/{rel}" if rel else base

    def moved(path: str) -> str:
        """Where a path inside the resource ends up after the move."""
        if path == native or path.startswith(native + "/"):
            return canonical + path[len(native):]
        return path

    unclear = False
    try:
        for rel in _files(root / native):
            data = (root / inside(native, rel)).read_bytes()
            if b"\0" in data:  # binary assets name no files
                continue
            text = data.decode("utf-8", errors="replace")
            candidates, cut_off = _candidates(text)
            bases = [(os.path.dirname(inside(native, rel)), os.path.dirname(inside(canonical, rel)))]
            if is_dir:
                bases.append((native, canonical))
            for ref in candidates:
                for native_base, canonical_base in bases:
                    from_native = os.path.normpath(os.path.join(native_base, ref))
                    if (os.path.normpath(os.path.join(canonical_base, ref)) != moved(from_native)
                            and os.path.lexists(root / from_native)):
                        return "breaks_reference"
            markdown = (rel or native).endswith((".md", ".mdc", ".markdown"))
            unclear = unclear or cut_off or (markdown and _unclear(text))
    except OSError:
        return "unclear_reference"
    return "unclear_reference" if unclear else None


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
            elif problem := reference_problem(root, c["path"], c["canonical"]):
                reason = problem
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
