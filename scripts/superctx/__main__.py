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


def _cmd_init(project_dir: Path) -> int:
    result = init_cmd.run(project_dir)
    if not result["created"]:
        print(f"SuperCtx: {result['ctx_dir']} already exists — no changes made.")
        return 0
    print(f"SuperCtx: created {result['ctx_dir']}")
    if result["detected"]:
        print("Tracked tool files detected:")
        for path in result["detected"]:
            print(f"  - {path}")
    else:
        print("No known tool instruction files detected yet.")
    print("Next: run /superctx:sync to centralize into .ctx/SUPERCTX.md")
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
        print("SuperCtx: no tracked files. Run /superctx:setup first.")
        return 0
    print("SuperCtx status:")
    for row in rows:
        print(f"  {row['state']:<10} {row['path']}")
    if any(r["state"] in ("drifted", "untracked") for r in rows):
        print("Run /superctx:sync to re-centralize.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="superctx")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("init", "sync", "status"):
        p = sub.add_parser(name)
        p.add_argument("project_dir", nargs="?", default=".")
    args = parser.parse_args(argv)

    project_dir = Path(args.project_dir).resolve()
    dispatch = {"init": _cmd_init, "sync": _cmd_sync, "status": _cmd_status}
    return dispatch[args.cmd](project_dir)


if __name__ == "__main__":
    sys.exit(main())
