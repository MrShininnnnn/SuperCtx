"""CLI entry point: `python3 -m superctx <init|sync|status> [project_dir]`.

Skills invoke this with PYTHONPATH pointing at the plugin's scripts/ directory. The default
project_dir is the current working directory (the user's project).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import init as init_cmd
from . import status as status_cmd
from . import sync as sync_cmd
from . import add as add_cmd


def _cmd_init(project_dir: Path) -> int:
    result = init_cmd.run(project_dir)
    if not result["created"]:
        if result.get("partially_migrated"):
            print("SuperCtx: This project is partially migrated.")
            print("The following shims are missing or broken:")
            for shim in result["broken_shims"]:
                print(f"  ! {shim}")
            print()
            return 0
        else:
            print("SuperCtx: Already initialized.")
            return 0

    print("SuperCtx initialized this repo.")
    print()

    connected = result.get("connected", [])
    if connected:
        print("Connected:")
        for file in connected:
            print(f"- {file}")
        print()

    hub = result.get("hub")
    if hub:
        print("Hub:")
        print(f"- {hub}")
        print()

    backups = result.get("backups", [])
    if backups:
        print("Backups:")
        for backup in backups:
            print(f"- {backup}")
        print()

    failed_shims = result.get("failed_shims", [])
    if failed_shims:
        print("WARNING: Some shims could not be applied due to pre-existing backups:")
        for shim in failed_shims:
            print(f"  ! {shim}")
        print("To overwrite the backups and apply the shims, run the appropriate add command with force.")
        print()

    untracked = result.get("untracked", [])
    if untracked:
        print("Untracked candidates:")
        for cand in untracked:
            print(f"- {cand}")
        print()

    file_cands = [c for c in untracked if (project_dir / c).is_file()]
    if file_cands:
        print("To track candidate files, run:")
        for cand_path in file_cands:
            print(f"  /superctx:add {cand_path}")
        print()

    return 0


def _cmd_sync(project_dir: Path) -> int:
    result = sync_cmd.run(project_dir)
    print("SuperCtx: regenerated .ctx/SUPERCTX.md")
    for path in result["centralized"]:
        print(f"  + centralized {path}")
    for path in result["missing"]:
        print(f"  ! tracked but not found: {path}")
    if not result["centralized"]:
        print("  (nothing centralized — no tracked files found)")
    return 0


def _cmd_status(project_dir: Path) -> int:
    diag = status_cmd.diagnostics(project_dir)
    print("SuperCtx diagnostics:")
    print(f"  version: {diag['version']}")
    print(f"  plugin root: {diag['plugin_root']}")
    print(f"  registry: {diag['registry']}")

    yes_no = lambda b: "yes" if b else "no"
    print(f"  supports .claude/CLAUDE.md: {yes_no(diag['supports_claude_md'])}")
    print(f"  supports .codex/AGENTS.md: {yes_no(diag['supports_codex_agents'])}")
    print(f"  project has .claude/CLAUDE.md: {yes_no(diag['project_has_claude_md'])}")
    print(f"  project has .codex/AGENTS.md: {yes_no(diag['project_has_codex_agents'])}")
    print()

    if diag["stale_install"]:
        stale_convs = []
        if diag["project_has_claude_md"] and not diag["supports_claude_md"]:
            stale_convs.append("`.claude/CLAUDE.md`")
        if diag["project_has_codex_agents"] and not diag["supports_codex_agents"]:
            stale_convs.append("`.codex/AGENTS.md`")
        convs_str = " and ".join(stale_convs)
        support_it_them = "them" if len(stale_convs) > 1 else "it"
        print(f"WARNING: Stale installation detected! The project uses {convs_str} but the active plugin registry does not support {support_it_them}.")
        print("To update to the latest version, run:")
        print("  /plugin marketplace update superctx")
        print("  /plugin update superctx")
        print("  /reload-plugins")
        print()
        print("If updating does not resolve the issue, reinstall the plugin:")
        print("  /plugin uninstall superctx")
        print("  /plugin install superctx@superctx")
        print("  /reload-plugins")
        print()

    rows = status_cmd.run(project_dir)
    if not rows:
        print("SuperCtx: no tracked files. Run /superctx:init first.")
        return 0

    tracked_rows = [r for r in rows if r["state"] in ("synced", "drifted", "missing")]
    untracked_verified_rows = [r for r in rows if r["state"] == "untracked"]
    candidate_rows = [r for r in rows if r["state"] == "untracked_candidate"]

    if tracked_rows:
        print("Tracked files:")
        for row in tracked_rows:
            print(f"  {row['state']:<10} {row['path']}")

    if untracked_verified_rows:
        if tracked_rows:
            print()
        print("Untracked instruction files (standard conventions):")
        for row in untracked_verified_rows:
            print(f"  untracked  {row['path']}")

    if candidate_rows:
        if tracked_rows or untracked_verified_rows:
            print()
        print("Untracked candidates:")
        for row in candidate_rows:
            note_suffix = f"; {row['note']}" if row["note"] else ""
            label_text = f"{row['label']}{note_suffix}"
            print(f"  ? {row['path']:<24} {label_text}")

    file_cands = [r["path"] for r in candidate_rows if (project_dir / r["path"]).is_file()]
    if file_cands:
        print()
        print("To track local candidate files, run:")
        for cand_path in file_cands:
            print(f"  /superctx:add {cand_path}")

    if any(r["state"] in ("drifted", "untracked") for r in rows):
        print()
        print("Run /superctx:sync to re-centralize.")
    return 0


def _cmd_add(project_dir: Path, file_path: str) -> int:
    try:
        result = add_cmd.run(project_dir, file_path)
        print(result.message)
        return 0
    except add_cmd.AddError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="superctx")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("init", "sync", "status"):
        p = sub.add_parser(name)
        p.add_argument("project_dir", nargs="?", default=".")

    # Add parser
    p_add = sub.add_parser("add")
    p_add.add_argument("path")
    p_add.add_argument("project_dir", nargs="?", default=".")

    args = parser.parse_args(argv)

    project_dir = Path(args.project_dir).resolve()
    if args.cmd == "add":
        return _cmd_add(project_dir, args.path)

    dispatch = {"init": _cmd_init, "sync": _cmd_sync, "status": _cmd_status}
    return dispatch[args.cmd](project_dir)


if __name__ == "__main__":
    sys.exit(main())
