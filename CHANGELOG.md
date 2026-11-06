# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] - 2026-11-05

### Added
- One-step setup also adopts Claude Code rules (`.claude/rules/`) and skills (`.claude/skills/`), Cursor rules (`.cursor/rules/`) and skills (`.cursor/skills/`), and Grok Build skills (`.grok/skills/`). Each is backed up, moved into `.ctx/`, and replaced by a relative symlink, so the tool keeps loading it from its original path.
- `/superctx:add <path>` connects a rule, a skill, or a whole reference or planning folder (for example `docs/architecture` or `.planning`) the same way.
- Skills from every supported tool share `.ctx/skills/`. Same-name skills from two tools are both left in place and reported.
- Anything that cannot move without changing behavior stays in place, and sync reports why (for example `breaks_reference`, `unclear_reference`, `name_collision`, `tool_folder`, `links_unsupported`).
- Tested compatibility matrix with Claude Code, Cursor, and Grok Build versions (`architecture/compatibility.md`). Real-tool checks are in `tests/test_real_agents.py` (opt-in).

### Changed
- The manifest moves to `.ctx/superctx.toml` (schema 2). On first sync, `.ctx/manifest.toml` is copied to `.ctx/manifest.v1.toml` and replaced by a compatibility marker: while it is present, the SuperCtx 0.1.4 commands (`sync`, `add`) refuse the repository and write nothing (tested; other 0.1.x versions are not). With the marker deleted, 0.1.4's internal setup function, which its commands do not reach, would set up again over the hub; this known hazard is kept as an expected test failure. Interrupted upgrades resume, and a lost v2 manifest is reported instead of rebuilt. See "Upgrading from 0.1" in the README.
- Sync leaves edited pointers, replaced or retargeted links, and missing canonical copies in place, reports them as conflicts, and exits with status 1.

### Not included
- Commands, subagents, hooks, MCP configuration, local settings, plugins, and other tool configuration are never adopted. No folder inside a tool's own folder can be connected.
- OpenAI Codex skills (`.agents/skills/`) are discovered but not adopted until verified.

## [0.1.4] - 2026-06-22

### Changed
- Simplified the visible plugin command surface by consolidating setup, health checking, and shim repair under `/superctx:sync`.
- Removed `/superctx:init`, `/superctx:status`, `superctx init`, and `superctx status` as user-facing commands. Setup and health logic now remain internal modules used by `sync`, hooks, and tests.
- Kept `/superctx:add` as a targeted file operation; repositories should use `/superctx:sync` for global setup/check/repair before adding individual files.
- Updated `_cmd_sync` to format outputs and map exit codes intentionally: `inspect`, `legacy`, and unresolved `repair` now exit with code `1`.
- Bumped the plugin/package version to `0.1.4` so Claude Code installs can refresh the command palette and drop stale cached `/superctx:init` and `/superctx:status` entries after update/reload.

## [0.1.3] - 2026-06-05

### Added
- Integrated `PreToolUse` write guard to intercept edits/writes to agent instruction files.
- Intercepts writes in candidate repos, clean repos, and managed repos to enforce the hub-and-shim model.
- Added `UserPromptExpansion` hook to intercept `/init` prompt.
- Added unit/integration test coverage for path classification and interception rules.
- Added version consistency test.
- Support for creating missing standard-file shims (e.g. `GEMINI.md`) using `superctx add --create-shim`.
- Python 3.9/3.10 TOML compatibility (using fallback `tomli`).
- Write-guard redirection so realistic `CLAUDE.md` updates are centralized in `.ctx/SUPERCTX.md` instead of directly editing generated shims.

### Changed
- Improved generated hub banner wording to "managed by SuperCtx."
- Refined all user-visible warning/error dialogs to use agent-guided consent language instead of command-first instructions.

## [0.1.2] - 2026-06-05

### Changed
- Renamed the SuperCtx agent reference skill from `/superctx:using-superctx` to `/using-superctx` to match Superpowers-style reference skill naming.
- Reframed `/superctx:status` as the primary user-facing health command.
- Moved setup, add, and repair operations toward agent-guided flows with explicit consent.
- Improved candidate-repo, untracked-candidate, and repair guidance to avoid command-first UX.
- Reframed `/superctx:sync` as a hub-and-shim repair command that checks registered shims, repairs missing or broken shims when safe, warns on missing inactive backups, and never rewrites `.ctx/SUPERCTX.md` from tool-specific files.
- Removed legacy inward-sync behavior entirely; `superctx sync` has no `--legacy` compatibility mode and must not rebuild the hub from tool-specific files.
- Renamed the plugin skill command from `/superctx:setup` to `/superctx:init` to align with Claude Code command vocabulary and avoid confusion with Claude Code built-in `/init`.
- Renamed `skills/setup/` folder to `skills/init/` to match the new command name.
- Updated skill `name:` frontmatter fields to explicitly namespaced values (`superctx:init`, `superctx:sync`, `superctx:status`) to ensure Claude Code registers commands under the `superctx:` prefix.
- Updated README and all skill text to use `/superctx:init` consistently.
- Added "Command Discovery and Namespace Safety" section to README with smoke test instructions.
- Updated README marketplace installation target from `@claude-plugins-official` to `@claude-community` and added "Coming Soon: Claude Community Marketplace" section.
- Verified fresh install smoke test and command-palette evidence for marketplace submission readiness (20 pytest tests pass; `claude plugin validate .` passes).

### Fixed
- Ensured user-visible command discovery changes ship with a plugin version bump so updated installs can receive the latest plugin surface.

### Removed
- Moved the marketplace readiness report out of the tracked repository root because it is local development planning material.

## [0.1.1] - 2026-05-31

### Added
- Added active version and stale-cache diagnostics to the `/superctx:status` command.
- Integrated update/reinstall/troubleshooting guidance for stale cached plugins.
- Added version resolution support tracking environment (`CLAUDE_PLUGIN_ROOT`), parent-walk directories, and fallback package version.
- Added test coverage for all three version resolution cases.
- Created `CHANGELOG.md` and added a release checklist to `CONTRIBUTING.md`.

### Changed
- Bumped version to `0.1.1` across plugin manifests, marketplace descriptors, and Python engine.
