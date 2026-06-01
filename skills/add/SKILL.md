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
