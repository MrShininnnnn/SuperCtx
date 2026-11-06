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

Supported rules and skills (currently Claude Code's `.claude/rules/` and `.claude/skills/`, Cursor's `.cursor/rules/` and `.cursor/skills/`, Grok Build's `.grok/skills/`, and OpenAI Codex's `.agents/skills/`) are moved into `.ctx/` and linked back to their original paths, so the tool keeps loading them. Reference and planning folders (for example `docs/architecture` or `.planning`) are connected the same way with `/superctx:add <folder>`, so existing readers and writers keep using their original paths. Anything SuperCtx cannot move safely stays where it is, and sync says why.

Which tools and versions were tested, and what v0.2 leaves alone (commands, subagents, hooks, MCP and other tool configuration), is in [architecture/compatibility.md](architecture/compatibility.md).

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

Connect one instruction file, rule, skill, or folder to the shared context.

Use this for a candidate that sync lists, a local instruction file such as `.agy/ANTIGRAVITY.md`, or a reference or planning folder such as `docs/architecture` or `.planning`. Running it again on something already connected reports it as already tracked.

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

With a rule and a skill as well:

```text
.claude/CLAUDE.md
.claude/rules/python.md
.claude/skills/review/
.codex/AGENTS.md
GEMINI.md
```

After `/superctx:sync`:

```text
.ctx/
  SUPERCTX.md
  superctx.toml      # manifest
  manifest.toml      # makes SuperCtx 0.1.4 commands refuse this repo
  rules/python.md
  skills/review/
  sources/           # local backups of the originals (gitignored)

.claude/CLAUDE.md          # points to .ctx/SUPERCTX.md
.claude/rules/python.md -> ../../.ctx/rules/python.md
.claude/skills/review   -> ../../.ctx/skills/review
.codex/AGENTS.md           # points to .ctx/SUPERCTX.md
GEMINI.md                  # points to .ctx/SUPERCTX.md
```

Edit `.ctx/SUPERCTX.md` for shared instructions. Rules and skills can be edited in `.ctx/` or through their original paths; both are the same file.

## When sync reports a conflict

Sync never overwrites something it did not write. It leaves it in place, reports it, and exits with status 1. Missing pointers and links elsewhere are still repaired in the same run and listed as repaired, so a run can report both:

| Reason | What happened | To resolve |
|---|---|---|
| `native_edited` | someone wrote into a generated pointer such as `CLAUDE.md` | move that text into `.ctx/SUPERCTX.md`, delete the file, run sync |
| `native_replaced` | a real file or folder replaced a link | merge its changes into the `.ctx/` copy, delete it, run sync |
| `link_retargeted` | a link now points somewhere else | delete the link, run sync |
| `canonical_missing` | the `.ctx/` copy is gone | restore it from version control (or `.ctx/sources/` on the machine that set it up), run sync |

Deleted pointers and links are recreated by the next sync.

## Upgrading from 0.1

1. Update the plugin (see [Updating](#updating)).
2. Run `/superctx:sync` once in each repository. It copies `.ctx/manifest.toml` to `.ctx/manifest.v1.toml`, writes the new manifest `.ctx/superctx.toml`, and turns `.ctx/manifest.toml` into a compatibility marker. `.ctx/SUPERCTX.md` and its content are kept, and pointers are refreshed to the current wording.
3. Commit the `.ctx/` changes, and have everyone working in the repository update to SuperCtx 0.2. While `.ctx/manifest.toml` is present, the SuperCtx 0.1.4 commands (`sync`, `add`, `add --create-shim`) report an invalid manifest and write nothing; this is the release gate's tested guarantee. It is not tested for other 0.1.x versions. Do not delete `.ctx/manifest.toml`: without it, 0.1.4's internal setup function (not reachable from its commands) would set up again over `.ctx/SUPERCTX.md`, a known hazard kept as an expected failure in `tests/test_v2_migration_safety.py`.
4. Rules, skills, and `.planning` already in the repository are listed as candidates rather than moved. Connect each one you want managed with `/superctx:add <path>`.

If the upgrade is interrupted, run `/superctx:sync` again; it resumes from `.ctx/manifest.v1.toml`. If `.ctx/superctx.toml` is lost after the upgrade, sync refuses to rebuild it, because the v1 copy does not record resources added since; restore it from version control.

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
- original instruction files, rules, skills, and folders are backed up under `.ctx/sources/`
- generated shims and links are disposable and can be repaired
- tool configuration (settings, hooks, agents, plugins, MCP) is never moved
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
