"""Compare the shipped token ESTIMATE with a reference tokenizer (dev-only, not shipped).

Uses `tiktoken` (OpenAI's tokenizer) only if it is installed; it is a reference point, not the
tokenizer of Claude or Gemini. Usage: python tools/calibrate_tokens.py [--files 200]
"""
from __future__ import annotations

import argparse
import itertools
import math
import statistics
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tessera" / "scripts"))

from _core import _CAMEL_RE, _TOKEN_RE, estimate_tokens, find_repo_files, padded, read_text  # noqa: E402

REPOS = ("flask", "requests", "django")


def sample_files(count: int) -> List[Path]:
    """Deterministic, evenly spaced sample across the benchmark repos."""
    per_repo = count // len(REPOS)
    chosen: List[Path] = []
    for repo in REPOS:
        root = ROOT / "bench" / "repos" / repo
        if not root.is_dir():
            continue
        paths = find_repo_files(str(root))
        step = max(1, len(paths) // per_repo)
        chosen += [root / p for p in paths[::step][:per_repo]]
    return chosen


def features(text: str) -> Dict[str, List[int]]:
    """Per-class counts used to re-weigh the estimate without re-tokenizing."""
    out: Dict[str, List[int]] = {"alpha": [], "digit": [], "newline": [0], "punct": [0], "nonascii": [0]}
    for match in _TOKEN_RE.finditer(text):
        kind, token = match.lastgroup, match.group()
        if kind == "a":
            out["alpha"].extend(len(w) for w in _CAMEL_RE.findall(token))
        elif kind == "d":
            out["digit"].append(len(token))
        elif kind == "w":
            out["newline"][0] += token.count("\n")
        elif kind == "u":
            out["nonascii"][0] += 1
        else:
            out["punct"][0] += 1
    return out


def weighed(f: Dict[str, List[int]], alpha: float, digit: float, newline: float, punct: float) -> float:
    return (sum(math.ceil(n / alpha) for n in f["alpha"]) + sum(math.ceil(n / digit) for n in f["digit"])
            + newline * f["newline"][0] + punct * f["punct"][0] + 2 * f["nonascii"][0])


def mape(pairs: Sequence[Tuple[float, int]]) -> float:
    return 100.0 * statistics.fmean(abs(est - ref) / ref for est, ref in pairs if ref)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--files", type=int, default=200)
    args = parser.parse_args(argv)
    try:
        import tiktoken
    except ImportError:
        print("tiktoken is not installed: calibration skipped (estimate left unchanged).")
        return 0
    encoder = tiktoken.get_encoding("cl100k_base")
    texts = [read_text(p) for p in sample_files(args.files)]
    refs = [len(encoder.encode(t, disallowed_special=())) for t in texts]
    feats = [features(t) for t in texts]
    current = [(estimate_tokens(t), r) for t, r in zip(texts, refs)]
    ratios = [e / r for e, r in current if r]
    print("files=%d reference=tiktoken cl100k_base (OpenAI; a reference point only)" % len(texts))
    print("current estimate: MAPE %.1f%%, mean ratio estimate/reference %.2f, median %.2f, min %.2f, max %.2f" % (
        mape(current), statistics.fmean(ratios), statistics.median(ratios), min(ratios), max(ratios)))
    short = sum(1 for e, r in current if padded(e) < r) / len(current)
    print("files where the estimate WITH the 1.10 safety margin is still below the reference: %.1f%%" % (100 * short))
    grid = []
    for alpha, digit, newline, punct in itertools.product((4, 5, 6, 7, 8), (3, 4), (0.25, 0.5, 0.75, 1.0), (0.25, 0.5, 0.75, 1.0)):
        pairs = [(weighed(f, alpha, digit, newline, punct), r) for f, r in zip(feats, refs)]
        under = sum(1 for e, r in pairs if e < r) / len(pairs)
        grid.append((mape(pairs), alpha, digit, newline, punct, under))
    print("best weightings (MAPE, alpha divisor, digit divisor, newline weight, punct weight, share under-estimated):")
    for row in sorted(grid)[:5]:
        print("  %.1f%%  alpha/%d digit/%d newline*%.1f punct*%.2f  under=%.0f%%" % (
            row[0], row[1], row[2], row[3], row[4], 100 * row[5]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
