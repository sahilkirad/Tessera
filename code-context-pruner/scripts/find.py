"""find.py: keyword search for functions, classes and methods."""
from __future__ import annotations

import json
import os
import sys
from typing import Optional, Sequence

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _core import (  # noqa: E402
    NO_PYTHON_FILES, Deadline, UsageError, footer, make_parser, require_root, run_guarded,
)
from _index import build_index  # noqa: E402
from _rank import find_payload, rank_symbols, render_find, tokenize  # noqa: E402

DEFAULT_TOP = 8


def _run(argv: Optional[Sequence[str]]) -> int:
    parser = make_parser("find.py", "Find symbols by 3-6 identifier-like keywords.")
    parser.add_argument("query", help='keywords, e.g. "discount coupon promo"')
    parser.add_argument("--top", type=int, default=DEFAULT_TOP, help="results to show (default 8)")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)
    if args.top < 1:
        raise UsageError("--top must be at least 1")
    root = require_root(args.root)
    index = build_index(root, deadline=Deadline(args.max_seconds))
    if not index.files:
        print("\n".join(filter(None, [NO_PYTHON_FILES, footer([], index.warnings)])))
        return 0
    result = rank_symbols(index, tokenize(args.query))
    if args.json:
        print(json.dumps(find_payload(result, args.top, index.warnings), ensure_ascii=False))
    else:
        print(render_find(args.query, result, args.top, index.warnings))
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    return run_guarded(_run, argv)


if __name__ == "__main__":
    sys.exit(main())
