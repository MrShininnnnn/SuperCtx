---
name: superctx:status
description: Use when the user wants a SuperCtx status check, asks about hub-and-shim health, or needs to verify that the hub exists and registered shims/backups are healthy.
---

# SuperCtx Status

Report structural integrity and health of the hub-and-shim v0.2 model. Read-only — never writes.

## Before Running

Announce that you are using SuperCtx:
> Using SuperCtx to check context health.

## Run

```bash
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m superctx status
```

## Then present the result

Present the output from the command. On the healthy path, confirm that all context links are healthy and stop there. Only surface detail when the command reports a problem:

- Broken or missing shims: tell the user to run `/superctx:sync` to repair them.
- Untracked candidates: suggest `/superctx:add <path>` to connect them.
- Hub missing or empty: tell the user to run `/superctx:init` or add content to `.ctx/SUPERCTX.md`.
- Missing backups: note that original content may not be recoverable.

Do not describe hub/shim/backup mechanics unless the user asks.
