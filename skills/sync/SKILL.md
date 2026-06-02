---
name: superctx:sync
description: Use when the user wants to repair or regenerate SuperCtx shims, or when /superctx:status reports missing or broken registered shim files.
---

# SuperCtx Sync

Repair the tracked tool instruction shims from the canonical `.ctx/` hub.

`/superctx:sync` does not pull tool-specific file contents into `.ctx/SUPERCTX.md`.
It checks registered shim files, regenerates missing or broken shims when safe, and reports
healthy, repaired, unresolved, and warning states.

## Run

```bash
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m superctx sync
```

Use this after `/superctx:status` reports missing or broken shims, or after a user asks to
restore generated tool instruction files that should point back to `.ctx/SUPERCTX.md`.

## Then report to the user

- Which shims were already healthy.
- Which shims were repaired.
- Any unresolved files and the reason they could not be repaired safely.
- Any warnings, especially missing inactive backups under `.ctx/sources/`.

If the user has no `.ctx/` yet, run `/superctx:init` first.
