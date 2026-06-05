import pytest
from superctx.guard import classify_write_path

def test_classify_write_path():
    tracked = {"CLAUDE.md", "AGENTS.md"}
    # 1. Ignored paths
    assert classify_write_path(".git/config", tracked) == "ignored_hidden_path"
    assert classify_write_path("src/.venv/bin/pytest", tracked) == "ignored_hidden_path"
    # 2. Tracked shim
    assert classify_write_path("CLAUDE.md", tracked) == "known_generated_shim"
    # 3. Known instruction file (untracked)
    assert classify_write_path("GEMINI.md", tracked) == "known_instruction_file"
    # 4. Agent folder candidates
    assert classify_write_path(".claude/settings.json", tracked) == "known_agent_folder_file"
    # 5. Unknown hidden
    assert classify_write_path(".other-tool/config", tracked) == "unknown_hidden_path"
    # 6. Normal file
    assert classify_write_path("src/main.py", tracked) == "normal_file"
