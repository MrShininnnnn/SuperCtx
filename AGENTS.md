# SuperCtx Agent Instructions

SuperCtx is a Python project for synchronizing AI coding tool context into a project-local `.ctx/` hub.

## Development Commands

- Run tests with `python -m pytest tests/ -v`.
- Run the CLI locally with `python -m superctx <init|sync|status>`.
- Keep the implementation dependency-light and deterministic.

## Project Rules

- The current MVP is inward synchronization from tool instruction files into `.ctx/`.
- Do not add outward generation of `.claude/`, Codex, Gemini, or AGY files as part of MVP verification.
- Keep local-only folders such as `.claude/`, `.codex/`, `.agy/`, and `docs/` out of Git.
