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

## GitHub & PR Workflow Guidelines

When working on issues or creating pull requests, agents must follow these steps:

1. **Address All PR Review Comments**:
   - Always read and reply to all individual review comments left on the PR.
   - Summarize the fixes made for each comment and submit the replies on GitHub.
2. **Link PRs to Issues**:
   - Ensure the PR relates to its corresponding issue so that the issue is automatically closed when merged.
   - Prepend `Closes #<IssueNumber>` or `Resolves #<IssueNumber>` in the PR description body.
3. **Engage in Issue Threads**:
   - Reply to any questions, needs, or open comments inside the GitHub issue thread itself if there is outstanding feedback or if clarification is needed.
4. **Pre-Push Quality Verification**:
   - Run `git diff --check` to ensure no trailing whitespace is introduced before push or PR creation.
   - Ensure tests pass locally with `python -m pytest tests/ -v`.
   - Run `claude plugin validate .` to verify marketplace plugin manifests.
