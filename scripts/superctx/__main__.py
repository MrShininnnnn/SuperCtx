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
            if result.get("manifest_error"):
                print(f"Error parsing manifest: {result['manifest_error']}")
            else:
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
        print("To resolve, remove the conflicting backup files in .ctx/sources/ and run /superctx:init again.")
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
    try:
        result = sync_cmd.run(project_dir)
    except sync_cmd.SyncError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    has_problems = result["unresolved"] or result["warnings"]
    if not has_problems and not result["repaired"]:
        if result["healthy"]:
            print("All SuperCtx shims are healthy; no repair needed.")
        else:
            print("  (no registered files)")
        return 0

    if result["repaired"]:
        print("Repaired shims:")
        for path in result["repaired"]:
            print(f"  + {path}")
        print()

    if result["unresolved"]:
        print("Unresolved shims:")
        for item in result["unresolved"]:
            print(f"  ! {item['path']}: {item['reason']}")
        print()

    if result["warnings"]:
        print("Warnings:")
        for warning in result["warnings"]:
            if warning["reason"] == "missing_backup":
                print(f"  ! Backup missing for {warning['path']}; original content cannot be recovered.")
            else:
                print(f"  ! {warning['path']}: {warning['reason']}")
        print()

    if not any(result[key] for key in ("repaired", "unresolved", "warnings")):
        print("  (no registered files)")

    return 0


def _cmd_status(project_dir: Path) -> int:
    try:
        diag = status_cmd.diagnostics(project_dir)

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
    except status_cmd.StatusError:
        print("SuperCtx: no tracked files. Run /superctx:init first.")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    hub_row = next((r for r in rows if r["kind"] == "hub"), None)
    shim_rows = [r for r in rows if r["kind"] == "shim"]
    backup_rows = [r for r in rows if r["kind"] == "backup"]
    candidate_rows = [r for r in rows if r["kind"] == "candidate"]

    hub_healthy = hub_row and hub_row["state"] == "healthy"
    shims_healthy = all(r["state"] == "healthy" for r in shim_rows)
    backups_healthy = all(r["state"] == "healthy" for r in backup_rows)
    all_healthy = hub_healthy and shims_healthy and backups_healthy and not candidate_rows

    if all_healthy:
        print("All SuperCtx context links are healthy.")
        return 0

    # Hub problems
    if hub_row and hub_row["state"] != "healthy":
        if hub_row["state"] == "missing_hub":
            print(f"Hub missing: {hub_row['path']}")
        elif hub_row["state"] == "empty_hub":
            print(f"Hub empty: {hub_row['path']}")
        print()

    # Shim problems
    broken_shims = [r for r in shim_rows if r["state"] != "healthy"]
    if broken_shims:
        print("Shim issues:")
        for row in broken_shims:
            print(f"  ! {row['path']} — shim missing or broken")
        print("  Run /superctx:sync to repair.")
        print()

    # Backup problems
    missing_backups = [r for r in backup_rows if r["state"] != "healthy"]
    if missing_backups:
        print("Missing backups:")
        for row in missing_backups:
            print(f"  ! {row['path']}")
        print()

    # Candidates
    if candidate_rows:
        print("Untracked candidates:")
        for row in candidate_rows:
            print(f"  ? {row['path']}")
            print(f"    Run /superctx:add {row['path']} to connect it.")
        print()

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
