"""pack.py: one call that returns a token-budgeted context bundle for a task."""
from __future__ import annotations

import json
import os
import sys
from typing import Optional, Sequence

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _core import (  # noqa: E402
    BUDGET_TOO_SMALL, MIN_BUDGET, NO_PYTHON_FILES, TASK_BUDGETS, Deadline, UsageError, footer,
    make_parser, require_root, resolve_budget, run_guarded,
)
from _index import build_index  # noqa: E402
from _rank import DEFAULT_DEPTH, DEFAULT_SEEDS, MAX_DEPTH, pack_context  # noqa: E402


def _run(argv: Optional[Sequence[str]]) -> int:
    parser = make_parser("pack.py", "Token-budgeted context bundle for a query.")
    parser.add_argument("query", help='3-6 identifier-like keywords, e.g. "discount coupon receipt"')
    parser.add_argument("--task", help="budget profile: " + ", ".join(TASK_BUDGETS))
    parser.add_argument("--budget", type=int, default=None, help="explicit token budget (cap 8000)")
    parser.add_argument("--seeds", type=int, default=DEFAULT_SEEDS, help="top symbols shown in full (default 3)")
    parser.add_argument("--depth", type=int, default=DEFAULT_DEPTH, help="import levels for outlines (default 2)")
    parser.add_argument("--json", action="store_true", help="machine-readable summary")
    args = parser.parse_args(argv)
    if args.seeds < 1:
        raise UsageError("--seeds must be at least 1")
    if args.depth < 1:
        raise UsageError("--depth must be at least 1")
    budget, source, notes = resolve_budget(args.budget, args.task)
    root = require_root(args.root)
    if budget < MIN_BUDGET:
        print(BUDGET_TOO_SMALL)
        return 0
    if args.depth > MAX_DEPTH:
        notes.append("depth %d clamped to %d" % (args.depth, MAX_DEPTH))
    index = build_index(root, deadline=Deadline(args.max_seconds))
    if not index.files:
        print("\n".join(filter(None, [NO_PYTHON_FILES, footer([], index.warnings)])))
        return 0
    result = pack_context(index, args.query, budget, source, args.task, args.seeds, args.depth, notes)
    print(json.dumps(result.to_json(), ensure_ascii=False) if args.json else result.text)
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    return run_guarded(_run, argv)


if __name__ == "__main__":
    sys.exit(main())
