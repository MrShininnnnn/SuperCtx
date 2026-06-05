---
name: superctx:init
description: Use when setting up SuperCtx in a project for the first time, or when the user asks to create the .ctx hub, connect existing instruction files, or "initialize superctx". Also use when no .ctx/ directory exists yet but the user wants cross-tool context management.
---

# SuperCtx Init

Scaffold the canonical `.ctx/` hub for this project. SuperCtx imports existing per-tool
instruction files (`CLAUDE.md`, `AGENTS.md`, `GEMINI.md`, ...), stores inactive backups,
and replaces those files with generated shims pointing to the hub.

## Before Running

Never run this command without first obtaining the user's explicit natural-language consent.

Use this consent prompt before setup:
> Using SuperCtx, I can set up one shared context hub for this repo.
>
> This will:
> - create `.ctx/SUPERCTX.md`
> - back up the original instruction files under `.ctx/sources/`
> - replace the live instruction files with generated shims pointing to the hub
>
> Proceed?

Do not create `.ctx/` or any other files before receiving the user's confirmation.

After consent, announce:
> Using SuperCtx to set up the shared project context for this repo.

## Run

If the repository is in a needs-repair state, run `/superctx:status` and `/superctx:sync` instead of `/superctx:init`. If the repository is in a legacy state, running `/superctx:init` directly may fail because existing SuperCtx state is already present. Treat this as migration/recovery work: preserve existing instruction contents and use explicit user-approved migration steps; do not delete `.ctx` or overwrite files ad hoc.

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
