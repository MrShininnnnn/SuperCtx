---
name: superctx:add
description: Use when the user wants to start tracking a local custom instruction file (like .agy/ANTIGRAVITY.md or .github/copilot-instructions.md) in SuperCtx. Requires a path argument.
---

# SuperCtx Add

Add a local candidate file to the SuperCtx manifest to begin tracking it.

## Before Running

Announce that you are using SuperCtx (replace `<path>` with the actual file path argument):
> Using SuperCtx to connect <path> as a local context file.

## Check File Existence First

Before running the add command, check whether the file exists in the project.

**If the file exists:** Run the add command normally:

```bash
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m superctx add "$ARGUMENTS"
```

**If the file does not exist and is a known standard convention** (e.g. `GEMINI.md`, `.claude/CLAUDE.md`, `.codex/AGENTS.md`, `.github/copilot-instructions.md`):

Explain that the file does not exist yet, and offer to create it as a generated shim:

> I do not see an existing `<path>`. I can create it as a generated shim pointing to `.ctx/SUPERCTX.md`. Proceed?

After the user confirms, run with `--create-shim`:

```bash
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m superctx add --create-shim "$ARGUMENTS"
```

Do not create any file before receiving the user's explicit consent.

**If the file does not exist and is not a known standard convention:**

Explain clearly that the file must exist before it can be tracked:

> `<path>` does not exist yet. SuperCtx tracks existing instruction files. Please create the file first or let me know if you would like me to create and connect it for you.

## Then report to the user

Present the result printed by the command. On the healthy path, keep the report concise: confirm the file is now connected and that `.ctx/SUPERCTX.md` is the canonical context. Only surface backup or shim details if the command reports a warning or error.
