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

SuperCtx never writes through a symlink it did not create. Commands refuse to write while `.ctx/` itself, the hub, `.ctx/sources/` or its README, `.ctx/.gitignore`, or a manifest file is a symlink. A native or backup path that resolves outside the repository, into `.ctx/`, or (for backups) outside `.ctx/sources/` is reported as `unsafe_path`.

A conflict is reported and changes nothing: sync never overwrites a native with unexpected content and never rewrites a canonical resource from a native one. Generated pointer content is disposable; a native's original content is never discarded, because adoption backs it up first.

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
