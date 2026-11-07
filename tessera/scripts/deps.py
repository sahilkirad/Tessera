"""deps.py: what a file imports (breadth-first), or which files import it."""
from __future__ import annotations

import os
import sys
from typing import Optional, Sequence

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _core import (  # noqa: E402
    NO_PYTHON_FILES, Deadline, PathError, UsageError, footer, make_parser, require_root, run_guarded,
    safe_resolve,
)
from _index import build_index  # noqa: E402
from _rank import DEFAULT_DEPTH, MAX_DEPTH, deps_bfs, render_deps, render_reverse, reverse_deps  # noqa: E402


def _run(argv: Optional[Sequence[str]]) -> int:
    parser = make_parser("deps.py", "Trace repo imports of a Python file.")
    parser.add_argument("file", help="path to a .py file inside root")
    parser.add_argument("--depth", type=int, default=DEFAULT_DEPTH, help="levels to follow (default 2, max 3)")
    parser.add_argument("--reverse", action="store_true", help="list files that import FILE (file level)")
    args = parser.parse_args(argv)
    if args.depth < 1:
        raise UsageError("--depth must be at least 1")
    root = require_root(args.root)
    path = safe_resolve(root, args.file)
    rel = os.path.relpath(str(path), root).replace(os.sep, "/")
    index = build_index(root, deadline=Deadline(args.max_seconds))
    if not index.files:
        print("\n".join(filter(None, [NO_PYTHON_FILES, footer([], index.warnings)])))
        return 0
    if rel not in index.files:
        raise PathError("not an indexed Python file: %s" % args.file)
    warnings = list(index.warnings)
    if args.depth > MAX_DEPTH:
        warnings.append("depth %d clamped to %d" % (args.depth, MAX_DEPTH))
    if args.reverse:
        print(render_reverse(rel, reverse_deps(index, rel), warnings))
    else:
        print(render_deps(deps_bfs(index, rel, args.depth), warnings))
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    return run_guarded(_run, argv)


if __name__ == "__main__":
    sys.exit(main())
