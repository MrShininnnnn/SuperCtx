---
name: sync
description: Use when the user wants to centralize, refresh, or update the .ctx hub, or after editing CLAUDE.md / AGENTS.md / GEMINI.md and wanting those changes pulled into .ctx. Also use when /superctx:status reports drift.
---

# SuperCtx Sync

Pull the tracked tool instruction files into the `.ctx/` hub. Inward only — tool files are read,
never modified.

## Run

```bash
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m superctx sync
```

This snapshots each tracked file into `.ctx/sources/<same path>` and regenerates
`.ctx/SUPERCTX.md` as a structured aggregation (each file's content under a `## From: <path>`
provenance header).

## Then report to the user

- Which files were centralized, and any tracked-but-missing files.
- Remind that `.ctx/SUPERCTX.md` is **generated** — to change it, edit the underlying tool files
  and re-run sync, don't hand-edit the hub.

If the user has no `.ctx/` yet, run `/superctx:init` first.
