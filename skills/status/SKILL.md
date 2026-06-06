---
name: superctx:status
description: Use when the user wants a SuperCtx status check, asks about hub-and-shim health, or needs to verify that the hub exists and registered shims/backups are healthy.
---

# SuperCtx Status

Report structural integrity and health of the current SuperCtx hub-and-shim model. Read-only — never writes.

## Before Running

Announce that you are using SuperCtx:
> Using SuperCtx to check context health.

## Run

```bash
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m superctx status
```

## Then present the result

Present the output from the command. On the healthy path, confirm that all context links are healthy and stop there.
When status finds an action that can be safely handled by SuperCtx, do not simply tell the user to run another command. Offer to do it after obtaining their explicit consent, then run the appropriate operation internally:
- Broken or missing shims: explain the issue, offer to repair them, and run `/superctx:sync` after consent.
- Untracked candidates: explain the issue, offer to connect them, and run `/superctx:add <path>` after consent.
- Hub missing or empty: explain the issue, and offer to inspect the setup (as automatic hub recovery is not supported).
- Missing backups: note that original content may not be recoverable.

Do not describe hub/shim/backup mechanics unless the user asks.
