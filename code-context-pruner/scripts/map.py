"""map.py: ranked, token-budgeted overview of a Python repository."""
from __future__ import annotations

import os
import sys
from typing import List, Optional, Sequence

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _core import (  # noqa: E402
    BUDGET_TOO_SMALL, MIN_BUDGET, NO_PYTHON_FILES, Deadline, PathError, footer, make_parser,
    require_root, resolve_budget, run_guarded, safe_resolve,
)
from _index import build_index  # noqa: E402
from _rank import render_map  # noqa: E402

DEFAULT_MAP_BUDGET = 1000


def _run(argv: Optional[Sequence[str]]) -> int:
    parser = make_parser("map.py", "Ranked overview of a Python repo within a token budget.")
    parser.add_argument("path", nargs="?", default="", help="folder inside root to focus on")
    parser.add_argument("--budget", type=int, default=None, help="token budget (default 1000)")
    args = parser.parse_args(argv)
    root = require_root(args.root)
    budget, _, notes = resolve_budget(DEFAULT_MAP_BUDGET if args.budget is None else args.budget, None)
    if budget < MIN_BUDGET:
        print(BUDGET_TOO_SMALL)
        return 0
    focus = ""
    if args.path:
        target = safe_resolve(root, args.path)
        if not target.is_dir():
            raise PathError("not a folder: %s" % args.path)
        focus = os.path.relpath(str(target), root).replace(os.sep, "/")
        focus = "" if focus == "." else focus
    index = build_index(root, deadline=Deadline(args.max_seconds))
    index.warnings.extend(notes)
    if not index.files:
        print("\n".join(filter(None, [NO_PYTHON_FILES, footer([], index.warnings)])))
        return 0
    print(render_map(index, focus, budget))
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    return run_guarded(_run, argv)


if __name__ == "__main__":
    sys.exit(main())
