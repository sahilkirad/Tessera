"""Dev-only: time cold find, pack and map (one new process each) on large repos; writes bench/results/large_repo_timing.md.

This is a speed measurement of the frozen scripts, separate from the holdout2 recall benchmark.
Usage: python tools/time_cold.py [repo ...]   (default: django click)
"""
from __future__ import annotations

import json
import platform
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "tessera" / "scripts"
RESULTS = ROOT / "bench" / "results"
RUNS = 3


def first_query(repo: str) -> str:
    tasks = json.loads((ROOT / "bench" / "tasks" / (repo + ".json")).read_text(encoding="utf-8"))
    task = tasks[0]
    return task["queries"]["naive"] if "queries" in task else task["query"]


def timed(args: list[str]) -> float:
    started = time.perf_counter()
    done = subprocess.run([sys.executable, "-I", *args], capture_output=True, text=True, check=False)
    if done.returncode != 0:
        raise SystemExit("failed: %s\n%s" % (args, done.stderr[-400:]))
    return time.perf_counter() - started


def main(argv: list[str] | None = None) -> int:
    repos = (sys.argv[1:] if argv is None else argv) or ["django", "click"]
    lines = ["# Cold timing of the frozen scripts (separate from the holdout2 benchmark)", "",
             "Each run is a new Python process (`python -I script ...`): it builds the index from scratch and prints. %d runs per cell, seconds, raw values then median and range. Python %s on %s. Machine caveat: a Windows laptop whose speed varied a lot during this project (the same Django query took 15 s on one occasion and 5.5 s on another), so treat these as one machine's numbers, not a guarantee." % (
                 RUNS, platform.python_version(), platform.platform()), "",
             "| repo | python files | command | runs (s) | median (s) | range (s) |", "|---|---|---|---|---|---|"]
    for repo in repos:
        root = str(ROOT / "bench" / "repos" / repo)
        files = sum(1 for p in Path(root).rglob("*.py") if ".git" not in p.parts)
        query = first_query(repo)
        commands = {
            "find": [str(SCRIPTS / "find.py"), query, "--root", root],
            "pack": [str(SCRIPTS / "pack.py"), query, "--root", root, "--task", "bug"],
            "map": [str(SCRIPTS / "map.py"), "--root", root],
        }
        for name, args in commands.items():
            runs = [timed(args) for _ in range(RUNS)]
            lines.append("| %s | %d | %s | %s | %.1f | %.1f to %.1f |" % (
                repo, files, name, ", ".join("%.1f" % r for r in runs), statistics.median(runs), min(runs), max(runs)))
            print(lines[-1], flush=True)
    lines += ["", "Query used per repo: the first task in `bench/tasks/<repo>.json` (naive style where available)."]
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "large_repo_timing.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
