---
name: superctx:init
description: Use when setting up SuperCtx in a project for the first time, or when the user asks to create the .ctx hub, connect existing instruction files, or "initialize superctx". Also use when no .ctx/ directory exists yet but the user wants cross-tool context management.
---

# SuperCtx Init

Scaffold the canonical `.ctx/` hub for this project. SuperCtx imports existing per-tool
instruction files (`CLAUDE.md`, `AGENTS.md`, `GEMINI.md`, ...), stores inactive backups,
and replaces those files with generated shims pointing to the hub.

## Before Running

Announce that you are using SuperCtx:
> Using SuperCtx to set up the shared project context for this repo.

## Run

```bash
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m superctx init
```

The command operates on the current working directory. It is idempotent — if `.ctx/` already
exists it makes no changes.

## Then report to the user

Present the output from the command. On the healthy path, keep the report concise:

- Which files were connected (from the command output).
- `.ctx/SUPERCTX.md` is now the canonical project context. Use `/superctx:add <path>` to connect additional instruction files.

Only surface backup or shim details if the command reports warnings or failures.
