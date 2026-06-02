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

The command takes the path to the instruction file to track.

## Then report to the user

Present the result printed by the command. If the file was successfully added, tell the user that the original content has been backed up, incorporated into `.ctx/SUPERCTX.md`, and the file replaced with a generated shim. `.ctx/SUPERCTX.md` is now the canonical project context — agents read it through their shims automatically.
