"""Internal read-only repository-state detection entry point.

This module exists for hooks and tests. It is intentionally not part of the
public `superctx` command surface.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from . import core, registry
from .status import detect_repo_state


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    project_dir = Path(args[0] if args else ".").resolve()
    reason, detail = "ctx_unreadable", core.unreadable_ctx_entry(project_dir)
    if detail is None:
        try:
            registry.check_readable(project_dir)
        except registry.ScanError as e:
            reason, detail = "tool_folder_unreadable", str(e)
    if detail is not None:
        # Detection would be incomplete or fail partway; report the folder instead.
        print(json.dumps({
            "state": "unreadable",
            "candidates": [],
            "reasons": [reason],
            "detail": detail,
            "recommended_action": "inspect",
            "recommended_action_mutates_files": False
        }))
        return 1
    print(json.dumps(detect_repo_state(project_dir)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
