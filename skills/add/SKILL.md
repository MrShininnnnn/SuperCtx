---
name: superctx:add
description: Use when the user wants to start tracking a local custom instruction file (like .agy/ANTIGRAVITY.md or .github/copilot-instructions.md) in SuperCtx. Requires a path argument.
---

# SuperCtx Add

Add a local candidate file to the SuperCtx manifest to begin tracking it.

## Before Running

Announce that you are using SuperCtx (replace `<path>` with the actual file path argument):
> Using SuperCtx to connect <path> as a local context file.

## Run

```bash
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m superctx add "$ARGUMENTS"
```

The command takes the path to the instruction file to track.

## Then report to the user

Present the result printed by the command. On the healthy path, keep the report concise: confirm the file is now connected and that `.ctx/SUPERCTX.md` is the canonical context. Only surface backup or shim details if the command reports a warning or error.
