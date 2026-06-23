# SuperCtx

**All the context, in one place.**

SuperCtx keeps AI coding assistant instruction files aligned through one shared `.ctx/SUPERCTX.md` hub.

AI coding assistants like Claude Code, Gemini, Codex, and Copilot each rely on their own instruction files. If you use multiple assistants in the same project, these files can easily drift. SuperCtx consolidates your project guidelines into a single hub and exposes them consistently via generated shims.

## Why SuperCtx?

AI coding tools expect project context in different instruction files (e.g., `CLAUDE.md`, `AGENTS.md`, `GEMINI.md`). When using multiple tools in a single repository:
- Different tools expect guidelines in different paths.
- Instruction files can quickly drift out of sync.
- SuperCtx solves this by maintaining a single, shared source of truth.

## How It Works

SuperCtx maps your workspace's context guidelines through a single central hub:

```text
.ctx/SUPERCTX.md        # source of truth

.claude/CLAUDE.md       # generated shim
.codex/AGENTS.md        # generated shim
GEMINI.md               # generated shim
```

- `.ctx/SUPERCTX.md` is the canonical, version-controlled shared context hub.
- Tool-specific instruction files remain at their expected paths, but become generated shims pointing back to the hub.
- Original instruction files are backed up under `.ctx/sources/` before replacement.

## Install

Inside Claude Code, add this repository as a plugin marketplace and install the `superctx` plugin:

```text
/plugin marketplace add MrShininnnnn/SuperCtx
/plugin install superctx@superctx
```

## Use

### `/superctx:sync`

Set up, check, repair, and report SuperCtx state for the current repository.

Use it when:
- first setting up SuperCtx;
- checking whether SuperCtx is healthy;
- repairing generated shims;
- bringing the repo back into the expected SuperCtx layout.

### `/superctx:add <path>`

Add or connect one specific instruction file.

Examples:
```text
/superctx:add GEMINI.md
/superctx:add .github/copilot-instructions.md
/superctx:add .agy/ANTIGRAVITY.md
```

### `/using-superctx`

Agent-facing reference skill that explains how SuperCtx works.

*Note: This is an agent-facing skill that coding assistants use to guide their context workflows; you do not need to run it yourself.*

## Example

Before connecting:
```text
.claude/CLAUDE.md
.codex/AGENTS.md
GEMINI.md
```

After connecting with SuperCtx:
```text
.ctx/SUPERCTX.md
.ctx/manifest.toml
.ctx/sources/

.claude/CLAUDE.md
.codex/AGENTS.md
GEMINI.md
```

Your original files are safely backed up under `.ctx/sources/`, while the live files are replaced with generated shims.

## CLI

SuperCtx also includes a lightweight Python CLI:

```bash
superctx sync
superctx add <path>
```

## Updating the Plugin

To update the plugin or troubleshoot a stale installation in Claude Code, run:

```text
/plugin marketplace update superctx
/plugin update superctx
/reload-plugins
```

## Safety

- **Local First**: Files are managed entirely within your local repository.
- **Automatic Backups**: Pre-existing instruction files are backed up to `.ctx/sources/` before shimming.
- **Clearly Marked Shims**: Generated files are explicitly tagged with header comments warning against direct manual edits.
- **No Secrets**: Never place credentials, API keys, or private sessions in context instruction files.

## Development

For local development or testing:

```bash
# Run the test suite
python -m pytest tests/ -v

# Validate the Claude plugin manifest
claude plugin validate .
```

## Project Policies

- [PRIVACY.md](PRIVACY.md)
- [SECURITY.md](SECURITY.md)
- [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)
- [CONTRIBUTING.md](CONTRIBUTING.md)

## Author

Ning Shi (Shining).

## License

MIT.
