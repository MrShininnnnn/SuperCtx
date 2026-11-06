# Tool Compatibility

Which tools SuperCtx adopts resources for, and how each was verified, as of SuperCtx 0.2.1. A resource type is adopted only when its row is **supported**; everything else is discovered and left in place with a reason.

| Tool | Resource | Native path | Published as | Result | Verified with | Date |
|---|---|---|---|---|---|---|
| Claude Code | instructions | `CLAUDE.md`, `.claude/CLAUDE.md` | pointer (`@` import) | supported | v0.1 behavior | 2026-05-29 |
| Claude Code | rule | `.claude/rules/**/*.md` | relative file symlink | supported | Claude Code 2.1.200, macOS 26 | 2026-11-05 |
| Claude Code | skill | `.claude/skills/<name>/` | relative directory symlink | supported | Claude Code 2.1.200, macOS 26 | 2026-11-05 |
| Cursor | rule | `.cursor/rules/**/*.mdc` | relative file symlink | supported | Cursor Agent CLI 2026.11.05-86047df (`grok-4.7-medium`), macOS 26 | 2026-11-05 |
| Cursor | skill | `.cursor/skills/<name>/` | relative directory symlink | supported | Cursor Agent CLI 2026.11.05-86047df (`grok-4.7-medium`), macOS 26 | 2026-11-05 |
| Cursor | skill (reused) | `.claude/skills/<name>/` | the Claude Code link | supported | Cursor Agent CLI 2026.11.05-86047df (`grok-4.7-medium`), macOS 26 | 2026-11-05 |
| Grok Build | instructions (reused) | `CLAUDE.md`, `AGENTS.md` | the existing pointers | supported | Grok Build 1.0.70 (`grok-4.7`), macOS 26 | 2026-11-05 |
| Grok Build | skill | `.grok/skills/<name>/` | relative directory symlink | supported | Grok Build 1.0.70 (`grok-4.7`), macOS 26 | 2026-11-05 |
| Grok Build | skill (reused) | `.claude/skills/<name>/` | the Claude Code link | supported | Grok Build 1.0.70 (`grok-4.7`), macOS 26 | 2026-11-05 |
| Grok Build | rule (reused) | `.claude/rules/**/*.md` | the Claude Code link | limited: `paths` scope ignored | Grok Build 1.0.70 (`grok-4.7`), macOS 26 | 2026-11-05 |
| OpenAI Codex | instructions (reused) | `AGENTS.md` | the existing pointer | supported | Codex CLI 0.167.0 (`gpt-6-luna`), macOS 26 | 2026-11-05 |
| OpenAI Codex | skill | `.agents/skills/<name>/` | relative directory symlink | supported | Codex CLI 0.167.0 (`gpt-6-luna`), macOS 26 | 2026-11-05 |
| OpenAI Codex | skill (Claude Code folder) | `.claude/skills/<name>/` | — | not read: Codex scans only `.agents/skills/` | Codex CLI 0.167.0 (`gpt-6-luna`), macOS 26 | 2026-11-05 |
| Claude Code | planning folder (write) | `.planning/`, or any folder added | relative directory symlink | supported | Claude Code 2.1.200 (`haiku`), macOS 26 | 2026-11-05 |
| Cursor | planning folder (write) | `.planning/`, or any folder added | relative directory symlink | supported | Cursor Agent CLI 2026.11.05-86047df (`grok-4.7-medium`), macOS 26 | 2026-11-05 |
| OpenAI Codex | planning folder (write) | `.planning/`, or any folder added | relative directory symlink | supported | Codex CLI 0.167.0 (`gpt-6-luna`), macOS 26 | 2026-11-05 |
| Grok Build | planning folder (write) | `.planning/`, or any folder added | relative directory symlink | supported | Grok Build 1.0.70 (`grok-4.7`), macOS 26 | 2026-11-05 |
| Claude Code | reference folder (read) | any folder added | relative directory symlink | supported | Claude Code 2.1.200 (`haiku`), macOS 26 | 2026-11-05 |

Instruction files for other tools (`AGENTS.md` for the tools besides Codex and Grok Build that read it, `GEMINI.md` for Gemini CLI, `.github/copilot-instructions.md` for GitHub Copilot, `.codex/AGENTS.md`) are published as pointers to `.ctx/SUPERCTX.md`, as in v0.1. Their paths are cited in `scripts/superctx/conventions.toml`; those tools were not re-run against v0.2.

"Reused" rows add no files: the tool reads another tool's native path, so the resource SuperCtx already published there serves both.

## How a row is verified

`tests/test_real_agents.py` (opt-in: `SUPERCTX_REAL_AGENTS=1`) sets up a repository with the real `superctx sync`, so resources reach the tool through the links SuperCtx publishes, then runs the tool non-interactively (Claude Code with project settings only):

- **Skill:** invoking `/review` runs the skill's bundled `scripts/run.sh` (executable bit preserved) and reads its bundled `references/guide.md`; both tokens appear in the answer.
- **Scoped rule, active:** a rule with `paths: ["src/**/*.py"]` supplies its codeword after Claude reads `src/app.py`.
- **Scoped rule, inactive:** the same rule supplies nothing after Claude reads `docs/notes.md`.
- **Cursor scoped rule:** the same two checks with a `.mdc` rule scoped by `globs: src/**/*.py`, run with `cursor-agent` in read-only ask mode. As a control, the same rule saved as `.md` (which Cursor ignores) supplied nothing for `src/app.py`.
- **Cursor skill:** in ask mode (which cannot run commands), asking for the skill by name, without searching the filesystem, returns the codeword from its bundled reference and the text of its bundled script, for a skill linked from `.cursor/skills/` and one linked from `.claude/skills/`. Control: the same package in a folder Cursor does not scan for skills is reported unavailable.
- **Grok Build:** runs use `GROK_FOLDER_TRUST=0` (trust for that run only; nothing is written to Grok's trust store) and turn off the user's Claude and Cursor hooks and MCP servers. Read-only questions run in plan mode; skill runs allow only `bash …/scripts/run.sh` and reads inside the repository.
  - **Instructions:** `grok inspect --json` lists the `CLAUDE.md` and `AGENTS.md` pointers as instruction sources and never `.ctx/SUPERCTX.md`, so the hub is not loaded twice: Grok does not follow `@` imports, and the model reads the hub when a pointer directs it. A session then answers codewords that exist only in the hub (imported from both original files).
  - **Skill:** `grok inspect --json` finds the skill at its linked path, and invoking it by name runs its bundled script and reads its bundled reference, for a skill linked from `.grok/skills/` and one linked from `.claude/skills/`.
  - **Claude rule:** the rule applies after reading `src/app.py`, but also after reading `docs/notes.md`: Grok ignores `paths`, with or without SuperCtx. The test asserts this, so it fails if Grok starts honoring the scope.

The same checks were run first on native (unlinked) folders to confirm they distinguish the cases.

- **OpenAI Codex:** runs use `codex exec --ephemeral --ignore-user-config` (the user's `config.toml` is not loaded and no session is saved), in the read-only sandbox, or workspace-write for the planning check.
  - **Skill:** asked to list its skills without running commands, Codex names the skill linked from `.agents/skills/` and not the ones in `.claude/skills/`, `.cursor/skills/`, `.grok/skills/`, or the control folder; invoked by name, it runs the bundled script and reads the bundled reference through the link. Discovery was checked first with an unlinked skill in `.agents/skills/`.
  - **Instructions:** a session answers codewords that exist only in the hub, read by following the `AGENTS.md` pointer.

- **Planning folder:** `.planning/` is connected with the real `superctx add`, and each tool is asked to append its own line to `.planning/<plan>/progress.md` through the original path with its ordinary file tools (Cursor in its default agent mode; Grok with edits allowed only inside the test repository). The canonical `.ctx/planning/<plan>/progress.md` gains the line and `.planning` is still a link afterwards. A writer that replaced the link would fail the check and stay unmanaged.
- **Reference folder:** `docs/architecture/` is connected the same way and Claude reads a document through its original path. Non-agent readers are covered by unit tests: a link in another document, a script reading a file, and the folder's own relative references all resolve through the original path.

Real tools occasionally answer wrongly: Claude Code (`haiku`) once answered `NONE` for the active scoped rule and passed on three reruns. Re-run a failing check before treating it as a regression.

Re-run the checks when a tool's version changes, and add a row (with `publish = "link"` and `verified_behavior` in `scripts/superctx/conventions.toml`) only after they pass.

## Outside v0.2

SuperCtx 0.2 manages root instructions, rules, complete skills, and reference or planning folders connected with `/superctx:add`. It does not discover, move, or link commands, subagent definitions, hooks, MCP configuration, local settings, plugins, or any other tool configuration, and no folder or other file inside a tool's own folder (`.claude/`, `.cursor/`, `.grok/`, `.codex/`, `.gemini/`, `.github/`, `.agents/`) can be connected, apart from registered instruction files, rules, and skills. It does not coordinate tasks between tools or synchronize arbitrary directories.
