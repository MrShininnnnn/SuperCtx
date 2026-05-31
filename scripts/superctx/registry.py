"""Load the cited conventions registry and match it against a project's files.

Identity is by PATH convention (never inferred from file contents). See conventions.toml.
"""

from __future__ import annotations

import tomllib
from pathlib import Path


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
