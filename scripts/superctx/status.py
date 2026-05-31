"""`superctx status` — read-only drift report comparing live tool files to their snapshots.

States per path:
  synced    — live file matches its .ctx/sources/ snapshot
  drifted   — live file differs from snapshot (or has never been synced)
  missing   — tracked in the manifest but the live file is gone
  untracked — a known instruction-file convention exists in the repo but isn't in the manifest
"""

from __future__ import annotations

from pathlib import Path
import os
import json

from . import core, registry


def resolve_version(module_path: Path | None = None) -> dict:
    if module_path is None:
        module_path = Path(__file__).resolve()
    else:
        module_path = Path(module_path).resolve()

    # 1. Primary: check env var
    env_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if env_root:
        root_path = Path(env_root).resolve()
        plugin_json = root_path / ".claude-plugin" / "plugin.json"
        if plugin_json.is_file():
            try:
                with open(plugin_json, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if "version" in data:
                        return {
                            "version": data["version"],
                            "plugin_root": str(root_path),
                            "version_source": "env"
                        }
            except Exception:
                pass

    # 2. Fallback: parent path walk
    curr = module_path
    while True:
        candidate = curr / ".claude-plugin" / "plugin.json"
        if candidate.is_file():
            try:
                with open(candidate, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if "version" in data:
                        return {
                            "version": data["version"],
                            "plugin_root": str(curr.resolve()),
                            "version_source": "parent"
                        }
            except Exception:
                pass
        if curr.parent == curr:
            break
        curr = curr.parent

    # 3. Final fallback: shared constant
    from . import __version__
    return {
        "version": __version__,
        "plugin_root": None,
        "version_source": "fallback"
    }


def sanitize_path(path: Path | str | None) -> str:
    if path is None:
        return "None"
    p = Path(path).resolve()
    try:
        home = Path.home().resolve()
        if p.is_relative_to(home):
            rel = p.relative_to(home)
            if str(rel) == ".":
                return "~"
            return f"~/{rel}"
    except Exception:
        pass
    return str(p)


def diagnostics(project_dir: Path, module_path: Path | None = None) -> dict:
    project_dir = Path(project_dir).resolve()
    res_version = resolve_version(module_path)

    conventions = registry.load_conventions()
    supported_paths = {c["path"] for c in conventions}

    claude_supported = ".claude/CLAUDE.md" in supported_paths
    codex_supported = ".codex/AGENTS.md" in supported_paths

    claude_present = (project_dir / ".claude/CLAUDE.md").is_file()
    codex_present = (project_dir / ".codex/AGENTS.md").is_file()

    stale_install = (claude_present and not claude_supported) or (codex_present and not codex_supported)

    return {
        "version": res_version["version"],
        "plugin_root": sanitize_path(res_version["plugin_root"]),
        "version_source": res_version["version_source"],
        "registry": sanitize_path(registry.registry_path()),
        "supports_claude_md": claude_supported,
        "supports_codex_agents": codex_supported,
        "project_has_claude_md": claude_present,
        "project_has_codex_agents": codex_present,
        "stale_install": stale_install
    }


def run(project_dir: Path) -> list[dict]:
    project_dir = Path(project_dir)
    manifest = core.load_manifest(project_dir)
    files = manifest.get("files", [])
    tracked = {entry["path"] for entry in files}
    results: list[dict] = []

    for entry in files:
        rel = entry["path"]
        live = project_dir / rel
        snapshot = core.sources_dir(project_dir) / rel
        if not live.is_file():
            state = "missing"
        elif not snapshot.is_file():
            state = "drifted"  # tracked but never centralized
        elif core.content_hash(core.read_text(live)) == core.content_hash(core.read_text(snapshot)):
            state = "synced"
        else:
            state = "drifted"
        results.append({"path": rel, "state": state})

    for conv in registry.detect(project_dir):
        if conv["path"] not in tracked:
            results.append({"path": conv["path"], "state": "untracked"})

    return results
