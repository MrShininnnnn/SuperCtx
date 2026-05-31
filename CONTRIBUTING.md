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

Use them for local agent setup, workflow notes, and private planning. Public-facing documentation belongs in tracked root files such as `README.md`, `CONTRIBUTING.md`, and `MARKETPLACE_READINESS.md`.

## Pull Requests

Before opening a PR:

1. Keep the change focused on one outcome.
2. Add or update tests when behavior changes.
3. Run `python -m pytest tests/ -v`.
4. Update README or public docs when user-facing behavior changes.
5. Confirm local-only files are not staged.

For skill-related changes, keep the skill aligned with SuperCtx's core purpose: synchronizing project context across AI coding tools.
