# SuperCtx

**All the context, in one place.**

SuperCtx keeps AI coding assistants aligned on one shared project context. It centralizes project instructions from files like `CLAUDE.md`, `AGENTS.md`, and `GEMINI.md` into a project-local `.ctx/` hub so teams can see what each tool knows and detect drift before it becomes confusing.

Many coding tools use their own project instruction files:

```text
CLAUDE.md
AGENTS.md
GEMINI.md
.github/copilot-instructions.md
```

When you use more than one tool, those files can drift apart. SuperCtx gives the project one context layer and helps synchronize it across Claude Code, Codex, Gemini, Antigravity, Copilot, Cursor, and other AI coding tools.

## Why SuperCtx?

Use SuperCtx when a repository has more than one AI coding tool and you want those tools to share the same project assumptions.

SuperCtx helps you:

- reduce repeated copy-paste between tool-specific instruction files
- keep context project-local instead of sending it to a cloud memory service
- inspect which instruction files were pulled into the shared context hub
- detect when a tool-specific file changed after the last sync
- dogfood project context workflows across Claude Code, Codex, Gemini, and related tools

## How It Works

SuperCtx uses a project-local context folder:

```text
.ctx/
```

The `.ctx/` folder is the centralized hub for project context. SuperCtx reads known tool instruction files and pulls them into `.ctx/SUPERCTX.md`:

```text
CLAUDE.md  ─┐
AGENTS.md  ─┼─>  .ctx/SUPERCTX.md
GEMINI.md  ─┘
```

`SUPERCTX.md` is a structured aggregation of the source instruction files with provenance for each source. Your original tool files are never modified.

## User Installation

SuperCtx is early software. Today, install it directly from GitHub for Claude Code or run the Python CLI from a source checkout.

### Install directly from GitHub today

From inside Claude Code, add this repository as a plugin marketplace and install the `superctx` plugin:

```text
/plugin marketplace add MrShininnnnn/SuperCtx
/plugin install superctx@superctx
```

Claude Code marketplace installs copy plugins into Claude's local plugin cache. After installing or updating the plugin, restart Claude Code if the new skills do not appear immediately.

### Load the plugin in Claude Code

After installation, the SuperCtx skills are available as slash commands:

```text
/superctx:init
/superctx:sync
/superctx:status
```

Run those commands from a repository that has one or more context files such as `CLAUDE.md`, `AGENTS.md`, or `GEMINI.md`.

### Coming Soon: Claude Plugin Marketplace

SuperCtx is not yet available in the official Claude plugin marketplace.

After marketplace acceptance, the intended install path is:

```text
/plugin install superctx@claude-plugins-official
```

Until then, use the GitHub installation path above.

## Quick Start

Inside Claude Code:

```text
/superctx:init
/superctx:sync
/superctx:status
```

The workflow:

1. `/superctx:init` scans the project for known tool instruction files and creates `.ctx/` with a manifest.
2. `/superctx:sync` pulls tracked tool files into `.ctx/SUPERCTX.md`.
3. `/superctx:status` reports whether tracked files are synced, drifted, missing, or untracked.

Example status output:

```text
synced     CLAUDE.md
drifted    AGENTS.md
untracked  GEMINI.md
```

Run `/superctx:sync` any time a tool instruction file changes.

## CLI Usage

SuperCtx also ships a Python CLI. From a source checkout with the package installed:

```bash
superctx init
superctx sync
superctx status
```

The same commands can be run without the console script:

```bash
python -m superctx init
python -m superctx sync
python -m superctx status
```

## Current Status

SuperCtx is in early development. The first version focuses on one practical task:

> Centralize project-specific AI coding context from multiple tool instruction files into one hub.

The current implementation includes:

- `init`, `sync`, and `status`
- auto-detection of known tool instruction files
- a deterministic Python sync engine using the standard library
- snapshot tests for generated demo project files
- CI for the Python test suite
- a Claude Code plugin manifest and GitHub marketplace catalog

## What SuperCtx Is

SuperCtx is:

- a project-context synchronization tool
- a shared context layer for AI coding tools
- a way to reduce repeated copy-paste
- a way to keep coding assistants aligned
- a project-local system, not a cloud service

## What SuperCtx Is Not

SuperCtx is not:

- a coding assistant
- an agent framework
- a task orchestration system
- a replacement for Claude Code, Codex, Gemini, Cursor, Copilot, or Antigravity
- a cloud memory database
- a secret manager

## Design Principles

1. One project context.
2. Keep context project-local.
3. Start simple.
4. Treat generated files as disposable.
5. Avoid syncing secrets, credentials, caches, and local sessions.
6. Support one implementation path first, but design for many tools.
7. Stay focused on context synchronization.

## Contributor / Development Setup

SuperCtx requires Python 3.11 or newer.

From a fresh clone:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test]'
python -m pytest tests/ -v
```

Use the editable install for local CLI development:

```bash
superctx init
superctx sync
superctx status
```

Project-local agent folders and workflow notes are intentionally ignored:

```text
.claude/
.codex/
.agy/
docs/
```

Keep those local-only files out of commits.

## Contributing

Contributions, bug reports, examples, and use cases are welcome.

SuperCtx is still early, so please open an issue before making large design changes, adding new skills, or changing generated file conventions.

For contribution details, see [CONTRIBUTING.md](CONTRIBUTING.md).

## Author

SuperCtx is created and maintained by **Ning Shi (Shining)**.

## License

MIT
