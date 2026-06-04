---
name: superctx:using-superctx
description: Use when entering a repository with a .ctx/ hub, or when the user asks about project context, agent instructions, tool configuration, sync, health, candidates, broken shims, or cross-tool context.
---

# SuperCtx Reference Guide

This skill orients coding agents on how to interact with the project-local SuperCtx context hub.

## When to Use

Use this skill whenever:
- A `.ctx/` directory exists in the project root.
- The user asks about project context, agent instructions, or tool configuration.
- The user asks about sync, health, candidates, broken shims, or cross-tool context.
- The user asks to update or apply context changes across agents.

## Core Model

SuperCtx provides a central project-local context layer using a hub-and-shim model:

- **`.ctx/SUPERCTX.md`** is the canonical project context hub.
- **Tool-specific instruction files** (e.g. `.claude/CLAUDE.md`, `.codex/AGENTS.md`) are generated shims/adapters pointing to the hub.
- **`.ctx/sources/`** contains inactive recovery copies of original instruction files.

## Agent Rules

1. **Stay quiet about internals.** Do not explain hub/shim/backup mechanics unless the user asks. Use SuperCtx context naturally without announcing how it works.
2. **Announce SuperCtx interactions.** When SuperCtx is relevant or actively shaping the work, announce in one short sentence before taking action:
   `Using SuperCtx to <purpose>.`
   Keep the announcement task-specific.
3. **Do NOT ask users to manually edit `manifest.toml` or `SUPERCTX.md` as the happy path.** Prefer agent action and SuperCtx commands.
4. **Avoid saying "sync context" unless actually running `/superctx:sync`.** The sync command is strictly for shim repair, not general context updates.
5. **Do NOT import `.ctx/sources/` backups as active context.** Agents must not read or load files from `.ctx/sources/` as active context. SuperCtx internals may read them for recovery and status checks.
6. **Do NOT edit generated shims as the source of truth.** Tool-specific files are thin generated pointers to `.ctx/SUPERCTX.md`.
7. **Use `/superctx:sync` for repair only.** It regenerates missing or broken shims from the hub; it does not update the hub from tool files.
8. **Offer agent-guided setup with explicit user consent when relevant.** If a candidate repository is detected (state `candidate_repo`) and the user's request is relevant (e.g., asking about project context, instructions, or tool alignment), do not run `/superctx:init` or mutate files without the user's explicit natural-language consent, disclosing that files will be backed up and shims written (e.g., asking: 'I can set up one shared context hub. This will back up the originals to .ctx/sources/ and replace the live instruction files with generated shims. Proceed?'). Once consent is given, run `/superctx:init`.
9. **Guide legacy or broken setups to repair/migration/inspection.**
   - If the state is `managed_needs_repair` and the recommended action is `repair`, run `/superctx:status` and `/superctx:sync` to restore shims from the hub.
   - If the state is `managed_needs_repair` and the recommended action is `inspect` (due to missing or invalid manifest), explain the problem clearly and do not run `sync` or `init`.
   - If the state is `managed_legacy`, explain the situation clearly, warning that migration/recovery is required. Preserve existing instruction contents and use explicit user-approved migration steps; do not delete `.ctx` or run a fresh setup ad hoc.
   Never run `/superctx:init` or mutate files on a repair/migration state without explicit user consent.

### Action Cues (Before Action)

Announce these cues *before* starting the corresponding action or command. Replace `<path>` with the actual file path.

| Situation | Phrase |
| --- | --- |
| Updating instructions | `Using SuperCtx to update the shared project context across connected agents.` |
| Checking health | `Using SuperCtx to check context health.` |
| Adding a local file | `Using SuperCtx to connect <path> as a local context file.` |
| Repairing shims | `Using SuperCtx to repair generated context shims.` |
| Offering setup | `Using SuperCtx to offer project context management setup.` |

### Result Confirmation Phrases (After Action)

Use these phrases to report successful execution when the command output is healthy.

| Situation | Phrase |
| --- | --- |
| Healthy result | `All SuperCtx context links are healthy.` |

## Command Guide

- `/superctx:init`: Scaffolds the `.ctx/` hub, auto-detects standard files, imports original content, stores inactive backups, and writes generated shims.
- `/superctx:add <path>`: Tracks a local custom candidate file, imports its current content into the hub, stores an inactive backup, and writes a generated shim.
- `/superctx:status`: Reports hub, shim, backup, and candidate health.
- `/superctx:sync`: Repairs missing or broken registered shims without rewriting the hub.

## Example Workflows

### Workflow 1: Updating project instructions
- **User:** "Update the project instructions to include Y."
- **Agent Action:** Update `.ctx/SUPERCTX.md`, then run `/superctx:status` to verify that registered shims are still healthy.

### Workflow 2: Checking context for a specific tool
- **User:** "What context does Codex have?"
- **Agent Action:** Inspect the registered Codex shim, then read `.ctx/SUPERCTX.md` as the canonical project context. If freshness matters, run `/superctx:status`.

### Workflow 3: Checking connection and health
- **User:** "Is everything connected?"
- **Agent Action:** Run `/superctx:status`.

### Workflow 4: Repairing generated shims
- **User:** "The Codex instruction file is missing."
- **Agent Action:** Run `/superctx:status`. If the registered shim is missing or broken, run `/superctx:sync` to repair it.

### Workflow 5: Tracking a new instruction file
- **User:** "I added a new tool instruction file at .agy/ANTIGRAVITY.md."
- **Agent Action:** Run `/superctx:add .agy/ANTIGRAVITY.md`.
