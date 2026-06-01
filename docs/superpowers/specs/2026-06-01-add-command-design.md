# Design Specification: Local Agent Candidate Add Command

This specification outlines the design and implementation for `superctx add` and `/superctx:add`, enabling users to easily track unverified local instruction files and standard conventions without manually editing `.ctx/manifest.toml`.

## Goal

Add a user-friendly CLI subcommand (`superctx add <path>`) and a Claude Code plugin skill (`/superctx:add <path>`) to add candidate files to the SuperCtx manifest.

## Proposed Architecture

```
scripts/superctx/
  __main__.py     # CLI routing and error output formatting
  add.py          # Validation logic, convention checks, manifest I/O
  registry.py     # Shared registry lookup helper
```

### 1. Conventions Registry Lookup (`registry.py`)

A new function `lookup_known_convention(path_str: str) -> dict | None` is added to check whether a path corresponds to a standard convention defined in `conventions.toml`.

* If a matching convention is found, we import the convention's `tools` array.
* If no convention matches, we assign `tools = []` (empty array).

### 2. Validation and Manifest Mutation (`add.py`)

The logic for adding a file is encapsulated inside `scripts/superctx/add.py`:
* **Validation Rules**:
  * The `.ctx/manifest.toml` file must already exist in the project (meaning `superctx init` has run).
  * The file path argument must exist.
  * The path must point to a file, not a directory.
  * The file must reside inside the project root directory.
  * The file must not be inside the `.ctx` directory (including `.ctx/sources/`).
* **Idempotency**:
  * If the path is already listed under `[[files]]` in `.ctx/manifest.toml`, the command returns a status indicating it is already tracked, rather than appending a duplicate entry.
* **Manifest Persistence**:
  * Modifies the list of tracked files and saves using `core.dump_manifest`.

### 3. CLI Subcommand and Formatting (`__main__.py`)

* Registers `add` as a subcommand under `argparse`.
* Catches `AddError` custom exceptions and prints clean user-facing error messages to standard error, returning exit code `1`.
* Updates status and initialization help messages to instruct the user to run `/superctx:add <path>` or `superctx add <path>` when local candidates are detected, instead of asking them to edit the TOML file manually.

### 4. Claude Code Skill Command (`skills/add/SKILL.md`)

* Exposes the skill to Claude Code as `superctx:add`.
* Documents how Claude Code can invoke the command using `/superctx:add <path>`.

---

## Verification Plan

### Automated Tests
* Test 1: Add a local candidate file (e.g. `.agy/ANTIGRAVITY.md`) to the manifest, verifying that `tools = []` is written.
* Test 2: Verify `add` followed by `sync` properly centralizes the file.
* Test 3: Verify duplicate adds are idempotent.
* Test 4: Verify missing files are rejected with a clear error.
* Test 5: Verify directories are rejected with a clear error.
* Test 6: Verify paths outside the project root are rejected.
* Test 7: Verify paths inside `.ctx/` are rejected.
* Test 8: Verify adding a known convention (e.g. `.github/copilot-instructions.md`) imports its official tool metadata from `conventions.toml`.

### Manual Verification
* Run `claude plugin validate .` to ensure the new skill schema is valid.
* Run `python -m pytest tests/ -v` to verify all test cases pass.
