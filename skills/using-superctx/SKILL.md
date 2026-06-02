---
name: superctx:using-superctx
description: Use when entering a repository with a .ctx/ hub, or when the user asks about project context, agent instructions, tool configuration, sync, health, candidates, drift, or cross-tool context.
---

# SuperCtx Reference Guide

This skill orients coding agents on how to interact with the project-local SuperCtx context hub.

## When to Use

This skill should be referred to whenever:
- A `.ctx/` directory exists in the project root.
- The user asks about project context, agent instructions, or tool configuration.
- The user asks about sync, health, candidates, drift, or cross-tool context.
- The user asks to update or apply context changes across agents.

## Core Model

SuperCtx provides a centralized project-local context layer. It supports the following models:

### Current Model (Inward Sync)
- **Tool-specific instruction files** (e.g. `.claude/CLAUDE.md`, `.codex/AGENTS.md`) are the active source of truth.
- **`.ctx/SUPERCTX.md`** is a generated structured aggregation of the source files. Do not hand-edit it.
- **`.ctx/sources/`** contains snapshot backups of source files at the time of the last sync to detect drift.

### Planned v0.2 Model (Hub-and-Shim)
- **`.ctx/SUPERCTX.md`** will become the canonical hub.
- **Tool-specific instruction files** will be generated shims/adapters pointing to the hub.
- **`.ctx/sources/`** will be inactive recovery copies.

## Agent Rules

1. **Do NOT import `.ctx/sources/` backups as active context.** Agents must not read or load files from `.ctx/sources/` as active context (they are inactive recovery/drift snapshots). SuperCtx internals may read them for drift checks and status checks.
2. **Do NOT instruct users to edit TOML manually.** In the happy path, always use `/superctx:add <path>` or `/superctx:init` rather than telling the user to edit `.ctx/manifest.toml`.
3. **Updating Instructions (Current Model):** To update project instructions, edit the active tool files (e.g. `.claude/CLAUDE.md`, `.codex/AGENTS.md`) and run `/superctx:sync`. Do NOT edit `.ctx/SUPERCTX.md` directly.
4. **Updating Instructions (Planned v0.2 Model):** Under the planned v0.2 hub-and-shim model, instructions will be updated directly in `.ctx/SUPERCTX.md`, and generated shims normally must not be edited. For emergency repair, prefer regenerating shims through SuperCtx commands before hand-editing them.

## Command Guide

- `/superctx:init`: Scaffolds the `.ctx/` hub and auto-detects standard files.
- `/superctx:add <path>`: Tracks a local custom candidate file.
- `/superctx:status`: Reports health and drift states (`synced`, `drifted`, `missing`, `untracked`).
- `/superctx:sync`: Centralizes/pulls tracked instruction files into the hub.

## Example Workflows

### Workflow 1: Updating project instructions
- **User:** "Update the project instructions to include Y."
- **Agent Action:** Edit the active tool file (e.g. `.claude/CLAUDE.md` or `.codex/AGENTS.md`) and run `/superctx:sync`. Do not edit `.ctx/SUPERCTX.md`.

### Workflow 2: Checking context for a specific tool
- **User:** "What context does Codex have?"
- **Agent Action:** Inspect `.codex/AGENTS.md`. If freshness matters, run `/superctx:status` to verify whether tracked files match their latest SuperCtx snapshots before relying on the generated hub.

### Workflow 3: Checking connection and health
- **User:** "Is everything connected?"
- **Agent Action:** Run `/superctx:status`.

### Workflow 4: Tracking a new instruction file
- **User:** "I added a new tool instruction file at .agy/ANTIGRAVITY.md."
- **Agent Action:** Run `/superctx:add .agy/ANTIGRAVITY.md`.
