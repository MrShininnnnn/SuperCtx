from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import core, registry


class AddError(Exception):
    """Raised for command-level errors (missing files, invalid paths)."""
    pass


@dataclass(frozen=True)
class AddResult:
    path: str
    status: str    # "added" | "already_tracked"
    tools: list[str]
    message: str


def run(project_dir: Path, input_path: str) -> AddResult:
    project_dir = Path(project_dir).resolve()
    manifest_path = core.manifest_path(project_dir)
    
    if not manifest_path.exists():
        raise AddError("SuperCtx is not initialized in this project. Run 'superctx init' first.")
        
    file_path = Path(input_path)
    resolved_file_path = (project_dir / file_path).resolve()
    
    if not resolved_file_path.exists():
        raise AddError(f"File does not exist: {input_path}")
        
    if not resolved_file_path.is_file():
        raise AddError(f"Directories are not supported by add yet: {input_path}")
        
    try:
        rel_path = resolved_file_path.relative_to(project_dir)
    except ValueError:
        raise AddError(f"Path must be inside the project root: {input_path}")
        
    rel_path_str = rel_path.as_posix()
    
    if rel_path.parts and rel_path.parts[0] == core.CTX_DIRNAME:
        raise AddError("Cannot add files inside the .ctx directory.")
        
    manifest = core.load_manifest(project_dir)
    tracked_files = manifest.setdefault("files", [])
    
    for entry in tracked_files:
        if entry["path"] == rel_path_str:
            return AddResult(
                path=rel_path_str,
                status="already_tracked",
                tools=entry.get("tools", []),
                message=f"{rel_path_str} is already tracked."
            )
            
    conv = registry.lookup_known_convention(rel_path_str)
    if conv:
        tools = conv.get("tools", [])
    else:
        tools = []
        
    tracked_files.append({
        "path": rel_path_str,
        "tools": tools
    })
    
    manifest_path.write_text(core.dump_manifest(manifest), encoding="utf-8")
    
    return AddResult(
        path=rel_path_str,
        status="added",
        tools=tools,
        message=(
            f"Added {rel_path_str} as a local custom instruction file.\n\n"
            f"Next step:\n"
            f"  Run /superctx:sync to centralize it."
        )
    )
