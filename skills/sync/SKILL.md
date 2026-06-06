---
name: superctx:sync
description: Use when the user wants to repair or regenerate SuperCtx shims, or when /superctx:status reports missing or broken registered shim files.
---

# SuperCtx Sync

Repair the tracked tool instruction shims from the canonical `.ctx/` hub.

`/superctx:sync` does not pull tool-specific file contents into `.ctx/SUPERCTX.md`.
It checks registered shim files, regenerates missing or broken shims when safe, and reports
healthy, repaired, unresolved, and warning states.

## Before Running

Announce that you are using SuperCtx:
> Using SuperCtx to repair generated context shims.

## Run

```bash
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m superctx sync
```

Use this after `/superctx:status` reports missing or broken shims, or after a user asks to
restore generated tool instruction files that should point back to `.ctx/SUPERCTX.md`.

## Then report to the user

Present the output from the command. On the healthy path, confirm that all shims are healthy. Only surface shim states (repaired, unresolved, warnings) if the command reports problems. If the repository is not yet initialized with a `.ctx/` directory, offer to set up SuperCtx (with explicit consent).
