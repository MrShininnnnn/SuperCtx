# Local Agent Candidate Add Command Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement `superctx add <path>` and `/superctx:add <path>` to easily track local agent candidates and standard conventions without manually editing TOML manifest files.

**Architecture:** Encapsulate validation and manifest write logic inside a new module `scripts/superctx/add.py`. Extend `scripts/superctx/registry.py` with registry lookup helpers, and integrate the command into `scripts/superctx/__main__.py`. Finally, expose it as a Claude Code skill.

**Tech Stack:** Python 3.12, stdlib (`pathlib`, `tomllib`, `argparse`, `dataclasses`).

---

### Task 1: Add Registry Lookup Helper

**Files:**
* Modify: [registry.py](file:///Users/shining/Desktop/Github/ShiningLab/SuperCtx/scripts/superctx/registry.py)
* Modify: [tests/test_engine.py](file:///Users/shining/Desktop/Github/ShiningLab/SuperCtx/tests/test_engine.py)

- [ ] **Step 1: Write a unit test verifying registry lookup**
  
  Add to the bottom of [tests/test_engine.py](file:///Users/shining/Desktop/Github/ShiningLab/SuperCtx/tests/test_engine.py):
  ```python
  def test_lookup_known_convention():
      # Test known convention matching
      conv = registry.lookup_known_convention(".github/copilot-instructions.md")
      assert conv is not None
      assert conv["tools"] == ["GitHub Copilot"]
      
      # Test unmatched convention
      assert registry.lookup_known_convention(".agy/ANTIGRAVITY.md") is None
      assert registry.lookup_known_convention("nonexistent.md") is None
  ```

- [ ] **Step 2: Run tests to verify the test fails**
  
  Run: `.venv/bin/python -m pytest tests/test_engine.py -k "test_lookup_known_convention" -v`
  Expected: FAIL with `AttributeError: module 'superctx.registry' has no attribute 'lookup_known_convention'`

- [ ] **Step 3: Implement lookup_known_convention in registry.py**
  
  Add to the bottom of [registry.py](file:///Users/shining/Desktop/Github/ShiningLab/SuperCtx/scripts/superctx/registry.py):
  ```python
  def lookup_known_convention(path_str: str) -> dict | None:
      """Find a known instruction-file convention by its relative path."""
      normalized = path_str.strip().replace("\\", "/").lstrip("/")
      for convention in instruction_conventions():
          if convention["path"] == normalized:
              return convention
      return None
  ```

- [ ] **Step 4: Run tests to verify they pass**
  
  Run: `.venv/bin/python -m pytest tests/test_engine.py -k "test_lookup_known_convention" -v`
  Expected: PASS

- [ ] **Step 5: Commit**
  
  ```bash
  git add scripts/superctx/registry.py tests/test_engine.py
  git commit -m "feat: add lookup_known_convention helper in registry.py"
  ```

---

### Task 2: Implement Core Add logic in `add.py`

**Files:**
* Create: [add.py](file:///Users/shining/Desktop/Github/ShiningLab/SuperCtx/scripts/superctx/add.py)
* Modify: [tests/test_engine.py](file:///Users/shining/Desktop/Github/ShiningLab/SuperCtx/tests/test_engine.py)

- [ ] **Step 1: Write failing unit tests for the add command logic**
  
  Add to the bottom of [tests/test_engine.py](file:///Users/shining/Desktop/Github/ShiningLab/SuperCtx/tests/test_engine.py):
  ```python
  from superctx import add as add_cmd
  
  def test_add_validates_manifest_exists(tmp_path):
      import pytest
      # Without init, add should raise AddError
      with pytest.raises(add_cmd.AddError) as exc_info:
          add_cmd.run(tmp_path, "somefile.md")
      assert "SuperCtx is not initialized in this project" in str(exc_info.value)
  
  def test_add_validations_missing_and_directories(tmp_path):
      import pytest
      init_cmd.run(tmp_path)
      
      # Missing path validation
      with pytest.raises(add_cmd.AddError) as exc_info:
          add_cmd.run(tmp_path, "missing.md")
      assert "File does not exist" in str(exc_info.value)
      
      # Directory path validation
      folder_path = tmp_path / "folder"
      folder_path.mkdir()
      with pytest.raises(add_cmd.AddError) as exc_info:
          add_cmd.run(tmp_path, "folder")
      assert "Directories are not supported" in str(exc_info.value)
      
      # Outside project validation
      outside = tmp_path.parent / "outside.md"
      outside.write_text("x", encoding="utf-8")
      with pytest.raises(add_cmd.AddError) as exc_info:
          add_cmd.run(tmp_path, "../outside.md")
      assert "Path must be inside the project root" in str(exc_info.value)
      
      # Inside .ctx/ sources validation
      ctx_file = core.ctx_dir(tmp_path) / "sources" / "somefile.md"
      ctx_file.parent.mkdir(parents=True, exist_ok=True)
      ctx_file.write_text("x", encoding="utf-8")
      with pytest.raises(add_cmd.AddError) as exc_info:
          add_cmd.run(tmp_path, ".ctx/sources/somefile.md")
      assert "Cannot add files inside the .ctx directory" in str(exc_info.value)
  
  def test_add_local_candidate_and_convention(tmp_path):
      init_cmd.run(tmp_path)
      
      # Add unrecognized candidate (.agy/ANTIGRAVITY.md)
      agy_file = tmp_path / ".agy/ANTIGRAVITY.md"
      agy_file.parent.mkdir(parents=True, exist_ok=True)
      agy_file.write_text("agy\n", encoding="utf-8")
      
      res = add_cmd.run(tmp_path, ".agy/ANTIGRAVITY.md")
      assert res.status == "added"
      assert res.tools == []
      assert ".agy/ANTIGRAVITY.md" in res.message
      
      # Check manifest
      manifest = core.load_manifest(tmp_path)
      assert {"path": ".agy/ANTIGRAVITY.md", "tools": []} in manifest["files"]
      
      # Add known convention (.github/copilot-instructions.md)
      copilot_file = tmp_path / ".github/copilot-instructions.md"
      copilot_file.parent.mkdir(parents=True, exist_ok=True)
      copilot_file.write_text("copilot\n", encoding="utf-8")
      
      res_conv = add_cmd.run(tmp_path, ".github/copilot-instructions.md")
      assert res_conv.status == "added"
      assert res_conv.tools == ["GitHub Copilot"]
      
      manifest2 = core.load_manifest(tmp_path)
      assert {"path": ".github/copilot-instructions.md", "tools": ["GitHub Copilot"]} in manifest2["files"]
      
      # Duplicate add check (should be idempotent)
      res_dup = add_cmd.run(tmp_path, ".agy/ANTIGRAVITY.md")
      assert res_dup.status == "already_tracked"
      assert res_dup.tools == []
      assert "is already tracked" in res_dup.message
  ```

- [ ] **Step 2: Run tests to verify they fail**
  
  Run: `.venv/bin/python -m pytest tests/test_engine.py -k "test_add_" -v`
  Expected: FAIL with `ImportError: cannot import name 'add' from 'superctx'`

- [ ] **Step 3: Create scripts/superctx/add.py with clean engine validation logic**
  
  Create file [add.py](file:///Users/shining/Desktop/Github/ShiningLab/SuperCtx/scripts/superctx/add.py):
  ```python
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
      
      if ".ctx" in rel_path.parts:
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
  ```

- [ ] **Step 4: Run tests to verify they pass**
  
  Run: `.venv/bin/python -m pytest tests/test_engine.py -k "test_add_" -v`
  Expected: PASS

- [ ] **Step 5: Commit**
  
  ```bash
  git add scripts/superctx/add.py tests/test_engine.py
  git commit -m "feat: implement add command core logic in add.py"
  ```

---

### Task 3: Integrate `add` command in `__main__.py`

**Files:**
* Modify: [__main__.py](file:///Users/shining/Desktop/Github/ShiningLab/SuperCtx/scripts/superctx/__main__.py)

- [ ] **Step 1: Implement argparse parser and routing in \_\_main\_\_.py**
  
  In [__main__.py](file:///Users/shining/Desktop/Github/ShiningLab/SuperCtx/scripts/superctx/__main__.py), import `add as add_cmd`:
  ```python
  from . import add as add_cmd
  ```
  
  Add `_cmd_add` routing helper:
  ```python
  def _cmd_add(project_dir: Path, file_path: str) -> int:
      try:
          result = add_cmd.run(project_dir, file_path)
          print(result.message)
          return 0
      except add_cmd.AddError as e:
          print(f"Error: {e}", file=sys.stderr)
          return 1
  ```
  
  Add argparse `add` subcommand parser to `main()`:
  ```python
      # Add parser
      p_add = sub.add_parser("add")
      p_add.add_argument("path")
      p_add.add_argument("project_dir", nargs="?", default=".")
  ```
  
  Dispatch logic update in `main()`:
  ```python
      project_dir = Path(args.project_dir).resolve()
      if args.cmd == "add":
          return _cmd_add(project_dir, args.path)
          
      dispatch = {"init": _cmd_init, "sync": _cmd_sync, "status": _cmd_status}
  ```

- [ ] **Step 2: Run CLI manually to verify output**
  
  Run:
  ```bash
  python -m superctx add nonexistent.md
  ```
  Expected output:
  `Error: File does not exist: nonexistent.md` (to stderr), exit code 1.

- [ ] **Step 3: Run full pytest suite**
  
  Run: `.venv/bin/python -m pytest tests/ -v`
  Expected: All 22 tests pass.

- [ ] **Step 4: Commit**
  
  ```bash
  git add scripts/superctx/__main__.py
  git commit -m "feat: integrate add command routing in __main__.py"
  ```

---

### Task 4: Expose Claude Plugin Skill `/superctx:add`

**Files:**
* Create: `skills/add/SKILL.md`

- [ ] **Step 1: Create skills/add/SKILL.md**
  
  Create file `skills/add/SKILL.md`:
  ```markdown
  ---
  name: superctx:add
  description: Use when the user wants to start tracking a local custom instruction file (like .agy/ANTIGRAVITY.md or .github/copilot-instructions.md) in SuperCtx. Requires a path argument.
  ---
  
  # SuperCtx Add
  
  Add a local candidate file to the SuperCtx manifest to begin tracking it.
  
  ## Run
  
  ```bash
  PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m superctx add "$ARGUMENTS"
  ```
  
  The command takes the path to the instruction file to track. It updates `.ctx/manifest.toml`.
  
  ## Then report to the user
  
  Present the result printed by the command. If the file was successfully added, tell the user the next step is running `/superctx:sync` to aggregate it into `.ctx/SUPERCTX.md`.
  ```

- [ ] **Step 2: Validate the plugin structure**
  
  Run: `claude plugin validate .`
  Expected: `✔ Validation passed`

- [ ] **Step 3: Commit**
  
  ```bash
  git add skills/add/SKILL.md
  git commit -m "feat: add superctx:add Claude plugin skill"
  ```

---

### Task 5: Improve init and status command guidance messages

**Files:**
* Modify: [__main__.py](file:///Users/shining/Desktop/Github/ShiningLab/SuperCtx/scripts/superctx/__main__.py)
* Modify: [tests/test_mvp_snapshots.py](file:///Users/shining/Desktop/Github/ShiningLab/SuperCtx/tests/test_mvp_snapshots.py)

- [ ] **Step 1: Replace manual TOML editing hints with command guidance**
  
  In [__main__.py](file:///Users/shining/Desktop/Github/ShiningLab/SuperCtx/scripts/superctx/__main__.py):
  
  * For `init` (`_cmd_init`), if candidates are detected, print:
    ```text
    To track a candidate file, run:
      /superctx:add <path>
    
    or:
      superctx add <path>
    ```
    
  * For `status` (`_cmd_status`), if candidates are detected, print:
    ```text
    To track a candidate file, run:
      /superctx:add <path>
    ```

- [ ] **Step 2: Update snapshot tests if needed**
  
  Run: `.venv/bin/python -m pytest tests/ -v`
  If `test_mvp_snapshots.py` fails due to guidance text updates, adjust assertions in `tests/test_mvp_snapshots.py` to match the new output strings.

- [ ] **Step 3: Verify all tests pass**
  
  Run: `.venv/bin/python -m pytest tests/ -v`
  Expected: PASS

- [ ] **Step 4: Commit**
  
  ```bash
  git add scripts/superctx/__main__.py tests/test_mvp_snapshots.py
  git commit -m "ux: guide users to use add command rather than editing TOML manually"
  ```

---

### Task 6: Documentation and Verification

**Files:**
* Modify: [README.md](file:///Users/shining/Desktop/Github/ShiningLab/SuperCtx/README.md)

- [ ] **Step 1: Update README.md to document add command and plugin skill**
  
  In [README.md](file:///Users/shining/Desktop/Github/ShiningLab/SuperCtx/README.md), add a section about tracking local custom instruction files using `superctx add` and `/superctx:add`.

- [ ] **Step 2: Run final validation suite**
  
  Run: `.venv/bin/python -m pytest tests/ -v`
  Run: `claude plugin validate .`
  Expected: Both pass cleanly.

- [ ] **Step 3: Commit**
  
  ```bash
  git add README.md
  git commit -m "docs: document superctx add and /superctx:add in README.md"
  ```
