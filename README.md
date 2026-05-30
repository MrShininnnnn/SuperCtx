# SuperCtx

**One project context. Every coding tool.**

SuperCtx helps keep AI coding assistants aligned on the same project context.

Many coding tools use their own project instruction files:

```text
CLAUDE.md
AGENTS.md
GEMINI.md
.github/copilot-instructions.md
```

When you use more than one tool, these files can drift apart. You may update instructions in one place, forget to copy them elsewhere, and later get inconsistent behavior from different assistants.

SuperCtx gives each project one shared context layer and helps synchronize it across tools.

## Why SuperCtx?

If you use Claude Code, Codex, Gemini, Cursor, Copilot, Antigravity, or other AI coding tools in the same repository, you often need to repeat the same project instructions again and again.

SuperCtx aims to reduce that repeated copy-paste.

Instead of manually maintaining several context files, you keep one project context hub and let SuperCtx centralize the tool-specific files when needed.

## How It Works

SuperCtx uses a project-local context folder:

```text
.ctx/
```

The `.ctx/` folder is the centralized hub for project context.

SuperCtx reads your existing tool-specific instruction files and pulls them into the hub:

```text
CLAUDE.md  ─┐
AGENTS.md  ─┼─→  .ctx/SUPERCTX.md
GEMINI.md  ─┘
```

`SUPERCTX.md` is a structured aggregation of all your tool instruction files in one place, with clear provenance for each source. Your original tool files are never modified.

## Basic Workflow

**1. Initialize the hub** (run once per project):

```text
/superctx:init
```

SuperCtx scans the project for known tool instruction files and creates `.ctx/` with a manifest.

**2. Centralize the context:**

```text
/superctx:sync
```

Pulls the tracked tool files into `.ctx/SUPERCTX.md`.

**3. Check for drift:**

```text
/superctx:status
```

Reports whether any tool instruction file has changed since the last sync:

```text
synced     CLAUDE.md
drifted    AGENTS.md
untracked  GEMINI.md
```

Run `/superctx:sync` any time a tool file changes to keep the hub current.

## Current Status

SuperCtx is in early development. The first version focuses on one practical task:

> Centralize project-specific AI coding context from multiple tool instruction files into one hub.

The current implementation includes:

* `init`, `sync`, and `status` skills
* auto-detection of known tool instruction files
* a deterministic Python sync engine (stdlib only, zero external dependencies)
* tests for the sync behavior

## What SuperCtx Is

SuperCtx is:

* a project-context synchronization tool
* a shared context layer for AI coding tools
* a way to reduce repeated copy-paste
* a way to keep coding assistants on the same page
* a project-local system, not a cloud service

## What SuperCtx Is Not

SuperCtx is not:

* a coding assistant
* an agent framework
* a task orchestration system
* a replacement for Claude Code, Codex, Gemini, Cursor, Copilot, or Antigravity
* a cloud memory database
* a secret manager

## Design Principles

1. One project context.
2. Keep context project-local.
3. Start simple.
4. Treat generated files as disposable.
5. Avoid syncing secrets, credentials, caches, and local sessions.
6. Support one implementation path first, but design for many tools.
7. Stay focused on context synchronization.

## Contributing

Contributions, bug reports, examples, and use cases are welcome.

SuperCtx is still early, so please open an issue before making large design changes or adding new skills.

General contribution process:

1. Fork the repository.
2. Create a branch for your work.
3. Keep the change focused and small.
4. Add or update tests when relevant.
5. Submit a pull request with a clear explanation of what changed and why.

For skill-related changes, please make sure the skill supports SuperCtx's long-term goal: project-context synchronization across AI coding tools.

New skills should be discussed in an issue before implementation.

## Author

SuperCtx is created and maintained by **Ning Shi (Shining)**.

## License

MIT
