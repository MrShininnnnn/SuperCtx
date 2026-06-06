from __future__ import annotations

import os
import sys
import json
import argparse
from pathlib import Path
from .status import detect_repo_state
from . import core

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

def parse_input(stdin_str: str) -> dict:
    try:
        return json.loads(stdin_str)
    except Exception:
        return {}

def extract_paths(tool_input: dict | list) -> list[str]:
    paths = []
    if isinstance(tool_input, dict):
        for key in ["file_path", "filePath", "path", "TargetFile", "target_file"]:
            if key in tool_input and isinstance(tool_input[key], str):
                paths.append(tool_input[key])
        for val in tool_input.values():
            if isinstance(val, (dict, list)):
                paths.extend(extract_paths(val))
    elif isinstance(tool_input, list):
        for item in tool_input:
            if isinstance(item, (dict, list)):
                paths.extend(extract_paths(item))
            elif isinstance(item, str):
                paths.append(item)
    return paths

def handle_pre_tool_use(data: dict) -> tuple[int, str]:
    cwd_str = data.get("cwd") or os.getcwd()
    project_dir = Path(cwd_str).resolve()

    tool_input = data.get("tool_input", {})
    target_paths = extract_paths(tool_input)
    if not target_paths:
        return 0, ""

    tracked_paths = set()
    try:
        manifest = core.load_manifest(project_dir)
        for entry in manifest.get("files", []):
            tracked_paths.add(entry["path"].replace("\\", "/"))
    except Exception:
        pass

    try:
        state = detect_repo_state(project_dir)
    except Exception:
        state = {"state": "not_candidate", "candidates": []}

    for p in target_paths:
        p_path = Path(p).resolve()
        try:
            rel_path = p_path.relative_to(project_dir)
            rel_str = rel_path.as_posix()
        except ValueError:
            continue

        classification = classify_write_path(rel_str, tracked_paths)
        if classification in ("ignored_hidden_path", "unknown_hidden_path", "normal_file", "known_agent_folder_file"):
            continue

        repo_state = state.get("state", "not_candidate")

        if repo_state == "candidate_repo":
            if classification == "known_instruction_file":
                cands_str = "\n".join(f"- {c}" for c in state.get("candidates", []))
                msg = (
                    f"Using SuperCtx, I found existing agent instruction files in this repo:\n"
                    f"{cands_str}\n\n"
                    f"I can set up one shared context hub so this instruction stays consistent across connected agents.\n\n"
                    f"This will:\n"
                    f"- create `.ctx/SUPERCTX.md`\n"
                    f"- back up the original instruction files under `.ctx/sources/`\n"
                    f"- replace the live instruction files with generated shims pointing to the hub\n\n"
                    f"Proceed?"
                )
                return 2, msg

        elif repo_state == "managed_healthy":
            if classification == "known_generated_shim":
                msg = (
                    f"Using SuperCtx to update the shared project context across connected agents.\n\n"
                    f"`{rel_str}` is a generated SuperCtx shim, so I will update `.ctx/SUPERCTX.md` instead."
                )
                return 2, msg
            elif classification == "known_instruction_file":
                msg = (
                    f"Using SuperCtx, I found that `{rel_str}` is a standard agent instruction file not yet tracked by SuperCtx.\n\n"
                    f"I can connect this file to the shared context hub `.ctx/SUPERCTX.md` and replace it with a shim.\n\n"
                    f"Proceed?"
                )
                return 2, msg

        elif repo_state == "managed_needs_repair":
            if classification in ("known_generated_shim", "known_instruction_file"):
                msg = (
                    "Using SuperCtx, I detected that the generated shims are broken or missing and need repair.\n\n"
                    "I can repair the shims to restore alignment with the shared context hub.\n\n"
                    "Proceed with repair?"
                )
                return 2, msg

        elif repo_state == "managed_legacy":
            if classification in ("known_generated_shim", "known_instruction_file"):
                msg = (
                    "Using SuperCtx, I detected an older legacy setup that needs to be migrated to the current hub-and-shim model.\n\n"
                    "I can migrate the setup while preserving your existing instruction contents.\n\n"
                    "Proceed with migration?"
                )
                return 2, msg

        elif repo_state == "not_candidate":
            if classification == "known_instruction_file":
                msg = (
                    f"Using SuperCtx, I noticed you are creating an agent instruction file: `{rel_str}`.\n\n"
                    f"I can set up one shared context hub to keep Claude, Codex, Gemini, and other agent instructions aligned.\n\n"
                    f"This will:\n"
                    f"- create `.ctx/SUPERCTX.md`\n"
                    f"- back up the original instruction files under `.ctx/sources/`\n"
                    f"- replace the live instruction files with generated shims pointing to the hub\n\n"
                    f"Proceed with SuperCtx setup instead?"
                )
                return 2, msg

    return 0, ""

def handle_user_prompt_expansion(data: dict) -> tuple[int, str]:
    prompt_text = ""
    for key in ["user_prompt", "prompt", "command", "userPrompt"]:
        if key in data and isinstance(data[key], str):
            prompt_text = data[key].strip()
            break

    if prompt_text.startswith("/init"):
        msg = (
            "Using SuperCtx, I noticed `/init` is about to create or update Claude instructions.\n\n"
            "This repo can use SuperCtx to keep Claude, Codex, Gemini, and other agent instructions aligned through one shared context hub.\n\n"
            "This will:\n"
            "- create `.ctx/SUPERCTX.md`\n"
            "- back up the original instruction files under `.ctx/sources/`\n"
            "- replace the live instruction files with generated shims pointing to the hub\n\n"
            "Proceed with SuperCtx setup instead?"
        )
        return 2, msg

    return 0, ""

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--event", required=True, choices=["PreToolUse", "UserPromptExpansion"])
    args = parser.parse_args()

    stdin_data = sys.stdin.read()
    data = parse_input(stdin_data)

    if args.event == "PreToolUse":
        code, msg = handle_pre_tool_use(data)
    else:
        code, msg = handle_user_prompt_expansion(data)

    if code == 2:
        sys.stderr.write(msg + "\n")
        sys.exit(2)
    else:
        sys.exit(0)

if __name__ == "__main__":
    main()
