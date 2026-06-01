"""Load the cited conventions registry and match it against a project's files.

Identity is by PATH convention (never inferred from file contents). See conventions.toml.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path


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
    DiscoveryCandidate(
        path=".agents/skills",
        label="Antigravity skills candidate",
        note="folder sync not enabled yet",
    ),
    DiscoveryCandidate(
        path=".agents/hooks.json",
        label="Antigravity hooks configuration",
        note="not confirmed official support",
    ),
    DiscoveryCandidate(
        path=".agents/hooks",
        label="Antigravity hooks",
        note="folder sync not enabled yet",
    ),
]




def registry_path() -> Path:
    return Path(__file__).with_name("conventions.toml")


def load_conventions(path: Path | None = None) -> list[dict]:
    with (Path(path) if path else registry_path()).open("rb") as fh:
        return tomllib.load(fh).get("convention", [])


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
        is_match = p.is_file() if cand.path.endswith(".json") else p.is_dir()
        if is_match:
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
