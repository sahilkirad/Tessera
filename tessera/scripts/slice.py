"""slice.py: file outline, exact symbol source, or exact line range."""
from __future__ import annotations

import os
import sys
from typing import Optional, Sequence

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _core import (  # noqa: E402
    UsageError, footer, make_parser, require_root, run_guarded, safe_resolve,
)
from _index import slice_report, split_target  # noqa: E402

DEFAULT_MAX_LINES = 400


def _run(argv: Optional[Sequence[str]]) -> int:
    parser = make_parser("slice.py", "Outline a file, or print an exact symbol or line range.")
    parser.add_argument("target", help="path.py | path.py:Class.method | path.py:40-88")
    parser.add_argument("--imports", action="store_true", help="include imports in the outline")
    parser.add_argument("--context", type=int, default=0, help="extra lines before and after")
    parser.add_argument("--with-class", action="store_true", help="prepend the enclosing class header")
    parser.add_argument("--max-lines", type=int, default=DEFAULT_MAX_LINES,
                        help="cut SYMBOL/RANGE output at N lines (default 400)")
    args = parser.parse_args(argv)
    if args.context < 0:
        raise UsageError("--context must be 0 or more")
    if args.max_lines < 1:
        raise UsageError("--max-lines must be at least 1")
    root = require_root(args.root)
    raw_path, spec = split_target(args.target)
    path = safe_resolve(root, raw_path)
    if path.is_dir() or path.suffix != ".py":
        raise UsageError("not a Python file: %s" % raw_path)
    rel = os.path.relpath(str(path), root).replace(os.sep, "/")
    text, omitted, warnings = slice_report(
        path, rel, spec, args.imports, args.context, args.with_class, args.max_lines)
    print("\n".join(filter(None, [text, footer(omitted, warnings)])))
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    return run_guarded(_run, argv)


if __name__ == "__main__":
    sys.exit(main())
