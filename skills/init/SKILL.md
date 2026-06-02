---
name: superctx:init
description: Use when setting up SuperCtx in a project for the first time, or when the user asks to create the .ctx hub, connect existing instruction files, or "initialize superctx". Also use when no .ctx/ directory exists yet but the user wants cross-tool context management.
---

# SuperCtx Init

Scaffold the canonical `.ctx/` hub for this project. SuperCtx imports existing per-tool
instruction files (`CLAUDE.md`, `AGENTS.md`, `GEMINI.md`, ...), stores inactive backups,
and replaces those files with generated shims pointing to the hub.

## Run

```bash
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m superctx init
```

The command operates on the current working directory. It is idempotent — if `.ctx/` already
exists it makes no changes.

## Then report to the user

- Which tool instruction files were auto-detected (from the cited conventions registry) and added
  to `.ctx/manifest.toml`.
- That `.ctx/sources/` is gitignored (inactive backup storage for original instruction files) while
  `.ctx/manifest.toml` and `.ctx/SUPERCTX.md` are committed.
- `.ctx/SUPERCTX.md` is now the canonical project context. Coding agents read it automatically through their shims. To update shared instructions, edit `.ctx/SUPERCTX.md` or use `/superctx:add <path>` to connect additional files.
