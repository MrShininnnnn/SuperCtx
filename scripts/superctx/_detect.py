"""Internal read-only repository-state detection entry point.

This module exists for hooks and tests. It is intentionally not part of the
public `superctx` command surface.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from .status import detect_repo_state


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    project_dir = Path(args[0] if args else ".").resolve()
    print(json.dumps(detect_repo_state(project_dir)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
