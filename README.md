# SuperCtx

**All the context, in one place.**

SuperCtx keeps AI coding assistant instruction files aligned through one shared `.ctx/SUPERCTX.md` hub. It backs up original instruction files, then keeps tool-specific files as generated shims that point back to the shared project context.

## Why SuperCtx?

AI coding tools expect project instructions in different places, such as `CLAUDE.md`, `AGENTS.md`, `GEMINI.md`, or tool-specific folders. When one repository uses multiple assistants, those files can drift.

SuperCtx gives the repository one local source of truth so Claude Code, Codex, Gemini, Copilot, Cursor, Antigravity, and similar tools can share the same project guidance.

## How It Works

SuperCtx creates a project-local hub:

```text
.ctx/SUPERCTX.md
```

Tool-specific instruction files remain where each assistant expects them, but become generated shims:

```text
.ctx/SUPERCTX.md        # shared project context hub
.claude/CLAUDE.md       # generated shim
.codex/AGENTS.md        # generated shim
GEMINI.md               # generated shim
```

Original instruction files are backed up under `.ctx/sources/` before SuperCtx replaces live instruction files with shims.

## Install

Install SuperCtx directly from GitHub in Claude Code:

```text
/plugin marketplace add MrShininnnnn/SuperCtx
/plugin install superctx@superctx
```

After installing or updating, restart Claude Code if the SuperCtx commands do not appear immediately.

Marketplace installation is planned for a future release.

## Use

### `/superctx:sync`

Set up, check, repair, and report SuperCtx state for the current repository.

Use this as the main command when entering a repository or when project context needs attention.

### `/superctx:add <path>`

Add or connect one specific instruction file to the shared context hub.

Use this when you have a local instruction file that SuperCtx should manage with the rest of the project context.

### `/using-superctx`

Agent-facing reference skill for using SuperCtx correctly.

Most users do not need to run this directly; it exists so agents can orient themselves around the repository's shared context.

## Example

Before SuperCtx:

```text
.claude/CLAUDE.md
.codex/AGENTS.md
GEMINI.md
```

After `/superctx:sync`:

```text
.ctx/
  SUPERCTX.md
  manifest.toml
  sources/
    .claude__CLAUDE.md
    .codex__AGENTS.md
    GEMINI.md

.claude/CLAUDE.md
.codex/AGENTS.md
GEMINI.md
```

The files at `.claude/CLAUDE.md`, `.codex/AGENTS.md`, and `GEMINI.md` remain available to their tools, but they point back to `.ctx/SUPERCTX.md`.

## CLI

SuperCtx also ships a Python CLI for source checkouts:

```bash
superctx sync
superctx add <path>
```

The same commands can be run as a module:

```bash
python -m superctx sync
python -m superctx add <path>
```

## Updating

To update the installed Claude Code plugin:

```text
/plugin marketplace update superctx
/plugin update superctx
/reload-plugins
```

To force a reinstall:

```text
/plugin uninstall superctx
/plugin install superctx@superctx
/reload-plugins
```

## Safety

SuperCtx is local-first:

- project context stays in the repository
- original instruction files are backed up under `.ctx/sources/`
- generated shims are disposable and can be repaired
- SuperCtx has no remote backend
- SuperCtx does not provide telemetry or analytics

Do not put secrets, credentials, API keys, or sensitive personal data in project instruction files.

## Development

SuperCtx requires Python 3.9 or newer. Python 3.11+ is recommended.

From a fresh clone:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test]'
python -m pytest tests/ -v
```

Run local validation before opening a pull request:

```bash
python -m pytest tests/ -v
claude plugin validate .
```

For contribution details, see [CONTRIBUTING.md](CONTRIBUTING.md).

## Project Policies

- [Privacy Policy](PRIVACY.md)
- [Security Policy](SECURITY.md)
- [Code of Conduct](CODE_OF_CONDUCT.md)
- [Contributing](CONTRIBUTING.md)

## Author

SuperCtx is created and maintained by **Ning Shi (Shining)**.

## License

MIT
