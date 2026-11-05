"""CLI entry point: `python3 -m superctx <sync|add> [project_dir]`.

Skills invoke this with PYTHONPATH pointing at the plugin's scripts/ directory. The default
project_dir is the current working directory (the user's project).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import sync as sync_cmd
from . import add as add_cmd


# Why a path was left in place or could not be published.
REASONS = {
    "unsafe_path": "a symlink in its path could redirect the write, so SuperCtx left it unchanged",
    "native_edited": "it holds content someone wrote, so SuperCtx left it unchanged",
    "native_replaced": "a file or folder replaced what SuperCtx published there",
    "link_retargeted": "the link points somewhere other than its canonical copy in .ctx/",
    "canonical_missing": "its canonical copy in .ctx/ is missing; restore it from version control or .ctx/sources/",
    "not_verified": "SuperCtx has not verified this tool's behavior through a link",
    "already_a_symlink": "it is already a symlink you manage",
    "contains_symlink": "it contains symlinks, which could break after moving it",
    "no_skill_md": "the folder has no SKILL.md",
    "name_collision": "another resource would get the same name or canonical path",
    "breaks_reference": "it links to a file next to it that would not resolve from its canonical path in .ctx/",
    "unclear_reference": "it has a link or import whose destination SuperCtx cannot determine, so moving it could break it",
    "canonical_exists": "something already exists at its canonical path in .ctx/",
    "backup_exists": "a backup already exists for it in .ctx/sources/",
    "backup_exists_and_live_has_edits": "inspect the backup in .ctx/sources/ against your local version",
}


def _explain(reason: str) -> str:
    return f"{reason}: {REASONS[reason]}" if reason in REASONS else reason


def _print_left_in_place(result: dict) -> None:
    left = result.get("left_in_place", [])
    if left:
        print()
        print("Left in place:")
        for item in left:
            print(f"- {item['path']} ({item['type']}): {_explain(item['reason'])}")


def _print_init_result(result: dict, project_dir: Path) -> None:
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
        else:
            print("SuperCtx: Already initialized.")
        return

    print("SuperCtx initialized this repo.")
    print()

    connected = result.get("connected", [])
    if connected:
        print("Connected:")
        for file in connected:
            print(f"- {file}")
        print()

    linked = result.get("linked", [])
    if linked:
        print("Linked (moved into .ctx/, with a symlink at the original path):")
        for path in linked:
            print(f"- {path}")
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
        reasons = result.get("failed_reasons", {})
        print("WARNING: Some adopted paths could not be published:")
        for path in failed_shims:
            print(f"  ! {path}: {_explain(reasons.get(path, 'unknown'))}")
        print()

    _print_left_in_place(result)

    untracked = result.get("untracked", [])
    if untracked:
        print("Untracked candidates:")
        for cand in untracked:
            print(f"- {cand}")
        print()

    file_cands = [c for c in untracked if (project_dir / c).is_file()]
    if file_cands:
        print("Recommended action: Offer to connect these candidate files (with explicit consent).")
        print()


def _cmd_sync(project_dir: Path) -> int:
    try:
        result = sync_cmd.run(project_dir)
    except sync_cmd.SyncError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    mode = result.get("mode")
    final_state = result.get("final_state", "needs_attention")

    if result.get("migrated"):
        print("Migrated the manifest to .ctx/superctx.toml (v1 copy kept at .ctx/manifest.v1.toml).")
        print()

    if mode == "not_candidate":
        print("SuperCtx: No setup needed. No candidate instruction files found.")
        return 0

    elif mode == "healthy":
        print("All SuperCtx context links are healthy.")
        _print_left_in_place(result)
        candidates = result.get("candidates", [])
        if candidates:
            print()
            print("Untracked candidates:")
            for cand in sorted(candidates):
                print(f"- {cand}")
            print()
            print("Recommended action: Offer to connect these candidate files (with explicit consent).")
        return 0

    elif mode == "init":
        _print_init_result(result["init_result"], project_dir)
        return 0 if final_state == "healthy" else 1

    elif mode == "inspect":
        print(result.get("message", "SuperCtx is present, but the configuration manifest or hub is missing or invalid."))
        print("Recommended action: Explain the problem and offer to inspect the setup.")
        return 1

    elif mode == "legacy":
        print("SuperCtx is present, but some instruction files are legacy and not yet fully migrated.")
        print("Recommended action: Offer to migrate/recover the legacy SuperCtx setup (with explicit consent).")
        return 1

    elif mode == "repair":
        if result["repaired"]:
            print("Repaired shims:")
            for path in result["repaired"]:
                print(f"  + {path}")
            print()

        if result["unresolved"]:
            print("Unresolved shims:")
            for item in result["unresolved"]:
                print(f"  ! {item['path']}: {_explain(item['reason'])}")
            print()

        if result["warnings"]:
            print("Warnings:")
            for warning in result["warnings"]:
                if warning["reason"] == "missing_backup":
                    print(f"  ! Backup missing for {warning['path']}; original content cannot be recovered.")
                else:
                    print(f"  ! {warning['path']}: {warning['reason']}")
            print()

        _print_left_in_place(result)

        if not any(result[key] for key in ("repaired", "unresolved", "warnings")):
            if result.get("healthy"):
                print("All SuperCtx shims are healthy; no repair needed.")
            else:
                print("  (no registered files)")

        return 0 if final_state == "healthy" else 1

    else:
        print(result.get("message", "Unexpected sync state."))
        return 0 if final_state == "healthy" else 1


def _cmd_add(project_dir: Path, file_path: str, create_if_missing: bool = False) -> int:
    try:
        result = add_cmd.run(project_dir, file_path, create_if_missing=create_if_missing)
        print(result.message)
        return 0
    except add_cmd.AddError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="superctx")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_sync = sub.add_parser("sync")
    p_sync.add_argument("project_dir", nargs="?", default=".")

    # Add parser
    p_add = sub.add_parser("add")
    p_add.add_argument("path")
    p_add.add_argument("project_dir", nargs="?", default=".")
    p_add.add_argument(
        "--create-shim",
        action="store_true",
        help="Create a generated shim even if the file does not exist yet (known conventions only)"
    )

    args = parser.parse_args(argv)

    project_dir = Path(args.project_dir).resolve()
    if args.cmd == "add":
        return _cmd_add(project_dir, args.path, create_if_missing=getattr(args, "create_shim", False))

    dispatch = {"sync": _cmd_sync}
    return dispatch[args.cmd](project_dir)


if __name__ == "__main__":
    sys.exit(main())
