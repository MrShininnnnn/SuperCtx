---
name: status
description: Use when the user asks whether their tool instruction files have drifted from the .ctx hub, wants a SuperCtx status check, or asks what needs syncing. Also use to verify the hub is current before relying on it.
---

# SuperCtx Status

Report whether the tracked tool files match what's centralized in `.ctx/`. Read-only — never
writes.

## Run

```bash
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m superctx status
```

## Then present the result

Each tracked path reports one state:

| State | Meaning |
|-------|---------|
| `synced` | live file matches its `.ctx/sources/` snapshot |
| `drifted` | live file changed since last sync (or never synced) |
| `missing` | tracked in the manifest but the file is gone |
| `untracked` | a known instruction file exists in the repo but isn't in the manifest |

If anything is `drifted` or `untracked`, recommend `/superctx:sync`. For `untracked`, mention the
file can be added to `.ctx/manifest.toml`. For `missing`, ask whether the file was intentionally
removed.
