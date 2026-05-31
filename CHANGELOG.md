# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.1] - 2026-05-31

### Added
- Added active version and stale-cache diagnostics to the `/superctx:status` command.
- Integrated update/reinstall/troubleshooting guidance for stale cached plugins.
- Added version resolution support tracking environment (`CLAUDE_PLUGIN_ROOT`), parent-walk directories, and fallback package version.
- Added test coverage for all three version resolution cases.
- Created `CHANGELOG.md` and added a release checklist to `CONTRIBUTING.md`.

### Changed
- Bumped version to `0.1.1` across plugin manifests, marketplace descriptors, and Python engine.
