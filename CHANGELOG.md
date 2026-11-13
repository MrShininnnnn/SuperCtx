# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
- Generated instruction shims now describe the expected original backup location (if available), without claiming the backup exists. Exact historical pointer formats remain recognized and refresh safely; user edits, backup flags, and missing-backup diagnostics are preserved.
- First-time sync and `add` no longer adopt a file that already holds SuperCtx pointer text. Such text says nothing about what the file held before or whether a backup of that exists, so they refuse it and change nothing: an exact generated pointer is reported as `already_a_pointer`, and anything else carrying the SuperCtx generated marker as `pointer_with_changes`, including a pointer cut off before its hub reference. Before, they backed up the pointer text or imported it into `.ctx/SUPERCTX.md` as if it were original content, and `add` could report "Original content backed up" without making a backup, which later showed up as `missing_backup`. Real instruction files are adopted as before, `add` claims a backup only when it made one, and existing manifest entries are unchanged. If every instruction file is refused, first-time sync creates no `.ctx/` and exits 1. (#108)
- Sync, the session-start hook, and the edit guard no longer offer to connect a file holding SuperCtx pointer text, or to set SuperCtx up for it, since `add` and first-time sync refuse such files. Each now lists it as left in place with its reason (`already_a_pointer` or `pointer_with_changes`); the guard explains instead of offering to connect it, and a repository whose only instruction files hold pointer text gets no setup offer. A link to such a file elsewhere in the repository (for example `GEMINI.md` -> `docs/orphan.md`) is reported the same way, and an edit through the link or to its target is explained; links leaving the repository are never followed. A link to a pointer SuperCtx already tracks (for example `GEMINI.md` -> `CLAUDE.md`) is listed as `links_to_tracked_pointer`, while the tracked pointer keeps its normal hub redirect or repair message. Real instruction files keep the normal suggestion, and file contents and manifest metadata are unchanged. (#109)

## [0.2.5] - 2026-11-10

### Fixed
- The edit guard no longer says the generated shims are broken or missing when the only finding is tool configuration that an earlier version replaced with a pointer (`tool_config_adopted`). Sync cannot repair that, and the pointers are intact, so an edit of a pointer such as `CLAUDE.md` is steered to `.ctx/SUPERCTX.md` as usual. A missing or edited pointer still gets the repair message, and the replaced configuration stays writable so it can be restored. (#104)
- The session-start hook no longer reports broken or missing shims, or offers a repair, when the only finding is tool configuration that an earlier version replaced with a pointer. It names each replaced path, says SuperCtx does not restore it automatically, and gives the recovery steps to offer. When shims really are broken as well, it keeps the repair offer and adds the replaced paths, noting that the repair will not restore them. (#105)

## [0.2.4] - 2026-11-10

### Fixed
- The internal `_detect` entry point used by the session-start hook reports a tool, rule, skill, or planning folder it cannot read (for example `.grok` with mode `000`) as JSON with state `unreadable`, reason `tool_folder_unreadable`, and the folder, and exits 1, instead of printing a Python traceback or a partial result. It writes nothing; the session-start hook stays silent in this state, as before. (#101)
- The edit guard keeps steering edits of a pointer such as `CLAUDE.md` to `.ctx/SUPERCTX.md` while an unrelated folder (for example `.cursor` with mode `000`) cannot be read. Before, it let the edit through, or asked to repair shims that were not broken. (#100)
- A missing or edited pointer is still reported as needing repair while a folder cannot be read: an unreadable folder now leaves only candidate discovery incomplete, instead of stopping the pointer and link checks, including when the folder holds another pointer such as `.claude/CLAUDE.md`. (#100)
- Tool configuration an earlier version replaced with a pointer stays writable while a folder cannot be read, so it can be restored, including through links from readable tool folders. (#100)
- If the edit guard cannot check the repository's state, it now blocks edits to the pointers listed in the manifest and says that verification failed, instead of letting them through. It does not claim the pointers are healthy or broken. The hub, other files, and tool configuration identified as replaced by an earlier version stay writable. (#102)
- A SuperCtx folder that cannot be read (for example `.ctx/sources` or `.ctx/skills` with mode `000` or `300`) no longer makes sync stop with a Python traceback, or lets `add` write into it. Sync, `add`, and the internal `_detect` entry point report `ctx_unreadable` with the folder, exit 1, and change nothing; the session-start hook stays silent. (#102)

## [0.2.3] - 2026-11-09

### Fixed
- Sync now reports tool configuration that a version before 0.2.2 replaced with a pointer, instead of calling the repository healthy. A tracked pointer inside a tool's own folder, or one reached from such a folder through links to files or folders, is listed as `tool_config_adopted` with the recovery steps, and sync exits 1. Link cycles, broken links, and links leaving the repository are skipped. If a folder a tool reaches cannot be read, detection is incomplete, so `add` and sync change nothing and report `tool_folder_unreadable`. Sync never rewrites, re-creates, or refreshes such a file, and the edit guard lets it be written so the original can be restored. Registered instruction files, rules, and skills are unaffected. (#97)
- `add` also refuses a file that a tool's own folder links to, directly or through a linked folder (for example `add configs/grok.toml` when `.grok/config.toml` links to it), since replacing it would break that tool's configuration. (#97)
- A tool, rule, skill, or planning folder that cannot be read (for example `.grok` with mode `000`) no longer makes `add` or sync stop with a Python traceback. Both check these folders before writing anything, report `tool_folder_unreadable` with the folder, exit 1, and change nothing; first-time setup does not create `.ctx/`. (#98)

## [0.2.2] - 2026-11-06

### Fixed
- `add` no longer replaces a file inside a tool's own folder with a pointer. Files such as `.grok/config.toml`, `.claude/settings.json`, `.agents/hooks.json`, or `.github/workflows/ci.yml` were backed up, imported into the hub, and overwritten, which broke that tool's configuration. They are now refused with `tool_folder` and nothing changes, whether the path given or the file a link resolves to is inside the tool folder; this includes unrecognized notes such as `.claude/notes.md`. Registered instruction files (`.claude/CLAUDE.md`, `.github/copilot-instructions.md`, `.codex/AGENTS.md`) and supported rules and skills are added as before. (#95)
  Upgrading does not repair a file an earlier version already replaced: sync still reports it as healthy. To recover one, copy the original back from `.ctx/sources/<same path>`, delete that path's `[[natives]]` entry from `.ctx/superctx.toml`, and delete its `## From: <path>` section from `.ctx/SUPERCTX.md`. Sync then reports the repository as healthy and leaves the file alone. Restoring the file without removing the entry stops sync from overwriting it, but every sync reports it as `native_edited`.
- Sync no longer suggests the `.agents/skills` folder itself as an untracked candidate. The suggestion came from an older Antigravity list, and adding that folder is refused because `.agents/` is a tool's own folder; the skills inside it are still suggested and connected one by one. (#93)
- Sync no longer suggests `.agents/hooks.json` or the `.agents/hooks` folder. Hooks are outside SuperCtx's scope and `add` refuses both, so the suggestions could not be acted on; the files are left untouched. (#94)

## [0.2.1] - 2026-11-06

### Added
- OpenAI Codex skills (`.agents/skills/`) are adopted like the other tools' skills: moved into the shared `.ctx/skills/` and linked back. Verified with Codex CLI 0.167.0, including its `AGENTS.md` pointer and writes through a connected `.planning` folder. Codex does not read `.claude/skills/`. In a repository already set up with 0.2.0, existing `.agents/skills/` skills are listed as candidates to connect with `/superctx:add`. (#89)

### Changed
- Grok Build is listed as a reader of the root `CLAUDE.md` and `AGENTS.md`, citing Grok's project-rules documentation, verified with Grok Build 1.0.70. Tool lists are written during setup or adoption, so manifests created before 0.2.1 keep their stored lists. (#90)
- Cursor is no longer listed as a reader of `.agents/skills/`, which has not been verified for Cursor. (#89)

### Fixed
- The opt-in real-tool skill checks for OpenAI Codex and Grok Build (`.grok/skills/`) now require the bundled script to run: its token appears only in the script's output, so quoting the script can no longer pass. (#89, #91)

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
