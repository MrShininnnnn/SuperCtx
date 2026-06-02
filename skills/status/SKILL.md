---
name: superctx:status
description: Use when the user asks whether their tool instruction files have drifted from the .ctx hub, wants a SuperCtx status check, or asks about hub-and-shim health. Also use to verify the hub is current and shims are healthy before relying on them.
---

# SuperCtx Status

Report structural integrity and health of the hub-and-shim v0.2 model. Read-only — never writes.

## Run

```bash
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m superctx status
```

## Then present the result

The command reports health states for the hub, registered shims, backups, and untracked candidates:

| State | Meaning |
|-------|---------|
| `healthy` | All structural integrity checks passed for the hub, shim, or backup |
| `missing_shim` | Registered file does not exist in the project |
| `broken_shim` | Registered file exists but is not a valid generated shim pointing to the hub |
| `missing_backup` | Original backup copy under `.ctx/sources/` is missing |
| `missing_hub` | The canonical `.ctx/SUPERCTX.md` hub does not exist |
| `empty_hub` | The canonical `.ctx/SUPERCTX.md` hub is empty |
| `untracked_candidate` | Local convention candidate path matches a standard convention but is not tracked |

If shims or backups are broken or missing, instruct the user to run `/superctx:sync` to repair them. For untracked candidates, suggest running `/superctx:add <path>` to begin tracking them.
