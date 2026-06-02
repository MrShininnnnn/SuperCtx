"""Shared, deterministic helpers: paths, content normalization, hashing, manifest I/O."""

from __future__ import annotations

import hashlib
import tomllib
from pathlib import Path

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


# --- content ----------------------------------------------------------------

def normalize(text: str) -> str:
    """Normalize newlines to \\n, strip trailing whitespace per line, ensure one trailing \\n.

    Keeps drift detection from firing on cosmetic whitespace/EOL differences.
    """
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    out = "\n".join(line.rstrip() for line in lines).rstrip("\n")
    return out + "\n" if out else ""


def content_hash(text: str) -> str:
    return hashlib.sha256(normalize(text).encode("utf-8")).hexdigest()


def read_text(path: Path) -> str:
    return Path(path).read_text(encoding="utf-8")


# --- manifest ---------------------------------------------------------------

def load_manifest(project_dir: Path) -> dict:
    with manifest_path(project_dir).open("rb") as fh:
        return tomllib.load(fh)


def _toml_str(value: str) -> str:
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'


def _toml_array(items) -> str:
    return "[" + ", ".join(_toml_str(item) for item in items) + "]"


def dump_manifest(data: dict) -> str:
    """Serialize the small SuperCtx manifest schema to TOML (stdlib has no TOML writer)."""
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
        if "note" in entry:
            lines.append(f'note = {_toml_str(entry["note"])}')
        lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"
