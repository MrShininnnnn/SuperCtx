"""Load the cited conventions registry and match it against a project's files.

Identity is by PATH convention (never inferred from file contents). See conventions.toml.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from . import core, toml_compat


@dataclass(frozen=True)
class DiscoveryCandidate:
    path: str
    label: str
    note: str


SUPPORTED_FOLDER_CANDIDATES = [
    DiscoveryCandidate(
        path=".agents/rules",
        label="Antigravity workspace rules",
        note="folder sync not enabled yet",
    ),
    DiscoveryCandidate(
        path="agents/skills",
        label="Antigravity skills",
        note="folder sync not enabled yet",
    ),
]

LEGACY_OR_UNCERTAIN_CANDIDATES = [
    DiscoveryCandidate(
        path=".agent/rules",
        label="Legacy Antigravity workspace rules",
        note="folder sync not enabled yet",
    ),
]




def registry_path() -> Path:
    return Path(__file__).with_name("conventions.toml")


def load_conventions(path: Path | None = None) -> list[dict]:
    with (Path(path) if path else registry_path()).open("rb") as fh:
        return toml_compat.load(fh).get("convention", [])


def instruction_conventions(convs: list[dict] | None = None) -> list[dict]:
    """In-scope-for-v0.1 entries: single instruction files (not folders)."""
    convs = load_conventions() if convs is None else convs
    return [c for c in convs if c.get("kind") == "instruction-file"]


def detect(project_dir: Path, convs: list[dict] | None = None) -> list[dict]:
    """Known instruction-file conventions whose path exists in the project."""
    project_dir = Path(project_dir)
    return [
        c for c in instruction_conventions(convs)
        if (project_dir / c["path"]).is_file()
    ]


def detect_all(project_dir: Path) -> dict[str, list[dict]]:
    project_dir = Path(project_dir)
    res = {
        "verified_instruction_file": [],
        "supported_folder_candidate": [],
        "legacy_or_uncertain_folder_candidate": [],
        "unverified_local_candidate": [],
    }

    # 1. Verified instruction files from conventions.toml
    for c in detect(project_dir):
        res["verified_instruction_file"].append({
            "path": c["path"],
            "tools": c.get("tools", []),
        })

    # 2. Supported folder candidates
    for cand in SUPPORTED_FOLDER_CANDIDATES:
        p = project_dir / cand.path
        if p.is_dir():
            res["supported_folder_candidate"].append({
                "path": cand.path,
                "label": cand.label,
                "note": cand.note,
            })

    # 3. Legacy or uncertain folder candidates
    for cand in LEGACY_OR_UNCERTAIN_CANDIDATES:
        p = project_dir / cand.path
        if p.is_dir():
            res["legacy_or_uncertain_folder_candidate"].append({
                "path": cand.path,
                "label": cand.label,
                "note": cand.note,
            })

    # 4. Unverified local candidates (checked conditionally)
    # Check .agy/ANTIGRAVITY.md first, else .agy/
    agy_md = project_dir / ".agy/ANTIGRAVITY.md"
    agy_dir = project_dir / ".agy"
    if agy_md.is_file():
        res["unverified_local_candidate"].append({
            "path": ".agy/ANTIGRAVITY.md",
            "label": "local convention candidate",
            "note": "not verified official support",
        })
    elif agy_dir.is_dir():
        res["unverified_local_candidate"].append({
            "path": ".agy",
            "label": "local convention candidate",
            "note": "not verified official support",
        })

    # Check .antigravity/ANTIGRAVITY.md first, else .antigravity/
    anti_md = project_dir / ".antigravity/ANTIGRAVITY.md"
    anti_dir = project_dir / ".antigravity"
    if anti_md.is_file():
        res["unverified_local_candidate"].append({
            "path": ".antigravity/ANTIGRAVITY.md",
            "label": "local convention candidate",
            "note": "not verified official support",
        })
    elif anti_dir.is_dir():
        res["unverified_local_candidate"].append({
            "path": ".antigravity",
            "label": "local convention candidate",
            "note": "not verified official support",
        })

    return res


RESOURCE_KINDS = {"rules": "rule", "skills": "skill", "planning": "planning"}
# Kinds whose convention names one whole folder. They are offered as candidates and
# adopted only with /superctx:add, never by the one-step setup.
FOLDER_KINDS = {"planning"}


def resource_conventions(convs: list[dict] | None = None) -> list[dict]:
    """Rule and skill folder conventions (see conventions.toml)."""
    convs = load_conventions() if convs is None else convs
    return [c for c in convs if c.get("kind") in RESOURCE_KINDS]


def _resource_id(prefix: str, rel: str, suffixes: list[str]) -> str:
    stem = next((rel[: -len(s)] for s in suffixes if rel.endswith(s)), rel)
    return f"{prefix}-{_slug(stem)}"


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9._-]+", "-", text.lower()).strip("-.")


def folder_canonical(rel: str) -> str:
    """Where a connected folder lives under .ctx/: at the native depth when possible
    (docs/architecture -> .ctx/architecture), else one level deeper (notes -> .ctx/notes)."""
    parts = rel.split("/")
    return f"{core.CTX_DIRNAME}/" + ("/".join(parts[1:]) if len(parts) > 1 else parts[0].lstrip(".") or parts[0])


def _reserved_ctx_names(convs: list[dict]) -> set[str]:
    """Top-level .ctx/ entries SuperCtx owns or gives to a convention."""
    names = {core.HUB_NAME, core.V2_MANIFEST_NAME, core.MANIFEST_NAME, core.V1_BACKUP_NAME, ".gitignore",
             core.SOURCES_DIRNAME}
    return names | {c["canonical"].split("/")[1] for c in convs if c.get("canonical")}


def _overlaps_convention(rel: str, convs: list[dict], own: str | None) -> bool:
    """True if rel is, holds, or sits inside another convention's path."""
    for conv in convs:
        path = conv["path"].rstrip("/")
        if path == own:
            continue
        if conv["kind"] in RESOURCE_KINDS:  # resources there are managed one by one
            if rel == path or path.startswith(rel + "/") or rel.startswith(path + "/"):
                return True
        elif conv["kind"] == "folder":  # tool-owned: configuration, hooks, agents, plugins
            if rel == path or path.startswith(rel + "/") or rel.startswith(path + "/"):
                return True
        elif rel == path or path.startswith(rel + "/"):  # instruction files
            return True
    return False


def in_tool_folder(rel: str) -> bool:
    """True if a single file sits inside a tool-owned folder and is not a known instruction file."""
    if lookup_known_convention(rel):
        return False
    return any(conv["kind"] == "folder" and rel.startswith(conv["path"].rstrip("/") + "/")
               for conv in load_conventions())


def adopted_tool_config(project_dir: Path, pointers: list[str]) -> set[str]:
    """Pointer paths that are tool configuration: inside a tool-owned folder, or the target of
    a link there (versions before 0.2.2 adopted both with `add`)."""
    project_dir = Path(project_dir).resolve()
    found = {rel for rel in pointers if in_tool_folder(rel)}
    rest = set(pointers) - found
    for conv in load_conventions():
        if conv["kind"] != "folder" or not rest:
            continue
        for dirpath, dirnames, filenames in os.walk(project_dir / conv["path"]):
            for name in filenames:
                path = Path(dirpath) / name
                if not path.is_symlink() or lookup_known_convention(path.relative_to(project_dir).as_posix()):
                    continue
                try:
                    target = path.resolve().relative_to(project_dir).as_posix()
                except ValueError:
                    continue
                if target in rest:
                    found.add(target)
    return found


def folder_candidate(project_dir: Path, rel: str, type_: str, tools: list[str] | None = None,
                     convention: str | None = None) -> dict:
    """A whole folder as one resource (reference, or planning under a planning convention)."""
    convs = load_conventions()
    path = Path(project_dir) / rel
    canonical = folder_canonical(rel)
    if path.is_symlink():
        reason = "already_a_symlink"
    elif _overlaps_convention(rel, convs, convention):
        reason = "tool_folder"
    elif canonical.split("/")[1] in _reserved_ctx_names(convs) and convention is None:
        reason = "reserved_name"
    elif any(p.is_symlink() for p in path.rglob("*")):
        reason = "contains_symlink"
    else:
        reason = None
    return {"type": type_, "path": rel, "canonical": canonical, "id": f"{type_}-{_slug(rel)}",
            "tools": list(tools or []), "reason": reason, "explicit": True}


def detect_resources(project_dir: Path) -> list[dict]:
    """Rules and skills found under known folders, each with its planned canonical path.

    `reason` is None when the resource's form allows adoption, or explains why it
    stays in place. Whether it is already tracked, collides, or has an unsafe path
    is decided by the caller.
    """
    project_dir = Path(project_dir)
    found = []
    for conv in resource_conventions():
        type_ = RESOURCE_KINDS[conv["kind"]]
        base_rel = conv["path"].rstrip("/")
        base = project_dir / base_rel
        if not base.is_dir():
            continue
        if conv["kind"] in FOLDER_KINDS:
            cand = folder_candidate(project_dir, base_rel, type_, conv.get("tools", []), convention=base_rel)
            if cand["reason"] is None and conv.get("publish") != "link":
                cand["reason"] = "not_verified"
            found.append(cand)
            continue
        suffixes = conv.get("suffixes", [])
        if conv["kind"] == "rules":
            # os.walk does not descend into symlinked directories; symlinked files
            # are listed and reported as already_a_symlink.
            items = []
            for dirpath, dirnames, filenames in os.walk(base):
                dirnames.sort()
                items += [Path(dirpath) / n for n in sorted(filenames) if n.endswith(tuple(suffixes))]
        else:
            items = sorted(p for p in base.iterdir() if p.is_dir())
        for item in items:
            inner = item.relative_to(base).as_posix()
            if item.is_symlink():
                reason = "already_a_symlink"
            elif type_ == "skill" and not (item / "SKILL.md").is_file():
                reason = "no_skill_md"
            elif type_ == "skill" and any(p.is_symlink() for p in item.rglob("*")):
                reason = "contains_symlink"
            elif conv.get("publish") != "link":
                reason = "not_verified"
            else:
                reason = None
            found.append({
                "type": type_,
                "path": f"{base_rel}/{inner}",
                "canonical": f"{conv['canonical'].rstrip('/')}/{inner}",
                "id": _resource_id(conv.get("id_prefix", type_), inner, suffixes),
                "tools": conv.get("tools", []),
                "reason": reason,
            })
    return found


def lookup_known_convention(path_str: str) -> dict | None:
    """Find a known instruction-file convention by its relative path."""
    normalized = path_str.strip().replace("\\", "/").lstrip("/")
    for convention in instruction_conventions():
        if convention["path"] == normalized:
            return convention
    return None
