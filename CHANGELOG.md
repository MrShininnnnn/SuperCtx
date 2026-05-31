# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed
- Renamed the plugin skill command from `/superctx:setup` to `/superctx:init` to align with Claude Code command vocabulary and avoid confusion with Claude Code built-in `/init`.
- Renamed `skills/setup/` folder to `skills/init/` to match the new command name.
- Updated skill `name:` frontmatter fields to explicitly namespaced values (`superctx:init`, `superctx:sync`, `superctx:status`) to ensure Claude Code registers commands under the `superctx:` prefix.
- Updated README, MARKETPLACE_READINESS.md, and all skill text to use `/superctx:init` consistently.
- Added "Command Discovery and Namespace Safety" section to README with smoke test instructions.

## [0.1.1] - 2026-05-31

### Added
- Added active version and stale-cache diagnostics to the `/superctx:status` command.
- Integrated update/reinstall/troubleshooting guidance for stale cached plugins.
- Added version resolution support tracking environment (`CLAUDE_PLUGIN_ROOT`), parent-walk directories, and fallback package version.
- Added test coverage for all three version resolution cases.
- Created `CHANGELOG.md` and added a release checklist to `CONTRIBUTING.md`.

### Changed
- Bumped version to `0.1.1` across plugin manifests, marketplace descriptors, and Python engine.
