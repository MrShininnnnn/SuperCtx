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

1. **Do NOT import `.ctx/sources/` backups as active context.** Agents must not read or load files from `.ctx/sources/` as active context. SuperCtx internals may read them for recovery and status checks.
2. **Do NOT instruct users to edit TOML manually.** In the happy path, always use `/superctx:add <path>` or `/superctx:init` rather than telling the user to edit `.ctx/manifest.toml`.
3. **Do NOT edit generated shims as the source of truth.** Tool-specific files should remain thin generated pointers to `.ctx/SUPERCTX.md`.
4. **Update instructions in the hub.** Make project instruction changes in `.ctx/SUPERCTX.md`, then use `/superctx:status` to verify health.
5. **Use `/superctx:sync` for repair only.** It regenerates missing or broken shims from the hub; it does not update the hub from tool files.

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
