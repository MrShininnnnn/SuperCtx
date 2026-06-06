# Privacy Policy

Last updated: June 6, 2026

SuperCtx is a Claude Code plugin that helps keep AI coding-assistant instruction files aligned through a shared, project-local context hub.

## Overview

SuperCtx runs locally in the user's Claude Code environment and project repository. SuperCtx does not operate a remote backend, analytics service, telemetry service, advertising system, or user-tracking system.

SuperCtx does not independently collect, transmit, sell, rent, or share personal data with the maintainer or maintainer-controlled services.

## Project Files SuperCtx Accesses

When the user or Claude Code agent uses SuperCtx, the plugin may read or write project-local files, including:

- `.ctx/SUPERCTX.md`
- `.ctx/manifest.toml`
- `.ctx/sources/`
- `.claude/CLAUDE.md`
- `.codex/AGENTS.md`
- `AGENTS.md`
- `CLAUDE.md`
- `GEMINI.md`
- other instruction files selected by the user or agent

SuperCtx uses these files to create and maintain the shared context hub, inactive backups, and generated instruction-file shims.

## Local Storage and Backups

SuperCtx stores its project context and configuration locally in the user's repository. Before replacing an existing instruction file with a generated shim, SuperCtx may create an inactive backup under `.ctx/sources/`.

SuperCtx does not store project files or user data outside the local repository. The `.ctx/sources/` directory is ignored by SuperCtx's generated `.ctx/.gitignore`, but users should review repository state before committing or sharing files.

## Network Activity

The SuperCtx runtime does not independently upload project files, prompts, telemetry, analytics, or personal data to the maintainer or to a SuperCtx-operated service. SuperCtx does not include a remote backend.

Installing or updating the plugin, opening documentation links, or using Git, GitHub, Claude Code, Codex, Gemini CLI, or other tools may involve network activity provided by those tools or services. Their own terms and privacy policies apply.

## Claude Code and Anthropic Services

SuperCtx runs inside Claude Code. When Claude Code reads files, displays tool output, or acts on user prompts, Anthropic may process that interaction according to Anthropic's terms, privacy policy, account settings, and Claude Code configuration.

SuperCtx does not control Anthropic's data handling, model-training settings, account settings, or Claude Code telemetry.

## User Control

Users control whether to install, enable, use, update, or remove SuperCtx. SuperCtx asks for explicit consent before agent-guided setup, connection, repair, or migration actions that modify protected instruction files.

Users can inspect all SuperCtx-created files in their repository. Before removing SuperCtx-created context files or shims, users should review `.ctx/SUPERCTX.md`, `.ctx/manifest.toml`, and backups under `.ctx/sources/` so important project instructions are not lost.

## Data Retention and Sharing

SuperCtx does not retain data outside the user's local project.

Files created or modified by SuperCtx remain in the local repository until the user or another tool edits, deletes, commits, pushes, or otherwise shares them. If users share the repository through Git, GitHub, or another service, those services may process the shared files according to their own privacy policies.

## Security

SuperCtx is designed to avoid silent mutation of protected instruction files. It uses consent-based setup and write-guard behavior before centralizing or rewriting instruction files.

Users should avoid placing secrets, API keys, credentials, or sensitive personal data in project instruction files.

For security vulnerabilities, follow the reporting instructions in [SECURITY.md](SECURITY.md).

## Contact

For privacy questions or other issues, use the [SuperCtx GitHub issue tracker](https://github.com/MrShininnnnn/SuperCtx/issues).
