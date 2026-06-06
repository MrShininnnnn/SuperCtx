# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
