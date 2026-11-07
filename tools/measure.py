"""Benchmark harness (dev-only, not shipped): measures pack output against labeled tasks.

Usage: python tools/measure.py [--split dev|holdout|all|dev2|holdout2] [--style naive|agent|both]
                               [--repos flask,requests,django]

Headline numbers come from a HOLDOUT split only (`holdout` is the original, spent on Step 5;
`holdout2` is the fresh one). `dev`/`dev2` runs are for tuning and are written to
<split>_results.json / <split>_summary.md so they never overwrite the full results. Tasks of the
second generation carry two queries (`naive` keywords, `agent` keywords plus identifiers) and are
run once per style; first-generation tasks have a single `query`.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tessera" / "scripts"))

from _core import (  # noqa: E402
    IgnoreRules, estimate_tokens, find_repo_files, next_budget, read_text, resolve_budget,
)
from _index import RepoIndex, Symbol, build_index  # noqa: E402
from _rank import PackResult, pack_context  # noqa: E402

TASKS_DIR = ROOT / "bench" / "tasks"
REPOS_DIR = ROOT / "bench" / "repos"
RESULTS_DIR = ROOT / "bench" / "results"
TARGET_REDUCTION = 0.60
TARGET_RECALL = 0.85
B2_TOP_FILES = 5
PROFILES = ("lookup", "test", "bug", "explore", "feature")
STYLES = ("naive", "agent")
LEGACY_SPLITS = ("dev", "holdout")
HEADLINE_SPLITS = ("holdout", "holdout2")


def load_tasks(repos: Optional[Sequence[str]]) -> List[dict]:
    tasks: List[dict] = []
    for path in sorted(TASKS_DIR.glob("*.json")):
        for task in json.loads(path.read_text(encoding="utf-8")):
            if repos is None or task["repo"] in repos:
                tasks.append(task)
    return tasks


def split_label(label: str) -> Tuple[str, str]:
    path, _, qualname = label.partition("::")
    return path, qualname


def symbols_for(index: RepoIndex, label: str) -> List[Symbol]:
    path, qualname = split_label(label)
    fi = index.files.get(path)
    return [s for s in fi.symbols if s.qualname == qualname] if fi else []


def covered(result: PackResult, sym: Symbol, forms: Tuple[str, ...]) -> bool:
    """True if a section of one of `forms` contains the symbol (file outlines contain everything)."""
    for sec in result.sections:
        if sec.path != sym.path or sec.form not in forms:
            continue
        if sec.form == "OUTLINE" and sec.qualname == "":
            return True
        if sec.start <= sym.start and (sym.end <= sec.end or sec.form == "TRUNCATED"):
            return True
        if sec.form == "OUTLINE" and sec.start <= sym.start <= sec.end:
            return True
    return False


def score_recall(index: RepoIndex, result: PackResult, entries: List[dict]) -> Dict[str, object]:
    full_hits: List[bool] = []
    any_hits: List[bool] = []
    missing: List[str] = []
    for entry in entries:
        syms = symbols_for(index, entry["symbol"])
        if not syms:
            missing.append(entry["symbol"])
        is_full = any(covered(result, s, ("FULL",)) for s in syms)
        is_any = is_full or any(covered(result, s, ("OUTLINE", "TRUNCATED")) for s in syms)
        if entry["need"] == "full":
            full_hits.append(is_full)
        any_hits.append(is_any)
    return {
        "full_hit": sum(full_hits), "full_total": len(full_hits),
        "any_hit": sum(any_hits), "any_total": len(any_hits),
        "recall_full": sum(full_hits) / len(full_hits) if full_hits else None,
        "recall_any": sum(any_hits) / len(any_hits) if any_hits else None,
        "label_missing": missing,
    }


def file_tokens(root: str, path: str) -> int:
    return estimate_tokens(read_text(Path(root, *path.split("/"))))


def baseline_b1(index: RepoIndex, entries: List[dict]) -> int:
    paths = {split_label(e["symbol"])[0] for e in entries}
    return sum(file_tokens(index.root, p) for p in paths)


def baseline_b2(index: RepoIndex, query: str) -> int:
    """Naive agent: open the 5 files with the most keyword hits, whole."""
    words = [w for w in re.split(r"\s+", query.lower()) if len(w) >= 3]
    hits: List[Tuple[int, str]] = []
    for path in index.files:
        text = read_text(Path(index.root, *path.split("/"))).lower()
        count = sum(text.count(w) for w in words)
        if count:
            hits.append((-count, path))
    top = sorted(hits)[:B2_TOP_FILES]
    return sum(file_tokens(index.root, p) for _, p in top)


def baseline_b3(index: RepoIndex, entries: List[dict]) -> int:
    """Exact line ranges of the labeled symbols (overlaps merged): the hard baseline."""
    spans: Dict[str, List[Tuple[int, int]]] = {}
    for entry in entries:
        for sym in symbols_for(index, entry["symbol"]):
            spans.setdefault(sym.path, []).append((sym.start, sym.end))
    total = 0
    for path, ranges in spans.items():
        lines = read_text(Path(index.root, *path.split("/"))).split("\n")
        merged: List[List[int]] = []
        for start, end in sorted(set(ranges)):
            if merged and start <= merged[-1][1] + 1:
                merged[-1][1] = max(merged[-1][1], end)
            else:
                merged.append([start, end])
        total += sum(estimate_tokens("\n".join(lines[a - 1:b])) for a, b in merged)
    return total


def reduction(pack_tokens: int, baseline: int) -> Optional[float]:
    return None if baseline <= 0 else 1.0 - pack_tokens / baseline


def query_of(task: dict, style: str) -> str:
    return task["queries"][style] if "queries" in task else task["query"]


def styles_of(task: dict, wanted: Sequence[str]) -> List[str]:
    """Query styles to run for a task: first-generation tasks have one unnamed query."""
    return [s for s in wanted if s in task["queries"]] if "queries" in task else ["legacy"]


def run_task(task: dict, style: str = "legacy") -> Dict[str, object]:
    root = str(REPOS_DIR / task["repo"])
    query = query_of(task, style)
    budget, source, notes = resolve_budget(None, task["task"])
    started = time.perf_counter()
    index = build_index(root)
    result = pack_context(index, query, budget, source, task["task"], notes=notes)
    cold_ms = (time.perf_counter() - started) * 1000.0
    again = pack_context(index, query, budget, source, task["task"], notes=notes)
    pack_tokens = result.tokens_used
    recall = score_recall(index, result, task["must_include"])
    row: Dict[str, object] = {
        "id": task["id"], "repo": task["repo"], "split": task["split"], "task": task["task"],
        "style": style, "query": query, "budget": budget, "confidence": result.confidence,
        "low_confidence": result.confidence == "LOW", "pack_tokens": pack_tokens,
        "B1": baseline_b1(index, task["must_include"]), "B2": baseline_b2(index, query),
        "B3": baseline_b3(index, task["must_include"]), "pack_ms": round(cold_ms, 1),
        "index_files": len(index.files), "deterministic": again.text == result.text,
        "budget_limited": result.budget_limited, "sections": [
            [s.form, s.path, s.qualname] for s in result.sections],
    }
    for name in ("B1", "B2", "B3"):
        row["reduction_vs_" + name] = reduction(pack_tokens, row[name])  # type: ignore[arg-type]
    row.update(recall)
    row["escalation_fixes"] = None
    if recall["recall_full"] is not None and recall["recall_full"] < 1.0:
        step = next_budget(budget)
        if step is not None:
            bigger = pack_context(index, query, step, "explicit", task["task"])
            fixed = score_recall(index, bigger, task["must_include"])["recall_full"]
            row["escalation_budget"] = step
            row["escalation_recall_full"] = fixed
            row["escalation_fixes"] = fixed == 1.0
    return row


# --------------------------------------------------------------------- reports

def pct(values: List[float], q: float) -> float:
    ordered = sorted(values)
    pos = (len(ordered) - 1) * q
    low, high = int(pos), min(int(pos) + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (pos - low)


def stats(values: List[Optional[float]]) -> Optional[Dict[str, float]]:
    data = [v for v in values if v is not None]
    if not data:
        return None
    return {"n": len(data), "median": statistics.median(data), "mean": statistics.fmean(data),
            "p25": pct(data, 0.25), "min": min(data), "max": max(data)}


def summarize(rows: List[Dict[str, object]]) -> Dict[str, object]:
    full_hit = sum(r["full_hit"] for r in rows)  # type: ignore[misc]
    full_total = sum(r["full_total"] for r in rows)  # type: ignore[misc]
    any_hit = sum(r["any_hit"] for r in rows)  # type: ignore[misc]
    any_total = sum(r["any_total"] for r in rows)  # type: ignore[misc]
    misses = [r for r in rows if r["recall_full"] is not None and r["recall_full"] < 1.0]  # type: ignore[operator]
    return {
        "n": len(rows),
        "reduction_vs_B1": stats([r["reduction_vs_B1"] for r in rows]),  # type: ignore[misc]
        "reduction_vs_B2": stats([r["reduction_vs_B2"] for r in rows]),  # type: ignore[misc]
        "reduction_vs_B3": stats([r["reduction_vs_B3"] for r in rows]),  # type: ignore[misc]
        "pack_tokens": stats([float(r["pack_tokens"]) for r in rows]),  # type: ignore[arg-type]
        "pack_ms": stats([float(r["pack_ms"]) for r in rows]),  # type: ignore[arg-type]
        "recall_full_micro": full_hit / full_total if full_total else None,
        "recall_full_per_task": stats([r["recall_full"] for r in rows]),  # type: ignore[misc]
        "recall_any_micro": any_hit / any_total if any_total else None,
        "low_confidence_share": sum(1 for r in rows if r["low_confidence"]) / len(rows),
        "low_tokens_mean": statistics.fmean([float(r["pack_tokens"]) for r in rows if r["low_confidence"]])
        if any(r["low_confidence"] for r in rows) else None,
        "deterministic": sum(1 for r in rows if r["deterministic"]),
        "budget_limited": sum(1 for r in rows if r["budget_limited"]),
        "recall_misses": len(misses),
        "escalation_fixed": sum(1 for r in misses if r.get("escalation_fixes")),
    }


def fmt(stat: Optional[Dict[str, float]], percent: bool = True) -> str:
    if not stat:
        return "n/a"
    scale = 100.0 if percent else 1.0
    unit = "%" if percent else ""
    return "n=%d median %.1f%s mean %.1f%s p25 %.1f%s range %.1f%s to %.1f%s" % (
        stat["n"], stat["median"] * scale, unit, stat["mean"] * scale, unit, stat["p25"] * scale, unit,
        stat["min"] * scale, unit, stat["max"] * scale, unit)


def block(title: str, rows: List[Dict[str, object]]) -> List[str]:
    if not rows:
        return []
    s = summarize(rows)
    recall = s["recall_full_micro"]
    any_recall = s["recall_any_micro"]
    low_mean = s["low_tokens_mean"]
    lines = ["### %s (n=%d)" % (title, s["n"]),
             "- reduction vs B1 (whole files, the claim baseline): " + fmt(s["reduction_vs_B1"]),  # type: ignore[arg-type]
             "- reduction vs B2 (grep and open 5 files): " + fmt(s["reduction_vs_B2"]),  # type: ignore[arg-type]
             "- reduction vs B3 (exact line ranges, the hard baseline): " + fmt(s["reduction_vs_B3"]),  # type: ignore[arg-type]
             "- recall_full (need=full entries, micro): %s; per-task: %s" % (
                 "n/a" if recall is None else "%.1f%%" % (100 * recall), fmt(s["recall_full_per_task"])),  # type: ignore[arg-type]
             "- recall_any (all entries, FULL or OUTLINE, micro): %s" % (
                 "n/a" if any_recall is None else "%.1f%%" % (100 * any_recall)),
             "- pack tokens: " + fmt(s["pack_tokens"], False),  # type: ignore[arg-type]
             "- cold pack time (index + pack), ms: " + fmt(s["pack_ms"], False),  # type: ignore[arg-type]
             "- LOW confidence: %.0f%% of tasks%s" % (
                 100 * s["low_confidence_share"],  # type: ignore[operator]
                 "" if low_mean is None else "; the LOW response itself costs ~%.0f tokens (extra cost of one retry)" % low_mean),
             "- deterministic: %d/%d; budget-limited: %d; recall misses: %d (one escalation step fixed %d)" % (
                 s["deterministic"], s["n"], s["budget_limited"], s["recall_misses"], s["escalation_fixed"]), ""]
    return lines


def render_summary(rows: List[Dict[str, object]], splits: Sequence[str], repos: List[str]) -> str:
    out = ["# Benchmark summary", "",
           "Estimates only (token counts are heuristic). Repos: " + ", ".join(
               "%s@%s" % (r, commit_of(r)) for r in repos) + ".",
           "Targets: median reduction vs B1 >= %d%%; recall_full >= %d%%. Headline = a holdout split only." % (
               TARGET_REDUCTION * 100, TARGET_RECALL * 100), ""]
    for split in splits:
        in_split = [r for r in rows if r["split"] == split]
        for style in sorted({str(r["style"]) for r in in_split}):
            part = [r for r in in_split if r["style"] == style]
            title = "HOLDOUT (headline)" if split in HEADLINE_SPLITS else split.upper() + " (tuning only)"
            label = "" if style == "legacy" else " / %s queries" % style
            out += ["## %s: %s%s" % (title, split, label), ""] + block("all repos", part)
            out += sum((block(repo, [r for r in part if r["repo"] == repo]) for repo in repos), [])
            out += sum((block("profile: " + p, [r for r in part if r["task"] == p]) for p in PROFILES), [])
    out += ["## Per-task results", "",
            "| id | style | split | profile | conf | tokens | B1 | red B1 | recall_full | recall_any | ms | note |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        notes = []
        if r["low_confidence"]:
            notes.append("LOW")
        if r["recall_full"] is not None and r["recall_full"] < 1.0:  # type: ignore[operator]
            notes.append("recall miss" + (", escalation fixes" if r.get("escalation_fixes") else ""))
        if r["label_missing"]:
            notes.append("LABEL MISSING")
        red = r["reduction_vs_B1"]
        out.append("| %s | %s | %s | %s | %s | %d | %d | %s | %s | %s | %.0f | %s |" % (
            r["id"], r["style"], r["split"], r["task"], r["confidence"], r["pack_tokens"], r["B1"],
            "n/a" if red is None else "%.0f%%" % (100 * red),  # type: ignore[operator]
            "n/a" if r["recall_full"] is None else "%.2f" % r["recall_full"],  # type: ignore[str-format]
            "n/a" if r["recall_any"] is None else "%.2f" % r["recall_any"],  # type: ignore[str-format]
            r["pack_ms"], ", ".join(notes)))
    return "\n".join(out) + "\n"


def commit_of(repo: str) -> str:
    head = REPOS_DIR / repo / ".git" / "HEAD"
    try:
        ref = head.read_text(encoding="utf-8").strip()
        if ref.startswith("ref: "):
            ref = (REPOS_DIR / repo / ".git" / ref[5:]).read_text(encoding="utf-8").strip()
        return ref[:7]
    except OSError:
        return "unknown"


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=("dev", "holdout", "all", "dev2", "holdout2"), default="all",
                        help="`all` means the first-generation dev and holdout splits")
    parser.add_argument("--style", choices=STYLES + ("both",), default="both",
                        help="query style for second-generation tasks")
    parser.add_argument("--repos", default=None, help="comma-separated subset of repos")
    args = parser.parse_args(argv)
    repos = args.repos.split(",") if args.repos else None
    wanted = STYLES if args.style == "both" else (args.style,)
    keep = LEGACY_SPLITS if args.split == "all" else (args.split,)
    tasks = [t for t in load_tasks(repos) if t["split"] in keep]
    rows = []
    for task in tasks:
        for style in styles_of(task, wanted):
            row = run_task(task, style)
            rows.append(row)
            print("%-12s %-7s %-8s %-4s %5d tok  recall_full=%s  %6.0f ms" % (
                row["id"], style, row["split"], row["confidence"], row["pack_tokens"], row["recall_full"],
                row["pack_ms"]), flush=True)
    present = sorted({r["repo"] for r in rows})
    splits = keep
    prefix = "" if args.split == "all" else args.split + "_" + ("" if args.style == "both" else args.style + "_")
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    groups = sorted({(str(r["split"]), str(r["style"])) for r in rows})
    payload = {"commits": {r: commit_of(r) for r in present},
               "summary": {s if st == "legacy" else "%s/%s" % (s, st): summarize(
                   [r for r in rows if r["split"] == s and r["style"] == st]) for s, st in groups},
               "tasks": rows}
    (RESULTS_DIR / (prefix + "results.json")).write_text(
        json.dumps(payload, indent=1, sort_keys=True), encoding="utf-8")
    (RESULTS_DIR / (prefix + "summary.md")).write_text(render_summary(rows, splits, present), encoding="utf-8")
    print("wrote", RESULTS_DIR / (prefix + "summary.md"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
