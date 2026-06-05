import os
from pathlib import Path

def classify_write_path(path_str: str, tracked_paths: set[str]) -> str:
    path_str = path_str.strip().replace("\\", "/").lstrip("/")
    parts = Path(path_str).parts
    
    ignored_folders = {".git", ".venv", ".cache", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".node_modules"}
    if any(part in ignored_folders for part in parts):
        return "ignored_hidden_path"
        
    if path_str in tracked_paths:
        return "known_generated_shim"
        
    known_instruction_files = {
        "CLAUDE.md",
        ".claude/CLAUDE.md",
        "AGENTS.md",
        ".codex/AGENTS.md",
        "GEMINI.md",
        ".github/copilot-instructions.md",
        ".agy/ANTIGRAVITY.md",
        ".antigravity/ANTIGRAVITY.md"
    }
    if path_str in known_instruction_files:
        return "known_instruction_file"
        
    known_agent_folders = (".claude/", ".codex/", ".cursor/", ".agy/", ".antigravity/", ".agents/", ".agent/")
    if path_str.startswith(known_agent_folders):
        return "known_agent_folder_file"
        
    is_hidden = False
    for part in parts:
        if part.startswith(".") and part not in (".", ".."):
            is_hidden = True
            break
    if is_hidden:
        return "unknown_hidden_path"
        
    return "normal_file"
