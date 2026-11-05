# SuperCtx v0.2 Manifest and Resource Ownership

**Status**: Accepted for v0.2
**Date**: 2026-11-02

## Context

v0.1 records only instruction files (`[[files]]` in `.ctx/manifest.toml`), all of them generated shims pointing to `.ctx/SUPERCTX.md`. v0.2 adds rules, complete skills, and explicitly adopted reference or planning folders. Each needs an owner (the canonical copy under `.ctx/`) and one or more native paths where tools look for it, published in a way that tool supports.

Released v0.1.x clients must not modify a v0.2 workspace. The migration-safety gate (`tests/test_v2_migration_safety.py`) runs the released v0.1.4 client against v0.2 workspaces and requires that it refuses without changing any file.

## Files

| Path | Role |
|------|------|
| `.ctx/superctx.toml` | v2 manifest (this document) |
| `.ctx/manifest.toml` | compatibility sentinel; never a v2 manifest |
| `.ctx/manifest.v1.toml` | v1 manifest copied at migration, for recovery |
| `.ctx/sources/<native path>` | original content of an adopted native path (inactive backup) |
| `.ctx/rules/`, `.ctx/cursor-rules/`, `.ctx/skills/` | canonical rules (Claude Code, Cursor) and skills, linked from their native paths (created only when one is adopted) |

The sentinel is valid TOML whose `files` key is a string. Every 0.1.x loader requires an array there, raises `SchemaError`, and takes its no-write branch. Its `migration` key is `"in-progress"` or `"complete"`.

## Schema

```toml
schema = 2

[project]
name = "my-repo"

[[resources]]
id = "instructions"            # unique; [a-z0-9][a-z0-9._-]*
type = "instructions"          # instructions | rule | skill | reference | planning
canonical = ".ctx/SUPERCTX.md" # under .ctx/, outside .ctx/sources/, not a manifest file

[[natives]]
resource = "instructions"      # id of the owning resource
path = "CLAUDE.md"             # repo-relative, outside .ctx/
mode = "pointer"               # pointer | link | generated
tools = ["Claude Code"]
backup = true                  # original content is at .ctx/sources/<path>
# published = false            # only while initial publication is pending (see Adoption)
note = "..."                   # optional
# published_hash = "sha256:<64 hex>"  # required for generated, forbidden otherwise
```

Validation rejects unknown keys, so a newer schema is refused rather than rewritten with fields dropped. It also rejects duplicate resource ids, duplicate canonical paths, a native path that equals or contains another native path, natives that reference unknown resources, and paths that are absolute or escape the repository. Exactly one `instructions` resource exists, its canonical path is `.ctx/SUPERCTX.md`, and its natives use `pointer` mode.

Mode is recorded per native path, not per resource: one skill may be linked into one tool's directory and published as a generated copy into another's.

## Publication modes

| | **pointer** | **link** | **generated** |
|---|---|---|---|
| Native path holds | a small generated file directing readers to the canonical resource | a relative symlink to the canonical resource, resolving inside the repository | a copy of the canonical resource |
| Adoption | back up the original to `.ctx/sources/`, import its content into the canonical resource, write the pointer | back up the original to `.ctx/sources/`, move its content to the canonical path, create the link | back up the original to `.ctx/sources/`, move its content to the canonical path, write the copy, record `published_hash` |
| Canonical edit | nothing to publish; readers follow the pointer | visible through the link immediately | sync republishes when the native still matches `published_hash`, then records the new hash |
| Native edit | the native is no longer a valid pointer: **conflict** | edits through the link change the canonical resource (intended); replacing or retargeting the link is a **conflict** | native differs from `published_hash`: **conflict** |
| Native deleted | sync recreates the pointer | sync recreates the link | sync republishes the copy |
| Canonical deleted | **conflict**; never rebuilt from natives | **conflict** (dangling link); the link is left in place | **conflict**; the copy is left in place |

SuperCtx never writes through a symlink it did not create. Commands refuse to write while `.ctx/` itself, the hub, `.ctx/sources/` or its README, `.ctx/.gitignore`, or a manifest file is a symlink. A pointer native whose path or backup path passes through any symlink is reported as `unsafe_path` and left unchanged, because the link could redirect the write into `.ctx/`, outside the repository, or onto an unrelated file. Migration checks that every manifest path it replaces is absent or a regular file before its first write.

A conflict is reported and changes nothing: sync never overwrites a native with unexpected content and never rewrites a canonical resource from a native one. Generated pointer content is disposable; a native's original content is never discarded, because adoption backs it up first.

A pointer counts as unedited only when it matches, byte for byte (line endings aside), a rendering SuperCtx produces for that path: the current one, or the v0.1.2–v0.1.4 one, which sync refreshes to the current wording. Searching for the generated marker is not enough, because a pointer with lines added keeps the marker. Sync rewrites a pointer only when it is missing, or, while its initial publication is pending, when the file still holds exactly its backed-up original. Any other content at a pointer path stays where it is and is reported as `native_edited`, whether or not a backup exists. That includes the original content restored on purpose after setup.

## Adoption

SuperCtx adopts a resource when it can preserve how the tool uses it: an instruction file gets a pointer to the hub, and a rule or skill whose tool has been verified through a link (`publish = "link"` in `conventions.toml`) gets a relative symlink at its native path. Canonical paths keep the native path's depth (`.claude/skills/review` → `.ctx/skills/review`), so relative references inside a resource resolve to the same place through the link or the target. The verified tools and versions are listed in `architecture/compatibility.md`.

Running `/superctx:sync` in a repository without `.ctx/` is the decision to set up shared context, and sync does it in one step:

1. Discover instruction files, rules, and skills. Check each for conflicts.
2. Build the new `.ctx/` (backups, hub, manifest, sentinel) in a staging directory inside the repository, then install it with one rename. A failure up to this point leaves the repository unchanged; a staging directory left by a crash is removed by the next run.
3. Publish each native: write the pointer, or move the rule or skill to its canonical path and create the link.

Setup and `add` record each new native with `published = false`, publish it, and then record it as published. Every publish step can be repeated, so a sync after an interruption finishes the job and records it. The flag is what lets sync tell finishing an adoption from inspecting something it already published: only an unpublished native may have its original bytes replaced by a pointer, or be moved into `.ctx/`, and only while it is identical to the backup setup took (same paths, bytes, and executable bits); anything changed since stays in place as `native_edited`. Natives migrated from v0.1.x are published. A linked native is in one of these states:

| State | Native path | Canonical path | Sync |
|---|---|---|---|
| healthy | symlink to the canonical path | present | — |
| missing | absent | present | create the link |
| pending (unpublished only) | the original, identical to its backup | absent | move it, then create the link |
| `native_edited` (unpublished only) | differs from its backup, or no backup | absent | report |
| `link_retargeted` | symlink elsewhere | any | report |
| `native_replaced` | a real file or folder | present | report |
| `canonical_missing` | absent, a symlink, or (once published) a real file or folder | absent | report |

Rules are never converted between tools. Claude Code scopes a rule with `paths:` in a `.md` file and Cursor with `globs:` or `alwaysApply` in a `.mdc` file, and some Cursor rule types have no Claude Code equivalent. So each tool's rules keep their own canonical folder (`.ctx/rules/`, `.ctx/cursor-rules/`) and their own id prefix (`rule-`, `cursor-rule-`), and are linked byte for byte, so activation conditions, directory scope, and metadata are unchanged. Canonical paths keep the native depth, so a relative reference that leaves the rules folder (`../../docs/guide.md`) reaches the same file from either path. A reference to a file beside the rule (`[guide](guide.md)`, `@guide.md`) would not resolve from `.ctx/`, so such a rule is left in place (`breaks_reference`). The check does not rely on one Markdown grammar, because parsers disagree on details. After every place a destination can start (`](`, `]:`, `href=`/`src=`, `@`, `<`), it considers each prefix of the rest of the line that ends where a destination can end, read as written, decoded as CommonMark does, decoded as HTML, and with backslash escapes removed, each with and without percent-decoding and any `?query` or `#fragment`. If any of those names an existing file that would not resolve from `.ctx/`, the rule stays in place. Separately, when SuperCtx recognizes a link, reference definition, or HTML attribute but cannot parse its complete destination, it also leaves the rule in place (`unclear_reference`): uncertainty preserves the native rule. A rule that should apply in both tools still exists once per tool.

In an existing workspace, newly discovered resources are listed as candidates and adopted with `/superctx:add <path>`. Resources that cannot be adopted stay where they are, and every sync reports why: `not_verified` (no verified link behavior for the tool), `already_a_symlink`, `contains_symlink` (a link inside a skill could break when it moves), `no_skill_md`, `breaks_reference` (a rule links to a file beside it that would not resolve from its canonical path), `unclear_reference` (a rule has a link or import whose destination cannot be determined), `name_collision` (two resources would share a name or canonical path), `canonical_exists`, `backup_exists`, or `unsafe_path`.

## Migration

Sync migrates a v1 workspace before doing anything else. The write order is:

1. copy `.ctx/manifest.toml` to `.ctx/manifest.v1.toml`
2. replace `.ctx/manifest.toml` with the sentinel, `migration = "in-progress"`
3. write `.ctx/superctx.toml`
4. replace the sentinel with `migration = "complete"`

Each step is an atomic replace from a temporary file created exclusively in `.ctx/`, so nothing already at a temporary path (such as a symlink) is followed. Before step 2 the workspace is still a plain v1 workspace. From step 2 on, every 0.1.x client refuses it.

`locate()` classifies the workspace from these files:

| `.ctx/superctx.toml` | `.ctx/manifest.toml` | State | Sync |
|---|---|---|---|
| absent | absent, `.ctx/` empty or missing | not set up | set up |
| absent | absent, other `.ctx/` content survives | `orphaned` | **refuse** to set up over it |
| absent | v1 manifest | `v1` | migrate |
| absent | sentinel, in progress, v1 copy present | `interrupted` | resume from the v1 copy |
| absent | sentinel, complete (or in progress without a v1 copy) | `lost` | **refuse** and report |
| present | sentinel, complete | `v2` | — |
| present | absent, or sentinel in progress | `v2_unsealed` | write the complete sentinel |
| present | anything else | `conflict` | **refuse** and report |

Only an interrupted upgrade is rebuilt from the v1 copy. Once migration completes, the v2 manifest can hold resources the v1 copy knows nothing about, so rebuilding a lost v2 manifest from it would silently drop their ownership records. A lost manifest must be restored from version control.

New workspaces are created directly as v2: `.ctx/superctx.toml`, then the complete sentinel.
