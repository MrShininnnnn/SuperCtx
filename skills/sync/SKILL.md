---
name: superctx:sync
description: Use when the user wants to set up, check, repair, or report the SuperCtx state for this repository. Consolidated command for global context convergence.
---

# SuperCtx Sync

Converge this repository into the correct SuperCtx state. `/superctx:sync` is the global setup, check, repair, and report command.

It checks the health of registered shims and links, sets up candidate repos in one step, repairs missing shims and links when safe, and reports healthy, repaired, unresolved, left-in-place, and warning states. It never overwrites a shim someone edited.

## Before Running (Consent Boundary)

1. **Direct User Invocation**: If the user explicitly typed `/superctx:sync` or asked you to sync/repair/setup the repo, you have consent. Announce the action:
   > Using SuperCtx to synchronize and verify project context.
2. **Agent-Initiated Flow**: If you detect a setup opportunity (no `.ctx/` folder but candidate files exist) or shim issues during a task, you **MUST** obtain explicit natural-language user consent before running the command. Use this consent prompt for setup:
   > Using SuperCtx, I can set up one shared context hub for this repo.
   >
   > This will:
   > - create `.ctx/SUPERCTX.md`
   > - back up the original instruction files, rules, and skills under `.ctx/sources/`
   > - replace the live instruction files with generated shims pointing to the hub
   > - move supported rules and skills into `.ctx/` and leave a link at their original path, so tools keep using them
   >
   > Proceed?

Do not run `/superctx:sync` or make any mutations until you have explicit consent.

## Run

```bash
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m superctx sync
```

## Then report to the user

Present the output from the command:
- On the **healthy** path (exit 0), confirm concisely that all shims are healthy:
  > All SuperCtx context links are healthy.
- On **initialization** (exit 0), confirm the connected instruction files, the linked rules and skills, the hub location, and any backups.
- On **repair** (exit 0), list the repaired shims and links.
- On **unresolved** items (exit 1), explain each reason. The same run may also have repaired other missing shims or links; report those repairs as well. `native_edited` means someone wrote content into a generated shim: it was left in place, so offer to move that content into `.ctx/SUPERCTX.md` before restoring the shim. Link conflicts (`link_retargeted`, `native_replaced`, `canonical_missing`) were also left untouched; explain them and ask how to proceed.
- For anything listed under **Left in place**, relay the reason. These are not errors: SuperCtx only adopts resources whose tool behavior it has verified.
- On **legacy or inspection warning/stops** (exit 1), explain the warning and explain what needs to be inspected. Do not attempt automatic repair.
