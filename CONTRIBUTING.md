# Contributing to SuperCtx

Thanks for helping improve SuperCtx.

SuperCtx is early software. Keep changes focused, reviewable, and tied to the goal of project-context synchronization across AI coding tools.

## Before You Start

Open an issue before working on:

- new generated file conventions
- new tool adapters
- changes to `.ctx/` structure
- marketplace packaging changes
- large README or public messaging rewrites

Small fixes, documentation corrections, tests, and narrowly scoped bug fixes can go straight to a pull request.

## Local Setup

SuperCtx requires Python 3.11 or newer.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test]'
```

## Running Tests

Run the full test suite before opening a pull request:

```bash
python -m pytest tests/ -v
```

When changing generated output, update or add snapshot coverage so reviewers can see exactly what changed.

## Local-Only Files

These paths are intentionally local-only and should not be committed:

```text
.claude/
.codex/
.agy/
docs/
```

Use them for local agent setup, workflow notes, and private planning. Public-facing documentation belongs in tracked root files such as `README.md`, `CONTRIBUTING.md`, `SECURITY.md`, and `CHANGELOG.md`.

## Pull Requests

Before opening a PR:

1. Keep the change focused on one outcome.
2. Add or update tests when behavior changes.
3. Run `python -m pytest tests/ -v`.
4. Update README or public docs when user-facing behavior changes.
5. Confirm local-only files are not staged.

For skill-related changes, keep the skill aligned with SuperCtx's core purpose: synchronizing project context across AI coding tools.

## Release Checklist

**Version bump rule**: Any change to skill names, command discovery, hooks, plugin metadata, or user-visible command behavior requires a plugin version bump.

Examples that require a version bump:
- renaming `/superctx:using-superctx` to `/using-superctx`
- adding or removing a skill folder
- changing skill frontmatter `name`
- changing hook behavior
- changing `hooks/hooks.json`
- changing slash-command output behavior
- changing plugin metadata
- changing README command-discovery promises

Before releasing a new version of SuperCtx:

1. **Bump Version Surfaces**: Ensure the new version string matches exactly across:
   - `pyproject.toml` (`version` field)
   - `.claude-plugin/plugin.json` (`version` field)
   - `.claude-plugin/marketplace.json` (`version` field inside `plugins`)
   - `scripts/superctx/__init__.py` (`__version__` constant)
2. **Update Changelog**: Document the release date and all added, changed, deprecated, removed, fixed, or security-patched features in `CHANGELOG.md`.
3. **Verify Code Quality**:
   - Run the full test suite: `python -m pytest tests/ -v`
   - Run the status CLI diagnostics and check path sanitization: `python -m superctx status`
4. **Clean Workspace**: Confirm that no local-only files (e.g. `.claude/`, `.codex/`, `.agy/`, `docs/`) are staged or committed.
5. **Release & Test**:
   - Create a corresponding git tag and push to GitHub.
   - Run `/plugin update superctx` and verify the active version is reported correctly.
