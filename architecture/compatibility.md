# Tool Compatibility

Which tools SuperCtx adopts resources for, and how each was verified. A resource type is adopted only when its row is **supported**; everything else is discovered and left in place with a reason.

| Tool | Resource | Native path | Published as | Result | Verified with | Date |
|---|---|---|---|---|---|---|
| Claude Code | instructions | `CLAUDE.md`, `.claude/CLAUDE.md` | pointer (`@` import) | supported | v0.1 behavior | 2026-05-29 |
| Claude Code | rule | `.claude/rules/**/*.md` | relative file symlink | supported | Claude Code 2.1.200, macOS 26 | 2026-11-02 |
| Claude Code | skill | `.claude/skills/<name>/` | relative directory symlink | supported | Claude Code 2.1.200, macOS 26 | 2026-11-02 |
| Cursor | rule | `.cursor/rules/**/*.mdc` | — | unsupported (not verified) | Cursor not available | 2026-11-02 |

## How a row is verified

`tests/test_real_agents.py` (opt-in: `SUPERCTX_REAL_AGENTS=1`) sets up a repository with the real `superctx sync`, so resources reach the tool through the links SuperCtx publishes, then runs the tool non-interactively with project settings only:

- **Skill:** invoking `/review` runs the skill's bundled `scripts/run.sh` (executable bit preserved) and reads its bundled `references/guide.md`; both tokens appear in the answer.
- **Scoped rule, active:** a rule with `paths: ["src/**/*.py"]` supplies its codeword after Claude reads `src/app.py`.
- **Scoped rule, inactive:** the same rule supplies nothing after Claude reads `docs/notes.md`.

The same checks were run first on native (unlinked) folders to confirm they distinguish the cases.

Re-run the checks when a tool's version changes, and add a row (with `publish = "link"` and `verified_behavior` in `scripts/superctx/conventions.toml`) only after they pass.
