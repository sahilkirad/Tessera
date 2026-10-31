"""PageRank over the import graph and the budgeted repository map."""
from __future__ import annotations

import ast
import math
import os
import re
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

from _core import (
    MAX_OMITTED_ITEMS, MAX_WARNINGS, TASK_BUDGETS, estimate_tokens, footer, next_budget, padded,
    printed_cost, raw_units, read_text, units_to_tokens,
)
from _index import FileIndex, RepoIndex, Symbol, render_class_outline, render_outline, resolve_rec

MAX_MAP_NAMES = 8
MAX_OMITTED_GROUPS = 5


def pagerank(nodes: Iterable[str], edges: Iterable[Tuple[str, str]],
             d: float = 0.85, iters: int = 30) -> Dict[str, float]:
    """PageRank where an edge (a, b) means a imports b, so rank flows to b."""
    order = sorted(set(nodes))
    count = len(order)
    if count == 0:
        return {}
    known = set(order)
    out: Dict[str, Set[str]] = {n: set() for n in order}
    for src, dst in edges:
        if src in known and dst in known and src != dst:
            out[src].add(dst)
    links = {n: sorted(out[n]) for n in order}
    rank = {n: 1.0 / count for n in order}
    for _ in range(iters):
        dangling = sum(rank[n] for n in order if not links[n])
        fresh = {n: (1.0 - d) / count + d * dangling / count for n in order}
        for n in order:
            for target in links[n]:
                fresh[target] += d * rank[n] / len(links[n])
        rank = fresh
    return rank


def file_ranks(index: RepoIndex) -> Dict[str, float]:
    """PageRank score per indexed file."""
    return pagerank(index.files, index.file_edges())


def imported_by_counts(index: RepoIndex) -> Dict[str, int]:
    """Number of distinct repo files that import each file."""
    counts: Dict[str, int] = {path: 0 for path in index.files}
    for _, dst in index.file_edges():
        counts[dst] = counts.get(dst, 0) + 1
    return counts


def _name_tokens(fi: FileIndex) -> List[Tuple[str, str]]:
    """Ordered ('class'|'method'|'def', name) tokens for the map; dunder methods are skipped."""
    kids: Dict[str, List[Symbol]] = {}
    for sym in fi.symbols:
        if "." in sym.qualname:
            kids.setdefault(sym.qualname.rpartition(".")[0], []).append(sym)
    tokens: List[Tuple[str, str]] = []
    for sym in fi.symbols:
        if "." in sym.qualname:
            continue
        if sym.kind == "class":
            tokens.append(("class", sym.name))
            tokens.extend(("method", k.name) for k in kids.get(sym.qualname, [])
                          if not (k.name.startswith("__") and k.name.endswith("__")))
        else:
            tokens.append(("def", sym.name))
    return tokens


def _name_lines(fi: FileIndex) -> List[str]:
    tokens = _name_tokens(fi)
    shown, rest = tokens[:MAX_MAP_NAMES], len(tokens) - MAX_MAP_NAMES
    lines: List[str] = []
    for kind, name in shown:
        if kind == "class":
            lines.append("  class " + name)
        elif kind == "method":
            lines[-1] += (": " if lines[-1].count(":") == 0 else ", ") + name
        elif lines and lines[-1].startswith("  def "):
            lines[-1] += ", " + name
        else:
            lines.append("  def " + name)
    if rest > 0:
        lines.append("  (+%d more)" % rest)
    return lines


def _omitted_summary(paths: List[str], base: str) -> str:
    groups: Dict[str, int] = {}
    for path in paths:
        rel = path[len(base):] if base else path
        key = rel.split("/", 1)[0] + "/" if "/" in rel else "(root)"
        groups[key] = groups.get(key, 0) + 1
    ranked = sorted(groups.items(), key=lambda kv: (-kv[1], kv[0]))
    shown = ["%s %d" % kv for kv in ranked[:MAX_OMITTED_GROUPS]]
    if len(ranked) > MAX_OMITTED_GROUPS:
        shown.append("...")
    return "%d files (%s); narrow with `map.py <folder>`" % (len(paths), ", ".join(shown))


def render_map(index: RepoIndex, focus: str, budget: int) -> str:
    """Files from highest PageRank down, never above `budget` estimated tokens (with margin)."""
    base = focus.strip("/") + "/" if focus.strip("/") else ""
    scope = [p for p in index.files if p.startswith(base)]
    ranks = file_ranks(index)
    counts = imported_by_counts(index)
    scope.sort(key=lambda p: (-round(ranks.get(p, 0.0), 12), p))
    blocks = [["%s  imported_by=%d loc=%d" % (p, counts.get(p, 0), index.files[p].loc)]
              + _name_lines(index.files[p]) for p in scope]
    name = os.path.basename(index.root.rstrip("/\\")) or index.root
    extra = (" focus=" + base if base else "") + (" PARTIAL" if index.partial else "")

    def compose(shown: int, tokens: int) -> str:
        head = "MAP root=%s files=%d shown=%d tokens~%d (estimate)%s" % (
            name, len(scope), shown, tokens, extra)
        omitted = [_omitted_summary(scope[shown:], base)] if shown < len(scope) else []
        tail = footer(omitted, index.warnings)
        return "\n".join([head] + [line for block in blocks[:shown] for line in block]
                         + ([tail] if tail else []))

    def settle(shown: int) -> str:
        tokens = 0
        for _ in range(4):
            text = compose(shown, tokens)
            fresh = estimate_tokens(text)
            if fresh == tokens:
                return text
            tokens = fresh
        return compose(shown, tokens)

    best = ""
    for shown in range(len(scope) + 1):
        text = settle(shown)
        if printed_cost(text) > budget:
            break
        best = text
    if best:
        return best
    return "MAP root=%s files=%d shown=0 (estimate)\nOMITTED: all files; raise --budget" % (name, len(scope))


# ------------------------------------------------------------ keyword ranking

WEIGHT_NAME = 3.0
WEIGHT_QUALIFIER = 3.0
WEIGHT_PATH = 2.0
WEIGHT_PARAM = 1.0
WEIGHT_DOC = 1.0
PREFIX_FACTOR = 0.8
PREFIX_MIN_CHARS = 4
TEST_DEMOTION = 0.5
TEST_MODE_DEMOTION = 0.65
HIGH_SCORE = 0.25
MEDIUM_SCORE = 0.12
RARE_DF_FRACTION = 0.05
GENERIC_DF_FRACTION = 0.20
GENERIC_MIN_SYMBOLS = 30
VOCAB_DF_FRACTION = 0.20
VOCAB_SIZE = 30
STOPWORDS = frozenset({
    "the", "an", "of", "to", "and", "for", "in", "is", "on", "or", "it", "be", "as", "at", "by",
    "with", "from", "this", "that", "are", "was", "what", "where", "how", "does", "do",
})
_WORD_RE = re.compile(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|[0-9]+")
_UNICODE_WORD_RE = re.compile(r"[^\W\d_]+|\d+")
_SPLIT_RE = re.compile(r"[\W_]+")


def tokenize(text: str) -> List[str]:
    """Lowercase tokens split on camelCase, snake_case, digits and punctuation."""
    out: List[str] = []
    for chunk in _SPLIT_RE.split(text):
        if not chunk:
            continue
        parts = _WORD_RE.findall(chunk) if chunk.isascii() else _UNICODE_WORD_RE.findall(chunk)
        out.extend(t for t in (p.lower() for p in parts) if len(t) >= 2 and t not in STOPWORDS)
    return out


def is_test_path(path: str) -> bool:
    """tests/ or test/ directory, `test_*.py`, or `*_test.py`."""
    parts = path.split("/")
    name = parts[-1]
    return (any(p in ("tests", "test") for p in parts[:-1])
            or name.startswith("test_") or name.endswith("_test.py"))


@dataclass
class Hit:
    symbol: Symbol
    score: float
    matched: List[str]
    name_matched: List[str]


@dataclass
class RankResult:
    terms: List[str]
    hits: List[Hit]
    confidence: str
    matched: List[str]
    unmatched: List[str]
    vocabulary: List[str]


def _symbol_tokens(sym: Symbol) -> Dict[str, float]:
    """token -> best field weight for one symbol."""
    best: Dict[str, float] = {}
    fields = ((WEIGHT_NAME, sym.name), (WEIGHT_QUALIFIER, sym.qualname.rpartition(".")[0]),
              (WEIGHT_PATH, sym.path[:-3] if sym.path.endswith(".py") else sym.path),
              (WEIGHT_PARAM, " ".join(sym.params)), (WEIGHT_DOC, sym.doc))
    for weight, text in fields:
        for tok in tokenize(text):
            if best.get(tok, 0.0) < weight:
                best[tok] = weight
    return best


def vocabulary_hint(index: RepoIndex, tokens: List[Dict[str, float]], symbols: List[Symbol]) -> List[str]:
    """Up to 30 name terms, weighted by file PageRank, skipping terms in over 20% of symbols."""
    ranks = file_ranks(index)
    df: Dict[str, int] = {}
    weight: Dict[str, float] = {}
    for sym, toks in zip(symbols, tokens):
        for tok in toks:
            df[tok] = df.get(tok, 0) + 1
        if sym.name.startswith("__"):
            continue
        for tok in set(tokenize(sym.name)):
            weight[tok] = weight.get(tok, 0.0) + ranks.get(sym.path, 0.0)
    limit = VOCAB_DF_FRACTION * len(symbols)
    usable = [(-round(w, 12), tok) for tok, w in weight.items() if df.get(tok, 0) <= limit and len(tok) >= 3]
    return [tok for _, tok in sorted(usable)[:VOCAB_SIZE]]


def _confidence(top: Optional[Hit], terms: List[str], df: Dict[str, int], n_symbols: int) -> str:
    if top is None or top.score < MEDIUM_SCORE:
        return "LOW"
    if n_symbols >= GENERIC_MIN_SYMBOLS and all(df[t] > GENERIC_DF_FRACTION * n_symbols for t in top.matched):
        return "LOW"
    if top.score >= HIGH_SCORE:
        if len(top.matched) >= 2:
            return "HIGH"
        if len(terms) == 1 and top.name_matched and df[terms[0]] <= RARE_DF_FRACTION * n_symbols:
            return "HIGH"
    return "MEDIUM"


def rank_symbols(index: RepoIndex, terms: List[str], include_tests: bool = False,
                 test_factor: Optional[float] = None) -> RankResult:
    """Weighted keyword search over symbol names, paths, parameters and docstrings.

    Test files are demoted by TEST_DEMOTION; `include_tests` lifts the demotion, or replaces it
    with `test_factor` when one is given.
    """
    test_scale = TEST_DEMOTION if not include_tests else (1.0 if test_factor is None else test_factor)
    terms = list(dict.fromkeys(terms))
    symbols = [s for fi in (index.files[p] for p in sorted(index.files)) for s in fi.symbols]
    tokens = [_symbol_tokens(s) for s in symbols]
    n = len(symbols)
    postings: Dict[str, Dict[int, float]] = {}
    for sid, toks in enumerate(tokens):
        for tok, weight in toks.items():
            postings.setdefault(tok, {})[sid] = weight
    best: Dict[int, Dict[str, float]] = {}
    name_hit: Dict[int, Set[str]] = {}
    df: Dict[str, int] = {}
    idf: Dict[str, float] = {}
    for term in terms:
        found: Dict[int, float] = {}
        for tok, plist in postings.items():
            factor = 1.0 if tok == term else (
                PREFIX_FACTOR if len(term) >= PREFIX_MIN_CHARS and tok.startswith(term) else 0.0)
            if factor:
                for sid, weight in plist.items():
                    if weight * factor > found.get(sid, 0.0):
                        found[sid] = weight * factor
                    if weight >= WEIGHT_NAME:
                        name_hit.setdefault(sid, set()).add(term)
        df[term] = len(found)
        idf[term] = math.log(1.0 + n / (1.0 + len(found)))
        for sid, value in found.items():
            best.setdefault(sid, {})[term] = value
    seen_terms = [t for t in terms if df[t] > 0]
    denom = WEIGHT_NAME * math.log(1.0 + n) * max(1, len(seen_terms)) if n else 1.0
    hits: List[Hit] = []
    for sid, per_term in best.items():
        score = min(1.0, sum(idf[t] * v for t, v in per_term.items()) / denom)
        if test_scale < 1.0 and is_test_path(symbols[sid].path):
            score *= test_scale
        hits.append(Hit(symbols[sid], score, [t for t in terms if t in per_term],
                        [t for t in terms if t in name_hit.get(sid, ())]))
    hits.sort(key=lambda h: (-round(h.score, 6), h.symbol.path, h.symbol.start))
    top = hits[0] if hits else None
    confidence = _confidence(top, terms, df, n)
    return RankResult(terms, hits, confidence, seen_terms, [t for t in terms if df[t] == 0],
                      vocabulary_hint(index, tokens, symbols) if confidence == "LOW" else [])


def _one_line(signature: str) -> str:
    return " ".join(signature.split())


def render_find(query: str, result: RankResult, top: int, warnings: List[str]) -> str:
    """Text output of find.py (exact formats in docs/TOOL_SPECS.md)."""
    if result.confidence == "LOW":
        vocab = ", ".join(result.vocabulary) + (", ..." if result.vocabulary else "")
        lines = ['FIND "%s" confidence=LOW' % query,
                 "No strong match. Repo vocabulary: %s" % (vocab or "(none)"),
                 "Retry with 3-6 identifier-like words from this vocabulary (max 2 retries), "
                 "then use `map.py <folder>`."]
        tail = footer([], warnings)
        return "\n".join(lines + ([tail] if tail else []))
    unmatched = " (unmatched: %s)" % ", ".join(result.unmatched) if result.unmatched else ""
    lines = ['FIND "%s" confidence=%s matched=%d/%d terms%s' % (
        query, result.confidence, len(result.matched), len(result.terms), unmatched)]
    for rank, hit in enumerate(result.hits[:top], 1):
        sym = hit.symbol
        lines.append("%d  %.2f  %s::%s  L%d-%d" % (rank, hit.score, sym.path, sym.qualname, sym.start, sym.end))
        lines.append("        " + _one_line(sym.signature))
    rest = len(result.hits) - top
    omitted = ["%d lower-scoring matches (use --top %d)" % (rest, max(top + 1, top * 5 // 2))] if rest > 0 else []
    tail = footer(omitted, warnings)
    return "\n".join(lines + ([tail] if tail else []))


def find_payload(result: RankResult, top: int, warnings: List[str]) -> Dict[str, object]:
    """JSON-ready mirror of the find output."""
    shown = [] if result.confidence == "LOW" else result.hits[:top]
    rest = 0 if result.confidence == "LOW" else max(0, len(result.hits) - top)
    return {
        "confidence": result.confidence,
        "matched": result.matched,
        "unmatched": result.unmatched,
        "results": [{"rank": i, "score": round(h.score, 4), "path": h.symbol.path,
                     "qualname": h.symbol.qualname, "start": h.symbol.start, "end": h.symbol.end,
                     "signature": _one_line(h.symbol.signature)} for i, h in enumerate(shown, 1)],
        "vocabulary": result.vocabulary,
        "omitted": ["%d lower-scoring matches" % rest] if rest else [],
        "warnings": warnings,
    }


# ------------------------------------------------------------------------ deps

HOP_WEIGHTS = {1: 1.0, 2: 0.6, 3: 0.3}
DEFAULT_DEPTH = 2
MAX_DEPTH = 3
MAX_LISTED = 30
MAX_EDGE_NAMES = 6


@dataclass
class DepsResult:
    start: str
    depth: int
    levels: Dict[str, int]
    order: List[str]
    names: Dict[Tuple[str, str], List[str]]
    tree: Dict[str, List[Tuple[str, bool]]]
    external: List[str]
    unresolved: List[str]
    beyond: int


def _targets(index: RepoIndex, path: str) -> Dict[str, List[str]]:
    """Internal import targets of a file in import order, with the names imported from each."""
    merged: Dict[str, List[str]] = {}
    for edge in index.edges.get(path, []):
        if edge.kind == "internal" and edge.target is not None:
            names = merged.setdefault(edge.target, [])
            names.extend(n for n in edge.names if n not in names)
    return merged


def deps_bfs(index: RepoIndex, start: str, depth: int = DEFAULT_DEPTH) -> DepsResult:
    """Cycle-safe breadth-first walk of repo imports; depth is capped at 3."""
    depth = max(1, min(depth, MAX_DEPTH))
    levels = {start: 0}
    order: List[str] = []
    names: Dict[Tuple[str, str], List[str]] = {}
    tree: Dict[str, List[Tuple[str, bool]]] = {}
    external: Set[str] = set()
    unresolved: Set[str] = set()
    leaf_targets: Set[str] = set()
    queue = deque([start])
    while queue:
        node = queue.popleft()
        for edge in index.edges.get(node, []):
            if edge.kind == "external":
                external.add(edge.module)
            elif edge.kind == "unresolved":
                unresolved.add(edge.module)
        targets = _targets(index, node)
        if levels[node] >= depth:
            leaf_targets.update(targets)
            continue
        kids: List[Tuple[str, bool]] = []
        for target, imported in targets.items():
            if target in levels:
                kids.append((target, False))
                continue
            levels[target] = levels[node] + 1
            order.append(target)
            names[(node, target)] = imported
            kids.append((target, True))
            queue.append(target)
        tree[node] = kids
    return DepsResult(start, depth, levels, order, names, tree, sorted(external), sorted(unresolved),
                      len([t for t in leaf_targets if t not in levels]))


def reverse_deps(index: RepoIndex, target: str) -> List[str]:
    """Sorted repo files that import `target` (file level only)."""
    return sorted({src for src, dst in index.file_edges() if dst == target})


def _name_list(names: List[str]) -> str:
    if not names:
        return "module"
    shown = names[:MAX_EDGE_NAMES]
    return ", ".join(shown) + (", +%d" % (len(names) - MAX_EDGE_NAMES) if len(names) > MAX_EDGE_NAMES else "")


def render_deps(result: DepsResult, warnings: List[str]) -> str:
    """Text output of deps.py."""
    lines = ["DEPS %s depth=%d" % (result.start, result.depth)]

    def walk(node: str, indent: str) -> None:
        for child, is_new in result.tree.get(node, []):
            if is_new:
                lines.append("%sL%d  %s  (%s)  w=%.1f" % (
                    indent, result.levels[child], child, _name_list(result.names[(node, child)]),
                    HOP_WEIGHTS[result.levels[child]]))
                walk(child, indent + "  ")
            else:
                lines.append("%sL%d  %s  (already shown)" % (indent, result.levels[node] + 1, child))

    walk(result.start, "")
    outside = result.external + ["%s (unresolved)" % u for u in result.unresolved]
    if outside:
        lines.append("EXTERNAL/UNRESOLVED: " + ", ".join(
            outside[:MAX_OMITTED_ITEMS] + (["+%d more" % (len(outside) - MAX_OMITTED_ITEMS)]
                                           if len(outside) > MAX_OMITTED_ITEMS else [])))
    omitted = ["%d files beyond depth %d (use --depth %d)" % (
        result.beyond, result.depth, result.depth + 1)] if result.beyond and result.depth < MAX_DEPTH else []
    if result.beyond and result.depth >= MAX_DEPTH:
        omitted = ["%d files beyond depth %d (follow with deps.py on a listed file)" % (result.beyond, result.depth)]
    tail = footer(omitted, warnings)
    return "\n".join(lines + ([tail] if tail else []))


def render_reverse(target: str, importers: List[str], warnings: List[str]) -> str:
    """Text output of deps.py --reverse."""
    lines = ["IMPORTED-BY %s (%d files)" % (target, len(importers))] + importers[:MAX_LISTED]
    omitted = ["%d more importers" % (len(importers) - MAX_LISTED)] if len(importers) > MAX_LISTED else []
    tail = footer(omitted, warnings)
    return "\n".join(lines + ([tail] if tail else []))


# ------------------------------------------------------------------------ pack

FULL, OUTLINE, MENTION, TRUNCATED = "FULL", "OUTLINE", "MENTION", "TRUNCATED"
PRIORITY_SEED = 1.0
PRIORITY_EXTRA = 0.7
NEIGHBOR_FILL = 0.5
DOWNGRADE_MAX_SHARE = 0.2
EXTRA_HITS = 5
PRIORITY_REF = 0.8
PRIORITY_UBIQUITOUS = 0.45
UBIQUITOUS_SHARE = 0.03
UBIQUITOUS_MIN_FILES = 8
PRIORITY_CONTEXT = 0.6
PRIORITY_NEIGHBOR = 0.5
DEFAULT_SEEDS = 3
SEED_MIN_RATIO = 0.6
QUERY_SHOW = 60
FOOTER_CAPS = ((MAX_OMITTED_ITEMS, MAX_WARNINGS), (8, 3), (4, 2), (2, 1), (0, 0))
EMERGENCY = "PACK budget %d too small for any section; use find.py and slice.py"


@dataclass
class Cand:
    form: str
    path: str
    sym: Optional[Symbol]
    priority: float
    order: int
    names: List[str]
    seed_rank: int = 0


@dataclass
class Section:
    form: str
    path: str
    qualname: str
    start: int
    end: int
    text: str
    priority: float
    order: int
    raw: int = field(init=False, default=0)

    def __post_init__(self) -> None:
        self.raw = raw_units(self.text)


@dataclass
class Omission:
    name: str
    label: str
    priority: float
    counts: bool = True


@dataclass
class PackResult:
    text: str
    confidence: str
    task: Optional[str]
    budget_source: str
    budget: int
    seeds: List[str] = field(default_factory=list)
    sections: List[Section] = field(default_factory=list)
    omitted: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    tokens_used: int = 0
    budget_limited: bool = False
    suggested_budget: Optional[int] = None
    baseline_tokens: int = 0
    candidates: List[str] = field(default_factory=list)
    vocabulary: List[str] = field(default_factory=list)

    def to_json(self) -> Dict[str, object]:
        """Machine-readable mirror of the text bundle (used by tools/measure.py)."""
        return {
            "confidence": self.confidence, "task": self.task, "budget_source": self.budget_source,
            "sections": [{"form": s.form, "path": s.path, "qualname": s.qualname, "start": s.start,
                          "end": s.end, "tokens": max(1, units_to_tokens(s.raw))} for s in self.sections],
            "omitted": self.omitted, "warnings": self.warnings, "tokens_used": self.tokens_used,
            "budget": self.budget, "budget_limited": self.budget_limited,
            "suggested_budget": self.suggested_budget, "baseline_tokens": self.baseline_tokens,
            "candidates": self.candidates, "vocabulary": self.vocabulary,
        }


class _Source:
    """Lazy per-file line cache and whole-file token estimates."""

    def __init__(self, index: RepoIndex) -> None:
        self.index = index
        self._lines: Dict[str, List[str]] = {}
        self._tokens: Dict[str, int] = {}

    def lines(self, path: str) -> List[str]:
        if path not in self._lines:
            self._lines[path] = read_text(Path(self.index.root, *path.split("/"))).split("\n")
        return self._lines[path]

    def file_tokens(self, path: str) -> int:
        if path not in self._tokens:
            self._tokens[path] = estimate_tokens("\n".join(self.lines(path)))
        return self._tokens[path]


def _top_symbol(index: RepoIndex, path: str, name: str) -> Optional[Symbol]:
    for sym in index.files[path].symbols:
        if sym.qualname == name and sym.kind in ("class", "function"):
            return sym
    return None


def _bindings(index: RepoIndex, path: str) -> Dict[str, Tuple[str, Optional[str]]]:
    """Local name -> (repo file, imported symbol name, or None when the name is a module)."""
    out: Dict[str, Tuple[str, Optional[str]]] = {}
    for rec in index.files[path].imports:
        for edge in resolve_rec(index, path, rec):
            if edge.kind != "internal" or edge.target is None:
                continue
            if rec.level == 0 and not rec.names:
                if "." not in rec.module or rec.aliases[0] != rec.module.split(".")[0]:
                    out[rec.aliases[0]] = (edge.target, None)
                continue
            for name, alias in zip(rec.names, rec.aliases):
                if name in edge.names:
                    out[alias] = (edge.target, name)
                elif not edge.names and edge.module.rpartition(".")[2] == name:
                    out[alias] = (edge.target, None)
    return out


def _parse_snippet(raw: str) -> Optional[ast.AST]:
    try:
        return ast.parse(raw if not raw[:1].isspace() else "class _:\n" + raw)
    except Exception:  # snippet cut out of a larger file; any failure just skips context
        return None


def seed_names(src: _Source, sym: Symbol) -> Tuple[Set[str], Set[str], Set[Tuple[str, str]]]:
    """Identifiers used in a symbol, its `self.x()`/`cls.x()` method names, and `name.attr()` calls."""
    tree = _parse_snippet("\n".join(src.lines(sym.path)[sym.start - 1:sym.end]))
    names: Set[str] = set()
    own: Set[str] = set()
    attrs: Set[Tuple[str, str]] = set()
    if tree is None:
        return names, own, attrs
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)):
            base, attr = node.func.value.id, node.func.attr
            if base not in ("self", "cls"):
                attrs.add((base, attr))
        if (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
                and node.value.id in ("self", "cls")):
            own.add(node.attr)
    return names, own, attrs


def _base_names(cls: Symbol) -> List[str]:
    try:
        tree = ast.parse(cls.signature + ":\n    pass")
    except Exception:
        return []
    node = tree.body[0]
    out = []
    for base in getattr(node, "bases", []):
        if isinstance(base, ast.Name):
            out.append(base.id)
        elif isinstance(base, ast.Attribute):
            out.append(base.attr)
    return out


def _resolve_base(index: RepoIndex, cls: Symbol, name: str,
                  binds: Dict[str, Tuple[str, Optional[str]]]) -> Optional[Symbol]:
    for sym in index.files[cls.path].symbols:
        if sym.kind == "class" and sym.qualname == name and sym is not cls:
            return sym
    if name in binds and binds[name][1] is not None:
        target = _top_symbol(index, binds[name][0], binds[name][1] or "")
        if target is not None and target.kind == "class":
            return target
    named = [s for fi in index.files.values() for s in fi.symbols if s.kind == "class" and s.name == name]
    return named[0] if len(named) == 1 and named[0] is not cls else None


def _enclosing_class(index: RepoIndex, sym: Symbol) -> Optional[Symbol]:
    parent = sym.qualname.rpartition(".")[0]
    if sym.kind == "class":
        return sym
    return next((s for s in index.files[sym.path].symbols if s.kind == "class" and s.qualname == parent), None)


def _importer_counts(index: RepoIndex) -> Dict[str, int]:
    """Imported name -> number of repo files that import it by name."""
    counts: Dict[str, int] = {}
    for fi in index.files.values():
        for name in {n for rec in fi.imports for n in rec.names}:
            counts[name] = counts.get(name, 0) + 1
    return counts


def _ref_priority(index: RepoIndex, target: Symbol, terms: Set[str], counts: Dict[str, int]) -> float:
    """PRIORITY_REF, lowered for helpers imported by many files unless the query names them."""
    crowd = counts.get(target.name, 0)
    if crowd < max(UBIQUITOUS_MIN_FILES, UBIQUITOUS_SHARE * len(index.files)):
        return PRIORITY_REF
    words = set(tokenize(target.name)) | set(tokenize(target.path.rpartition("/")[2][:-3]))
    if any(t in words or (len(t) >= PREFIX_MIN_CHARS and any(w.startswith(t) for w in words)) for t in terms):
        return PRIORITY_REF
    return PRIORITY_UBIQUITOUS


def _build_candidates(index: RepoIndex, seeds: List[Symbol], depth: int, src: _Source,
                      extras: Optional[List[Symbol]] = None,
                      terms: Optional[Set[str]] = None) -> List[Cand]:
    cands: List[Cand] = []
    counts = _importer_counts(index)

    def add(form: str, path: str, sym: Optional[Symbol], priority: float,
            names: Optional[List[str]] = None, seed_rank: int = 0) -> None:
        cands.append(Cand(form, path, sym, priority, len(cands), names or [], seed_rank))

    for rank, seed in enumerate(seeds, 1):
        add(FULL, seed.path, seed, PRIORITY_SEED, seed_rank=rank)
    for extra in extras or []:
        add(FULL, extra.path, extra, PRIORITY_EXTRA)
    for seed in seeds:
        binds = _bindings(index, seed.path)
        used, own, attrs = seed_names(src, seed)
        for alias in sorted(used & set(binds)):
            path, name = binds[alias]
            target = _top_symbol(index, path, name) if name is not None else None
            if target is not None:
                add(FULL, path, target, _ref_priority(index, target, terms or set(), counts))
            elif name is None:
                add(OUTLINE, path, None, PRIORITY_NEIGHBOR)
        cls = _enclosing_class(index, seed)
        if seed.kind == "method" and cls is not None:
            for sym in index.files[seed.path].symbols:
                if sym.kind == "method" and sym.qualname == cls.qualname + "." + sym.name and sym.name in own:
                    add(FULL, sym.path, sym, PRIORITY_CONTEXT)
        if cls is not None:
            for base in _base_names(cls):
                found = _resolve_base(index, cls, base, binds)
                if found is not None:
                    add(FULL, found.path, found, PRIORITY_CONTEXT)
        for base, attr in sorted(attrs):
            hit = binds.get(base)
            if hit is not None and hit[1] is None:
                target = _top_symbol(index, hit[0], attr)
                if target is not None:
                    add(FULL, target.path, target, PRIORITY_CONTEXT)
        deps = deps_bfs(index, seed.path, depth)
        for path in deps.order:
            level = deps.levels[path]
            parent_names = next((n for (p, c), n in deps.names.items() if c == path), [])
            add(MENTION if level >= 3 else OUTLINE, path, None, PRIORITY_NEIGHBOR * HOP_WEIGHTS[level],
                parent_names)
    return cands


def _cand_key(c: Cand) -> Tuple[object, ...]:
    if c.form == FULL and c.sym is not None:
        return (FULL, c.path, c.sym.qualname, c.sym.start)
    return (c.form, c.path)


def _dedupe(cands: List[Cand]) -> List[Cand]:
    """Keep the highest-priority copy of each item, in discovery order."""
    best: Dict[Tuple[object, ...], Cand] = {}
    for cand in cands:
        key = _cand_key(cand)
        if key not in best or cand.priority > best[key].priority:
            best[key] = cand
    return sorted(best.values(), key=lambda c: c.order)


def _sort_key(sec: Section) -> Tuple[str, int, int, str]:
    return (sec.path, sec.start, sec.end, sec.form)


def _limited_line(limited: List[Omission], budget: int) -> str:
    if not limited:
        return ""
    head = "BUDGET-LIMITED: %d relevant items omitted (%s)." % (
        len(limited), ", ".join(o.name for o in limited[:3]))
    nxt = next_budget(budget)
    if nxt is None:
        return head + " At the hard cap; use slice.py."
    task = {v: k for k, v in TASK_BUDGETS.items()}.get(nxt)
    rerun = "--task %s or --budget %d" % (task, nxt) if task else "--budget %d" % nxt
    return head + " Rerun with %s, or use slice.py." % rerun


class _Packer:
    """Greedy, budget-exact assembly of a pack bundle."""

    def __init__(self, index: RepoIndex, src: _Source, budget: int, head: str,
                 warnings: List[str]) -> None:
        self.index, self.src, self.budget, self.head, self.warnings = index, src, budget, head, warnings

    def render(self, sections: List[Section], omitted: List[Omission],
               caps: Tuple[int, int] = FOOTER_CAPS[0]) -> Tuple[str, int, int]:
        """(text, tokens_used, baseline_tokens) with the real footer and a settled token count."""
        files = {s.path for s in sections}
        baseline = sum(self.src.file_tokens(p) for p in files)
        limited = _limited_line([o for o in omitted if o.counts and o.priority >= PRIORITY_NEIGHBOR], self.budget)
        body = [s.text for s in sorted(sections, key=_sort_key)]
        tail = footer([o.label for o in omitted], self.warnings, caps[0], caps[1])
        fixed = [self.head] + body + ([tail] if tail else []) + ([limited] if limited else [])
        # Token estimates are additive over newline-joined parts, so only the stats line is re-counted.
        fixed_raw = raw_units(self.head) + sum(s.raw for s in sections) + len(fixed)
        fixed_raw += (raw_units(tail) if tail else 0) + (raw_units(limited) if limited else 0)

        def stats(tokens: int) -> str:
            saved = max(0, round((1 - tokens / baseline) * 100)) if baseline else 0
            return "TOKENS: ~%d / %d (estimate). Whole contributing files ~%d, saved ~%d%% (estimate)" % (
                tokens, self.budget, baseline, saved)

        tokens = 0
        for _ in range(5):
            line = stats(tokens)
            fresh = max(1, units_to_tokens(fixed_raw + raw_units(line)))
            if fresh == tokens:
                break
            tokens = fresh
        return "\n".join(fixed + [stats(tokens)]), tokens, baseline

    def fits(self, sections: List[Section], omitted: List[Omission]) -> bool:
        return padded(self.render(sections, omitted)[1] + 1) <= self.budget


def _full_section(src: _Source, sym: Symbol, priority: float, order: int) -> Section:
    code = "\n".join(src.lines(sym.path)[sym.start - 1:sym.end])
    text = "=== FULL %s::%s L%d-%d\n%s" % (sym.path, sym.qualname, sym.start, sym.end, code)
    return Section(FULL, sym.path, sym.qualname, sym.start, sym.end, text, priority, order)


def _truncated_section(src: _Source, sym: Symbol, shown: int, priority: float, order: int) -> Section:
    lines = src.lines(sym.path)[sym.start - 1:sym.start - 1 + shown]
    last = sym.start + shown - 1
    head = "=== TRUNCATED %s::%s L%d-%d of L%d-%d" % (sym.path, sym.qualname, sym.start, last, sym.start, sym.end)
    tail = "TRUNCATED (lines %d-%d of %d-%d): use slice %s:%d-%d" % (
        sym.start, last, sym.start, sym.end, sym.path, last + 1, sym.end)
    return Section(TRUNCATED, sym.path, sym.qualname, sym.start, last, "\n".join([head] + lines + [tail]),
                   priority, order)


def _outline_section(index: RepoIndex, cand: Cand, sym: Optional[Symbol]) -> Section:
    """File outline, or the enclosing class outline when `sym` is given."""
    fi = index.files[cand.path]
    cls = _enclosing_class(index, sym) if sym is not None else None
    if cls is not None:
        text = "=== OUTLINE %s::%s\n%s" % (cand.path, cls.qualname, render_class_outline(fi, cls.qualname))
        return Section(OUTLINE, cand.path, cls.qualname, cls.start, cls.end, text, cand.priority, cand.order)
    body = render_outline(fi)
    text = "=== OUTLINE %s" % cand.path + ("\n" + body if body else "")
    return Section(OUTLINE, cand.path, "", 0, fi.loc, text, cand.priority, cand.order)


def _mention_section(index: RepoIndex, cand: Cand) -> Section:
    fi = index.files[cand.path]
    detail = ", ".join(cand.names[:MAX_EDGE_NAMES]) if cand.names else "%d symbols" % len(fi.symbols)
    text = "=== MENTION %s  (%s)" % (cand.path, detail)
    return Section(MENTION, cand.path, "", 0, fi.loc, text, cand.priority, cand.order)


def _cand_name(cand: Cand) -> str:
    return "%s::%s" % (cand.path, cand.sym.qualname) if cand.sym is not None else cand.path


def _section_key(sec: Section) -> Tuple[str, str, str, int]:
    return (sec.form, sec.path, sec.qualname, sec.start)


def _header(query: str, confidence: str, budget: int, source: str, task: Optional[str],
            seeds: List[str], partial: bool) -> str:
    shown = query if len(query) <= QUERY_SHOW else query[:QUERY_SHOW - 3] + "..."
    label = {"task": "task %s" % task, "explicit": "explicit", "default": "default", "clamped": "clamped"}[source]
    text = 'PACK "%s" confidence=%s budget=%d (%s)' % (shown, confidence, budget, label)
    if seeds:
        text += " seeds: " + ", ".join(seeds[:DEFAULT_SEEDS + 2])
    return text + (" PARTIAL" if partial else "")


def _low_result(index: RepoIndex, ranked: RankResult, query: str, budget: int, source: str,
                task: Optional[str], warnings: List[str]) -> PackResult:
    candidates = ["%s::%s" % (h.symbol.path, h.symbol.qualname) for h in ranked.hits[:3]]
    vocab = list(ranked.vocabulary)
    head = _header(query, "LOW", budget, source, task, [], index.partial)
    tail = footer([], warnings, *FOOTER_CAPS[2])
    advice = ("Retry with 3-6 identifier-like words from this vocabulary (max 2 retries), "
              "then use `map.py <folder>`.")

    def build(n_cand: int, n_vocab: int) -> str:
        lines = [head, "No strong match. Candidates (no code): " + (", ".join(candidates[:n_cand]) or "(none)")]
        if n_vocab:
            lines.append("Repo vocabulary: " + ", ".join(vocab[:n_vocab]) + (", ..." if n_vocab < len(vocab) else ""))
        lines.append(advice)
        return "\n".join(lines + ([tail] if tail else []))

    text = build(len(candidates), len(vocab))
    for n_cand, n_vocab in ((3, 20), (3, 10), (2, 5), (1, 0), (0, 0)):
        if printed_cost(text) <= budget:
            break
        text = build(min(n_cand, len(candidates)), min(n_vocab, len(vocab)))
    if printed_cost(text) > budget:
        text = _header(query[:20], "LOW", budget, source, task, [], False)
    return PackResult(text, "LOW", task, source, budget, warnings=warnings, tokens_used=estimate_tokens(text),
                      candidates=candidates, vocabulary=vocab)


def pack_context(index: RepoIndex, query: str, budget: int, source: str = "default",
                 task: Optional[str] = None, seeds: int = DEFAULT_SEEDS, depth: int = DEFAULT_DEPTH,
                 notes: Optional[List[str]] = None) -> PackResult:
    """Budgeted context bundle: seeds in full, referenced symbols, outlines of neighbours."""
    warnings = list(index.warnings) + list(notes or [])
    ranked = rank_symbols(index, tokenize(query), include_tests=(task == "test"),
                          test_factor=TEST_MODE_DEMOTION if task == "test" else None)
    if ranked.confidence == "LOW":
        return _low_result(index, ranked, query, budget, source, task, warnings)
    chosen: List[Symbol] = []
    extras: List[Symbol] = []
    floor = SEED_MIN_RATIO * ranked.hits[0].score
    for hit in ranked.hits:
        if hit.score < floor or (len(chosen) >= seeds and len(extras) >= EXTRA_HITS):
            break
        if hit.symbol in chosen or hit.symbol in extras:
            continue
        (chosen if len(chosen) < seeds else extras).append(hit.symbol)
    src = _Source(index)
    cands = _dedupe(_build_candidates(index, chosen, depth, src, extras, set(ranked.terms)))
    head = _header(query, ranked.confidence, budget, source, task, [s.qualname for s in chosen], index.partial)
    packer = _Packer(index, src, budget, head, warnings)
    included: List[Section] = []
    omitted: List[Omission] = []
    for cand in sorted(cands, key=lambda c: (-c.priority, c.order)):
        _place(packer, index, src, cand, included, omitted)
    return _finish(packer, index, ranked.confidence, task, source, budget, chosen, included, omitted, warnings)


def _place(packer: _Packer, index: RepoIndex, src: _Source, cand: Cand, included: List[Section],
           omitted: List[Omission]) -> None:
    """Add one candidate in the richest form that fits; otherwise record what was left out."""
    sym = cand.sym
    if cand.form == FULL and sym is not None:
        if any(s.form == FULL and s.path == cand.path and s.start <= sym.start and sym.end <= s.end
               for s in included):
            return
        forms = [("full", _full_section(src, sym, cand.priority, cand.order))]
        if cand.seed_rank == 1 and not packer.fits([forms[0][1]], omitted):
            if _place_truncated(packer, src, cand, included, omitted):
                return
        forms.append(("outline", _outline_section(index, cand, sym)))
    elif cand.form == OUTLINE:
        if any(s.path == cand.path for s in included):
            omitted.append(Omission(_cand_name(cand), cand.path + " (outline)", cand.priority, False))
            return
        forms = [("outline", _outline_section(index, cand, None)), ("mention", _mention_section(index, cand))]
    else:
        forms = [("mention", _mention_section(index, cand))]
    existing = {_section_key(s) for s in included}
    used = sum(s.raw for s in included)
    for number, (_, sec) in enumerate(forms):
        if _section_key(sec) in existing:
            return
        if cand.form != FULL and padded(units_to_tokens(used + sec.raw)) > NEIGHBOR_FILL * packer.budget:
            continue
        if cand.form == FULL and number > 0 and padded(units_to_tokens(sec.raw)) > DOWNGRADE_MAX_SHARE * packer.budget:
            continue
        trial_omitted = list(omitted)
        if cand.form == FULL and number > 0:
            trial_omitted.append(Omission(_cand_name(cand), _cand_name(cand) + " (outline only)", cand.priority))
        if packer.fits(included + [sec], trial_omitted):
            included.append(sec)
            omitted[:] = trial_omitted
            return
    label = _cand_name(cand) + ("" if cand.form == FULL else " (%s)" % cand.form.lower())
    omitted.append(Omission(_cand_name(cand), label, cand.priority, cand.form == FULL))


def _place_truncated(packer: _Packer, src: _Source, cand: Cand, included: List[Section],
                     omitted: List[Omission]) -> bool:
    """Top seed larger than the budget: signature plus as many body lines as fit, never an overflow."""
    sym = cand.sym
    assert sym is not None
    total = sym.end - sym.start + 1
    low, high, best = 1, total - 1, 0
    extra = omitted + [Omission(_cand_name(cand), _cand_name(cand) + " (truncated)", cand.priority)]
    while low <= high:
        mid = (low + high) // 2
        if packer.fits(included + [_truncated_section(src, sym, mid, cand.priority, cand.order)], extra):
            best, low = mid, mid + 1
        else:
            high = mid - 1
    if not best:
        return False
    included.append(_truncated_section(src, sym, best, cand.priority, cand.order))
    omitted[:] = extra
    return True


def _finish(packer: _Packer, index: RepoIndex, confidence: str, task: Optional[str], source: str,
            budget: int, chosen: List[Symbol], included: List[Section], omitted: List[Omission],
            warnings: List[str]) -> PackResult:
    """Repair loop: shrink footer caps, then drop the lowest-priority section, until it fits."""
    step = 0
    while True:
        text, tokens, baseline = packer.render(included, omitted, FOOTER_CAPS[step])
        if padded(tokens + 1) <= budget:
            break
        if step < len(FOOTER_CAPS) - 1:
            step += 1
            continue
        if not included:
            text, tokens, baseline = EMERGENCY % budget, 0, 0
            break
        drop = min(included, key=lambda s: (s.priority, -s.order))
        included.remove(drop)
        omitted.append(Omission("%s::%s" % (drop.path, drop.qualname) if drop.qualname else drop.path,
                                "%s (%s)" % (drop.path, drop.form.lower()), drop.priority,
                                drop.form in (FULL, TRUNCATED)))
        step = 0
    limited = [o for o in omitted if o.counts and o.priority >= PRIORITY_NEIGHBOR]
    return PackResult(
        text=text, confidence=confidence, task=task, budget_source=source, budget=budget,
        seeds=[s.qualname for s in chosen], sections=sorted(included, key=_sort_key),
        omitted=[o.label for o in omitted], warnings=warnings, tokens_used=tokens,
        budget_limited=bool(limited), suggested_budget=next_budget(budget) if limited else None,
        baseline_tokens=baseline)
