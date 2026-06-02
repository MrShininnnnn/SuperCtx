# SuperCtx

**All the context, in one place.**

SuperCtx keeps AI coding assistants aligned on one shared project context. It creates a project-local `.ctx/` hub from files like `CLAUDE.md`, `AGENTS.md`, and `GEMINI.md`, then keeps tool-specific instruction files as thin generated shims pointing back to that hub.

Many coding tools use their own project instruction files:

```text
CLAUDE.md
AGENTS.md
GEMINI.md
.github/copilot-instructions.md
```

When you use more than one tool, those files can drift apart. SuperCtx gives the project one context layer and exposes it consistently across Claude Code, Codex, Gemini, Antigravity, Copilot, Cursor, and other AI coding tools.

## Why SuperCtx?

Use SuperCtx when a repository has more than one AI coding tool and you want those tools to share the same project assumptions.

SuperCtx helps you:

- reduce repeated copy-paste between tool-specific instruction files
- keep context project-local instead of sending it to a cloud memory service
- inspect which instruction files are connected to the shared context hub
- detect missing or broken generated shims and missing inactive backups
- dogfood project context workflows across Claude Code, Codex, Gemini, and related tools

## How It Works

SuperCtx uses a project-local context folder:

```text
.ctx/
```

The `.ctx/` folder is the centralized hub for project context. SuperCtx makes `.ctx/SUPERCTX.md` the canonical hub, and generates thin shims pointing back to it:

```text
               ┌─> CLAUDE.md (shim)
.ctx/SUPERCTX.md ┼─> AGENTS.md (shim)
               └─> GEMINI.md (shim)
```

`SUPERCTX.md` is a version-controlled, hand-editable Markdown file that serves as the single source of truth. Original tool instruction files are backed up and converted to thin referential shims.

### Agent-Native Bootstrapping

SuperCtx includes a built-in agent reference skill, `/superctx:using-superctx`. Run it when working in a SuperCtx-enabled repository to orient Claude Code on the current project's context boundaries and active files.

In this release, SuperCtx uses a **hub-and-shim** model: agents and users edit the shared project context in `.ctx/SUPERCTX.md` directly. Tool-specific files are generated shims that point back to the hub.

In all versions, SuperCtx is designed to be agent-native: agents should invoke the appropriate slash commands rather than telling users to edit `.ctx/manifest.toml` manually in the happy path.

## What SuperCtx Auto-Detects

SuperCtx scans the project directory during initialization and status reporting:

1. **Verified Instruction Files** (Auto-connected):
   Root-level `CLAUDE.md`, `AGENTS.md`, `GEMINI.md`, and hidden standard paths like `.claude/CLAUDE.md`, `.codex/AGENTS.md`, and `.github/copilot-instructions.md`. These are automatically added to `.ctx/manifest.toml`.
2. **Supported Folder Candidates** (Surfaced, not auto-connected):
   Known standard folder layouts like `.agents/rules/` and `agents/skills/` are surfaced as candidates for future connection work.
3. **Legacy or Uncertain Candidates** (Surfaced, not auto-connected):
   Legacy layouts such as `.agent/rules/` or `.agents/skills/` are reported.
4. **Unverified Local Candidates** (Surfaced, not auto-connected):
   Local conventions such as `.agy/` or `.agy/ANTIGRAVITY.md` are surfaced and labeled as unverified local candidates (not official support).

## User Installation

SuperCtx is early software. Today, install it directly from GitHub for Claude Code or run the Python CLI from a source checkout.

### Install directly from GitHub today

From inside Claude Code, add this repository as a plugin marketplace and install the `superctx` plugin:

```text
/plugin marketplace add MrShininnnnn/SuperCtx
/plugin install superctx@superctx
```

Claude Code copies marketplace plugins into Claude's local plugin cache. After installing or updating the plugin, restart Claude Code if the new skills do not appear immediately.

### Load the plugin in Claude Code

After installation, the SuperCtx skills are available as slash commands:

```text
/superctx:init
/superctx:sync
/superctx:status
/superctx:add <path>
```

Run those commands from a repository that has one or more context files such as `CLAUDE.md`, `AGENTS.md`, or `GEMINI.md`.

### Coming Soon: Claude Community Marketplace

If accepted into the Claude community marketplace, SuperCtx will be installable with:

```text
/plugin marketplace add anthropics/claude-plugins-community
/plugin install superctx@claude-community
```

Until then, use the GitHub installation path above.

## Updating SuperCtx

To update SuperCtx to the latest version, run the following commands inside Claude Code:

```text
/plugin marketplace update superctx
/plugin update superctx
/reload-plugins
```

If updating does not resolve issues or if you suspect a cached or stale version is running, uninstall and reinstall the plugin to force-clear the local cache:

```text
/plugin uninstall superctx
/plugin install superctx@superctx
/reload-plugins
```

As a last resort if plugin caches persist, you can manually clear the Claude plugin cache directories under your user home profile.

## Quick Start

Inside Claude Code:

```text
/superctx:init
/superctx:status
```

The workflow:

1. `/superctx:init` scans the project for known tool instruction files, populates `.ctx/SUPERCTX.md` with their contents, backs them up under `.ctx/sources/`, and replaces them with generated shims.
2. `/superctx:status` reports structural integrity and health of the hub, registered shims, backups, and untracked candidates.

If status reports missing or broken shims, run `/superctx:sync` to repair the generated shim files from the hub.

Example status output:

```text
Hub:
- .ctx/SUPERCTX.md exists

Registered files:
- .claude/CLAUDE.md imports .ctx/SUPERCTX.md
- .codex/AGENTS.md points to .ctx/SUPERCTX.md

Backups:
- .ctx/sources/.claude/CLAUDE.md
- .ctx/sources/.codex/AGENTS.md

Candidates:
- .agy/ANTIGRAVITY.md untracked local candidate
```

## Command Discovery and Namespace Safety

SuperCtx commands are registered under the `superctx:` namespace to avoid colliding with Claude Code built-in slash commands such as `/init`, `/status`, and `/sync`.

After installing or reloading the plugin (`/reload-plugins`), you can verify command discovery:

**Type `/superctx` in Claude Code** — the command palette should show only:

```text
/superctx:init
/superctx:sync
/superctx:status
/superctx:add
```

**Type `/status`** — only the Claude Code built-in status command should appear. SuperCtx does not register an unprefixed `/status` command.

**Run `/superctx:status`** — SuperCtx reports diagnostics plus hub-and-shim health (hub existence, shim targets, backups, and untracked candidates).

## CLI Usage

SuperCtx also ships a Python CLI. From a source checkout with the package installed:

```bash
superctx init
superctx sync
superctx status
superctx add <path>
```

`superctx sync` is a repair/recovery command for registered shims. It does not rewrite `.ctx/SUPERCTX.md` from tool-specific files.

The same commands can be run without the console script:

```bash
python -m superctx init
python -m superctx sync
python -m superctx status
python -m superctx add <path>
```

## Current Status

SuperCtx is in early development. The first version focuses on one practical task:

> Keep project-specific AI coding context in one local hub and expose it through tool-specific shims.

The current implementation includes:

- `init`, `sync`, and `status`
- auto-detection of known tool instruction files
- a deterministic Python engine using the standard library
- shim repair for missing or broken registered instruction files
- snapshot tests for generated demo project files
- CI for the Python test suite
- a Claude Code plugin manifest and marketplace catalog installable from GitHub

## What SuperCtx Is

SuperCtx is:

- a project-context hub and shim tool
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
5. Avoid storing secrets, credentials, caches, and local sessions.
6. Support one implementation path first, but design for many tools.
7. Stay focused on shared project context and shim repair.

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

Project-local agent folders and workflow notes are gitignored to prevent committing local setups, but SuperCtx scans and reports files inside them as candidates:

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
