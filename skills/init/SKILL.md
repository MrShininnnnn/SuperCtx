---
name: init
description: Use when setting up SuperCtx in a project for the first time, or when the user asks to create the .ctx hub, start centralizing context, or "set up superctx". Also use when no .ctx/ directory exists yet but the user wants cross-tool context management.
---

# SuperCtx Init

Scaffold the canonical `.ctx/` hub for this project. The hub centralizes per-tool instruction
files (`CLAUDE.md`, `AGENTS.md`, `GEMINI.md`, ...) so they stop drifting apart.

## Run

```bash
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m superctx init
```

The command operates on the current working directory. It is idempotent — if `.ctx/` already
exists it makes no changes.

## Then report to the user

- Which tool instruction files were auto-detected (from the cited conventions registry) and added
  to `.ctx/manifest.toml`.
- That `.ctx/sources/` is gitignored (a local drift-detection cache) while `.ctx/manifest.toml`
  and `.ctx/SUPERCTX.md` are committed.
- Next step: run `/superctx:sync` to populate `.ctx/SUPERCTX.md`.

If nothing was detected, suggest the user add file paths to `.ctx/manifest.toml` manually.
