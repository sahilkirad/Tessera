"""Dev-only: for every `need: full` symbol that pack missed, test which recovery path finds it.

Paths (all on the frozen scripts, in-process; the CLIs are thin wrappers over the same functions):
  R1a  pack with the symbol's qualified name alone as the query
  R1b  pack with the original task query plus the qualified name appended
  R2   find with the bare method/function name; hit within the top 8 / top 20
  R3   find with the name plus the first two content words of the task query; top 8 / top 20
  R4a  slice path:Class.method (only when the path appeared in the original pack output)
  R4b  slice path (outline lists the name; same applicability)
  R5   map <folder of the file> lists the name
This is a text-guidance measurement. It does not tune any code.
Usage: python tools/recovery_paths.py   -> bench/results/recovery_paths.md and .json
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import measure  # noqa: E402
from _core import resolve_budget  # noqa: E402
from _index import RepoIndex, Symbol, build_index, slice_report  # noqa: E402
from _rank import STOPWORDS, pack_context, rank_symbols, render_map, tokenize  # noqa: E402

SPLITS = ("dev", "dev2", "holdout2")
RESULTS = ROOT / "bench" / "results"
MAP_BUDGET = 1000


def in_top(index: RepoIndex, query: str, sym: Symbol, top: int) -> bool:
    hits = rank_symbols(index, tokenize(query)).hits[:top]
    return any(h.symbol.path == sym.path and h.symbol.qualname == sym.qualname and h.symbol.start == sym.start
               for h in hits)


def task_words(query: str, name: str) -> List[str]:
    """First two content words of the task query that are not part of the symbol name."""
    skip = set(tokenize(name)) | STOPWORDS
    words = [w for w in re.findall(r"[A-Za-z][A-Za-z0-9]*", query) if len(w) >= 4 and w.lower() not in skip]
    return words[:2]


def pack_has(index: RepoIndex, query: str, task: dict, sym: Symbol) -> bool:
    budget, source, notes = resolve_budget(None, task["task"])
    result = pack_context(index, query, budget, source, task["task"], notes=notes)
    return measure.covered(result, sym, ("FULL",))


def path_shown(result, omitted_text: str, sym: Symbol) -> bool:
    return any(sec.path == sym.path for sec in result.sections) or sym.path in omitted_text


def try_slice(index: RepoIndex, sym: Symbol, spec: Optional[str]) -> bool:
    path = Path(index.root, *sym.path.split("/"))
    text, _, _ = slice_report(path, sym.path, spec, False, 0, False, 400)
    first = [ln for ln in text.split("\n") if ln.strip()][:1]
    if first and (first[0].startswith("AMBIGUOUS") or first[0].startswith("NOT FOUND")):
        return False
    return re.search(r"\b%s\b" % re.escape(sym.name), text) is not None


def one_miss(index: RepoIndex, task: dict, style: str, query: str, result, sym: Symbol) -> Dict[str, object]:
    omitted_text = " ".join(result.omitted)
    known = path_shown(result, omitted_text, sym)
    words = task_words(query, sym.name)
    folder = sym.path.rpartition("/")[0]
    r3q = " ".join([sym.name] + words)
    return {
        "task": task["id"], "style": style, "split": task["split"], "symbol": "%s::%s" % (sym.path, sym.qualname),
        "path_in_pack_output": known,
        "R1a": pack_has(index, sym.qualname, task, sym),
        "R1b": pack_has(index, query + " " + sym.qualname, task, sym),
        "R2_top8": in_top(index, sym.name, sym, 8), "R2_top20": in_top(index, sym.name, sym, 20),
        "R3_top8": in_top(index, r3q, sym, 8), "R3_top20": in_top(index, r3q, sym, 20),
        "R4a": try_slice(index, sym, sym.qualname), "R4b": try_slice(index, sym, None),
        "R5": re.search(r"\b%s\b" % re.escape(sym.name), render_map(index, folder, MAP_BUDGET)) is not None,
        "R3_query": r3q,
    }


def collect() -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    indexes: Dict[str, RepoIndex] = {}
    for task in measure.load_tasks(None):
        if task["split"] not in SPLITS:
            continue
        index = indexes.setdefault(task["repo"], build_index(str(measure.REPOS_DIR / task["repo"])))
        budget, source, notes = resolve_budget(None, task["task"])
        for style in measure.styles_of(task, measure.STYLES):
            query = measure.query_of(task, style)
            result = pack_context(index, query, budget, source, task["task"], notes=notes)
            for entry in task["must_include"]:
                if entry["need"] != "full":
                    continue
                for sym in measure.symbols_for(index, entry["symbol"])[:1]:
                    if not measure.covered(result, sym, ("FULL",)):
                        rows.append(one_miss(index, task, style, query, result, sym))
    return rows


COLUMNS = (("R1a", "R1a pack, name alone"), ("R1b", "R1b pack, task words + name"),
           ("R2_top8", "R2 find name, top 8"), ("R2_top20", "R2 find name, top 20"),
           ("R3_top8", "R3 find name + 2 words, top 8"), ("R3_top20", "R3 find name + 2 words, top 20"),
           ("R4a", "R4a slice path:Class.method (path known)"), ("R4b", "R4b slice outline (path known)"),
           ("R5", "R5 map folder lists name"))


def count(rows: List[Dict[str, object]], key: str) -> Tuple[int, int]:
    pool = [r for r in rows if r["path_in_pack_output"]] if key.startswith("R4") else rows
    return sum(1 for r in pool if r[key]), len(pool)


def table(rows: List[Dict[str, object]], title: str) -> List[str]:
    out = ["### %s (%d misses, %d unique symbols)" % (title, len(rows), len({r["symbol"] for r in rows})), "",
           "| path | success | n |", "|---|---|---|"]
    for key, label in COLUMNS:
        hit, total = count(rows, key)
        out.append("| %s | %d (%s) | %d |" % (label, hit, "n/a" if not total else "%.0f%%" % (100.0 * hit / total), total))
    out.append("")
    return out


def render(rows: List[Dict[str, object]]) -> str:
    out = ["# Recovery paths for symbols that pack missed", "",
           "Question: when `pack.py` does not deliver a needed function in full, which follow-up finds it? Every `need: full` label that was not delivered as FULL (dev, dev2, holdout2; each query style counted separately, so one symbol can appear twice) was tried with each path below on the frozen scripts. The query words for R3 are the first two content words of the task query. R4 only applies when the file path appeared somewhere in the pack output (a FULL, OUTLINE or MENTION section, or the OMITTED line); the agent otherwise would not know the path. A success means the symbol's code (R1, R4a), name (R2, R3, R4b, R5) appeared as described.",
           "Small n: read counts, not percentages. R1a and R4 use the exact qualified name from the answer key (R4 also needs the true file path), so they are best cases; the bare method name alone was not measured for pack. R1b appends the name to a query that had already failed (the agent-style queries often already contained the bare name), so R1b does not show that adding a name to a keyword list is generally worse. This measurement was run on the frozen code after holdout2 and tunes nothing; it only decides what the guidance text recommends. holdout2 misses are included here, which does not change any label or code.", ""]
    out += table(rows, "All misses")
    for split in SPLITS:
        out += table([r for r in rows if r["split"] == split], "Split: " + split)
    for style in ("naive", "agent", "legacy"):
        part = [r for r in rows if r["style"] == style]
        if part:
            out += table(part, "Query style: " + style)
    out += ["### Per miss", "", "| task | style | symbol | path known | " + " | ".join(k for k, _ in COLUMNS) + " |",
            "|---|---|---|---|" + "---|" * len(COLUMNS)]
    for r in rows:
        out.append("| %s | %s | %s | %s | " % (r["task"], r["style"], r["symbol"], "yes" if r["path_in_pack_output"] else "no")
                   + " | ".join("yes" if r[k] else "no" for k, _ in COLUMNS) + " |")
    return "\n".join(out) + "\n"


def main(argv: Optional[List[str]] = None) -> int:
    rows = collect()
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "recovery_paths.json").write_text(json.dumps(rows, indent=1, sort_keys=True), encoding="utf-8")
    (RESULTS / "recovery_paths.md").write_text(render(rows), encoding="utf-8")
    print("misses:", len(rows))
    for key, label in COLUMNS:
        hit, total = count(rows, key)
        print("%-45s %d/%d" % (label, hit, total))
    return 0


if __name__ == "__main__":
    sys.exit(main())
