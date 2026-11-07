"""AST symbol and import index, import resolution and outline rendering."""
from __future__ import annotations

import ast
import copy
import difflib
import os
import re
import sys
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from _core import Deadline, IgnoreRules, UsageError, find_repo_files, read_text

RAW_LINES = 60
DOC1_MAX = 200
DOC_PARA_MAX = 300
FIELD_MAX = 80
_ALL_CAPS = re.compile(r"[A-Z][A-Z0-9_]*")
_RANGE = re.compile(r"[0-9]+-[0-9]+")
_DEFS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
_STATEMENT_LISTS = ("body", "orelse", "finalbody", "handlers", "cases")
_SCAN_DEF = re.compile(r"^(\s*)(?:async\s+)?def\s+(\w+)")
_SCAN_CLASS = re.compile(r"^(\s*)class\s+(\w+)")
_NEWER_SYNTAX = (
    ((3, 10), re.compile(r"^[ \t]*match[ \t]+\S.*:[ \t]*$", re.M)),
    ((3, 11), re.compile(r"^[ \t]*except[ \t]*\*", re.M)),
    ((3, 12), re.compile(r"^[ \t]*(?:class|def|type)[ \t]+\w+[ \t]*\[|^[ \t]*type[ \t]+\w+[ \t]*=", re.M)),
)


@dataclass
class Symbol:
    kind: str
    name: str
    qualname: str
    path: str
    start: int
    end: int
    signature: str
    doc1: str
    decorators: List[str]
    params: List[str]
    is_async: bool
    refs: List[str]
    doc: str = ""
    fields: List[str] = field(default_factory=list)


@dataclass
class ImportRec:
    module: str
    names: List[str]
    level: int
    lineno: int
    aliases: List[str] = field(default_factory=list)


@dataclass
class FileIndex:
    path: str
    size: int
    loc: int
    symbols: List[Symbol]
    imports: List[ImportRec]
    constants: List[str]
    module_doc1: str
    parse_ok: bool


@dataclass
class ImportEdge:
    target: Optional[str]
    kind: str
    module: str
    names: List[str]
    lineno: int


@dataclass
class RepoIndex:
    root: str
    files: Dict[str, FileIndex]
    module_map: Dict[str, str]
    warnings: List[str]
    modules: Dict[str, str] = field(default_factory=dict)
    edges: Dict[str, List[ImportEdge]] = field(default_factory=dict)
    partial: bool = False
    tops: Set[str] = field(default_factory=set)

    def file_edges(self) -> Set[Tuple[str, str]]:
        """Unique (importer, imported) pairs between repo files, no self edges."""
        return {(src, e.target) for src, es in self.edges.items() for e in es
                if e.target is not None and e.target != src}


# ------------------------------------------------------------------- parsing

def looks_newer(text: str, version: Optional[Tuple[int, int]] = None) -> bool:
    """True if `text` seems to use syntax newer than `version` (default: this Python)."""
    version = version or (sys.version_info[0], sys.version_info[1])
    return any(version < needed and rx.search(text) for needed, rx in _NEWER_SYNTAX)


def _count_lines(text: str) -> int:
    if not text:
        return 0
    return text.count("\n") + (0 if text.endswith("\n") else 1)


def _first_line(doc: str) -> str:
    for line in doc.split("\n"):
        if line.strip():
            return line.strip()[:DOC1_MAX]
    return ""


def _is_str_const(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and isinstance(node.value, str)


def _assign_text(stmt: ast.stmt) -> str:
    """One-line source for an assignment, never longer than FIELD_MAX and always valid."""
    text = ast.unparse(stmt)
    if len(text) <= FIELD_MAX and "\n" not in text:
        return text
    if isinstance(stmt, ast.AnnAssign):
        short = "%s: %s" % (ast.unparse(stmt.target), ast.unparse(stmt.annotation))
        return short if len(short) <= FIELD_MAX and "\n" not in short else "%s: ..." % ast.unparse(stmt.target)
    assert isinstance(stmt, ast.Assign)
    return " = ".join(ast.unparse(t) for t in stmt.targets) + " = ..."


def _simple_target(stmt: ast.stmt) -> Optional[str]:
    if isinstance(stmt, ast.Assign) and all(isinstance(t, ast.Name) for t in stmt.targets):
        return stmt.targets[0].id  # type: ignore[attr-defined]
    if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
        return stmt.target.id
    return None


def _body_on_header_line(node: ast.AST, lines: List[str]) -> bool:
    first = node.body[0]  # type: ignore[attr-defined]
    prefix = lines[first.lineno - 1].encode("utf-8")[:first.col_offset].decode("utf-8", "ignore")
    return bool(prefix.strip())


def _unparse_header(node: ast.AST) -> str:
    clone = copy.copy(node)
    clone.body = [ast.Expr(value=ast.Constant(value=Ellipsis))]  # type: ignore[attr-defined]
    clone.decorator_list = []  # type: ignore[attr-defined]
    head = ast.unparse(clone).strip().rsplit("\n", 1)[0]
    return head[:-1] if head.endswith(":") else head


def _signature(node: ast.AST, lines: List[str]) -> str:
    """Header text exactly as written (no trailing colon); unparse fallback for odd layouts."""
    first = node.body[0]  # type: ignore[attr-defined]
    if not _body_on_header_line(node, lines):
        chunk = lines[node.lineno - 1:first.lineno - 1]  # type: ignore[attr-defined]
        while chunk and (not chunk[-1].strip() or chunk[-1].strip().startswith("#")):
            chunk.pop()
        text = textwrap.dedent("\n".join(chunk)).rstrip()
        if text.endswith(":"):
            return text[:-1].rstrip()
    return _unparse_header(node)


def _make_symbol(node: ast.AST, qual: str, in_class: bool, lines: List[str], path: str) -> Symbol:
    is_class = isinstance(node, ast.ClassDef)
    decos = [d.lineno for d in node.decorator_list]  # type: ignore[attr-defined]
    doc = ast.get_docstring(node, clean=True) or ""  # type: ignore[arg-type]
    paragraph = doc.strip().split("\n\n")[0].replace("\n", " ")[:DOC_PARA_MAX]
    params: List[str] = []
    fields: List[str] = []
    if is_class:
        for stmt in node.body:  # type: ignore[attr-defined]
            if _simple_target(stmt) is not None:
                fields.append(_assign_text(stmt))
    else:
        a = node.args  # type: ignore[attr-defined]
        params = [x.arg for x in a.posonlyargs + a.args]
        params += [a.vararg.arg] if a.vararg else []
        params += [x.arg for x in a.kwonlyargs]
        params += [a.kwarg.arg] if a.kwarg else []
    return Symbol(
        kind="class" if is_class else ("method" if in_class else "function"),
        name=node.name,  # type: ignore[attr-defined]
        qualname=qual,
        path=path,
        start=min([node.lineno] + decos),  # type: ignore[attr-defined]
        end=node.end_lineno or node.lineno,  # type: ignore[attr-defined]
        signature=_signature(node, lines),
        doc1=_first_line(doc),
        decorators=["@" + ast.unparse(d) for d in node.decorator_list],  # type: ignore[attr-defined]
        params=params,
        is_async=isinstance(node, ast.AsyncFunctionDef),
        refs=[],
        doc=paragraph,
        fields=fields,
    )


def _child_statements(node: ast.AST) -> List[ast.AST]:
    """Nested statement lists of a compound statement (never descends into expressions)."""
    kids: List[ast.AST] = []
    for name in _STATEMENT_LISTS:
        value = getattr(node, name, None)
        if isinstance(value, list):
            kids.extend(value)
    return kids


def _scan_statements(tree: ast.Module, lines: List[str], path: str) -> Tuple[List[Symbol], List[ImportRec]]:
    """One statement-level pass: symbols (never inside functions) and every import statement."""
    symbols: List[Symbol] = []
    found: List[Tuple[int, int, ImportRec]] = []
    stack = [(node, "", False, False) for node in reversed(tree.body)]
    while stack:
        node, prefix, in_class, in_func = stack.pop()
        if isinstance(node, _DEFS):
            qual = prefix + node.name
            if not in_func:
                symbols.append(_make_symbol(node, qual, in_class, lines, path))
            inner = (qual + ".", True, in_func) if isinstance(node, ast.ClassDef) else (prefix, False, True)
            stack.extend((kid, *inner) for kid in reversed(node.body))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                rec = ImportRec(alias.name, [], 0, node.lineno, [alias.asname or alias.name.split(".")[0]])
                found.append((node.lineno, node.col_offset, rec))
        elif isinstance(node, ast.ImportFrom):
            rec = ImportRec(node.module or "", [a.name for a in node.names], node.level, node.lineno,
                            [a.asname or a.name for a in node.names])
            found.append((node.lineno, node.col_offset, rec))
        else:
            stack.extend((kid, prefix, in_class, in_func) for kid in reversed(_child_statements(node)))
    found.sort(key=lambda item: (item[0], item[1]))
    return symbols, [rec for _, _, rec in found]


def _scan_lines(path: str, lines: List[str]) -> List[Symbol]:
    """Names-only fallback for files that cannot be parsed."""
    out: List[Symbol] = []
    for number, line in enumerate(lines, 1):
        cls = _SCAN_CLASS.match(line)
        fn = _SCAN_DEF.match(line)
        if not (cls or fn):
            continue
        match = cls or fn
        assert match is not None
        kind = "class" if cls else ("method" if match.group(1) else "function")
        out.append(Symbol(kind, match.group(2), match.group(2), path, number, number,
                          line.strip().rstrip(":"), "", [], [], "async" in line.split("def")[0], []))
    return out


def _failure_reason(text: str, exc: BaseException) -> str:
    if isinstance(exc, SyntaxError) and looks_newer(text):
        return "file uses syntax this Python cannot parse"
    detail = "%s: %s" % (type(exc).__name__, getattr(exc, "msg", None) or str(exc))
    line = getattr(exc, "lineno", None)
    return "could not parse (%s%s)" % (detail, ", line %d" % line if line else "")


def _index_tree(path: str, text: str, size: int, tree: ast.Module, lines: List[str]) -> FileIndex:
    symbols, imports = _scan_statements(tree, lines, path)
    constants = []
    for stmt in tree.body:
        target = _simple_target(stmt)
        if target and _ALL_CAPS.fullmatch(target):
            constants.append(_assign_text(stmt))
    return FileIndex(path, size, _count_lines(text), symbols, imports, constants,
                     _first_line(ast.get_docstring(tree, clean=True) or ""), True)


def parse_file(path: str, text: str, size: int, warnings: List[str]) -> FileIndex:
    """Index one file; any failure becomes a warning plus a names-only fallback."""
    lines = text.split("\n")
    try:
        return _index_tree(path, text, size, ast.parse(text), lines)
    except Exception as exc:  # per-file isolation: SyntaxError, ValueError, RecursionError, ...
        warnings.append("%s: %s" % (path, _failure_reason(text, exc)))
        return FileIndex(path, size, _count_lines(text), _scan_lines(path, lines), [], [], "", False)


# ---------------------------------------------------------- module resolution

def _source_roots(paths: List[str]) -> List[str]:
    """Repo root, `src`, and every package root (dir with __init__ whose parent has none)."""
    init_dirs = {p.rpartition("/")[0] for p in paths if p.rsplit("/", 1)[-1] == "__init__.py"}
    roots = {""}
    if any(p.startswith("src/") for p in paths):
        roots.add("src")
    for d in init_dirs:
        parent = d.rpartition("/")[0]
        if parent not in init_dirs:
            roots.add(parent)
    return sorted(roots, key=lambda r: -len(r))


def _module_name(path: str, roots: List[str]) -> Optional[str]:
    for root in roots:
        if root == "" or path.startswith(root + "/"):
            rel = path[len(root) + 1:] if root else path
            parts = rel[:-3].split("/")
            if parts[-1] == "__init__":
                parts.pop()
            return ".".join(parts) if parts else None
    return None


def _build_modules(paths: List[str], warnings: List[str]) -> Tuple[Dict[str, str], Dict[str, str]]:
    roots = _source_roots(paths)
    modules: Dict[str, str] = {}
    module_map: Dict[str, str] = {}
    for path in paths:
        name = _module_name(path, roots)
        if name is None:
            continue
        if name in module_map:
            warnings.append("module name clash: %s (kept %s, skipped %s)" % (name, module_map[name], path))
            continue
        module_map[name] = path
        modules[path] = name
    return modules, module_map


def _lookup(module_map: Dict[str, str], name: str) -> Optional[str]:
    """Longest-prefix match of a dotted name in the module map."""
    parts = name.split(".")
    while parts and parts[0]:
        hit = module_map.get(".".join(parts))
        if hit:
            return hit
        parts.pop()
    return None


def _package_of(index: RepoIndex, path: str) -> str:
    mod = index.modules.get(path, "")
    return mod if path.rsplit("/", 1)[-1] == "__init__.py" else mod.rpartition(".")[0]


def _absolute(index: RepoIndex, path: str, rec: ImportRec) -> Optional[str]:
    """Absolute dotted module of an import record (None if a relative import climbs too far)."""
    if rec.level == 0:
        return rec.module
    pkg = _package_of(index, path).split(".") if _package_of(index, path) else []
    up = rec.level - 1
    if up > len(pkg):
        return None
    return ".".join(pkg[:len(pkg) - up] + ([rec.module] if rec.module else []))


def _reexport(index: RepoIndex, init_path: str, name: str) -> Optional[Tuple[str, str]]:
    """ONE re-export hop: `from .x import name` inside a package __init__."""
    for rec in index.files[init_path].imports:
        if rec.names and name in rec.aliases:
            absolute = _absolute(index, init_path, rec)
            target = _lookup(index.module_map, absolute) if absolute else None
            if target and target != init_path:
                return target, rec.names[rec.aliases.index(name)]
    return None


def _unclassified(index: RepoIndex, rec: ImportRec, lineno: int) -> ImportEdge:
    dotted = "." * rec.level + rec.module
    top = rec.module.split(".")[0]
    if rec.level == 0 and top and top not in index.tops:
        return ImportEdge(None, "external", top, [], lineno)
    return ImportEdge(None, "unresolved", dotted, [], lineno)


def _resolve_rec(index: RepoIndex, path: str, rec: ImportRec) -> List[ImportEdge]:
    if rec.level == 0 and not rec.names:
        target = _lookup(index.module_map, rec.module)
        if target:
            return [ImportEdge(target, "internal", rec.module, [], rec.lineno)]
        return [_unclassified(index, rec, rec.lineno)]
    absolute = _absolute(index, path, rec)
    if absolute is None:
        return [_unclassified(index, rec, rec.lineno)]
    base = index.module_map.get(absolute) if absolute else None
    by_target: Dict[str, List[str]] = {}
    out: List[ImportEdge] = []
    for name in rec.names:
        sub = index.module_map.get(absolute + "." + name if absolute else name)
        if sub:
            out.append(ImportEdge(sub, "internal", absolute + "." + name, [], rec.lineno))
        elif base:
            hop = _reexport(index, base, name) if base.rsplit("/", 1)[-1] == "__init__.py" else None
            target, real = hop if hop else (base, name)
            by_target.setdefault(target, []).append(real)
        else:
            return out + [_unclassified(index, rec, rec.lineno)]
    out.extend(ImportEdge(t, "internal", absolute, names, rec.lineno) for t, names in by_target.items())
    return out


def build_index(root: str, rules: Optional[IgnoreRules] = None,
                deadline: Optional[Deadline] = None) -> RepoIndex:
    """Parse every repo file in sorted order and resolve imports between them."""
    root = os.path.abspath(root)
    rules = rules or IgnoreRules.from_root(root)
    warnings: List[str] = []
    paths = find_repo_files(root, rules, warnings)
    files: Dict[str, FileIndex] = {}
    partial = False
    for number, rel in enumerate(paths):
        if deadline is not None and deadline.expired():
            partial = True
            warnings.append("time limit reached: indexed %d of %d files" % (number, len(paths)))
            break
        full = os.path.join(root, *rel.split("/"))
        try:
            text = read_text(Path(full))
            size = os.path.getsize(full)
        except OSError as exc:
            warnings.append("%s: could not read (%s)" % (rel, exc.strerror or type(exc).__name__))
            continue
        files[rel] = parse_file(rel, text, size, warnings)
    modules, module_map = _build_modules(sorted(files), warnings)
    index = RepoIndex(root, files, module_map, warnings, modules, {}, partial,
                      {m.split(".")[0] for m in module_map})
    for rel in sorted(files):
        index.edges[rel] = [e for rec in files[rel].imports for e in _resolve_rec(index, rel, rec)]
    return index


# -------------------------------------------------------------------- outline

def _doc_literal(doc: str) -> str:
    """Always-valid string literal for a one-line docstring."""
    if '"' in doc or "\\" in doc or not doc.isprintable():
        return repr(doc)
    return '"""' + doc + '"""'


def _import_line(rec: ImportRec) -> str:
    if rec.level == 0 and not rec.names:
        alias = rec.aliases[0]
        return "import " + rec.module + ("" if alias == rec.module.split(".")[0] else " as " + alias)
    parts = [n if a == n else "%s as %s" % (n, a) for n, a in zip(rec.names, rec.aliases)]
    return "from %s%s import %s" % ("." * rec.level, rec.module, ", ".join(parts))


def _indent(text: str, prefix: str) -> str:
    return "\n".join(prefix + line if line else line for line in text.split("\n"))


def _emit(sym: Symbol, kids: Dict[str, List[Symbol]], used: Set[str], pad: str, out: List[str]) -> None:
    out.extend(pad + d for d in sym.decorators)
    head = _indent(sym.signature, pad)
    if sym.kind == "class":
        out.append(head + ":")
        body: List[str] = []
        if sym.doc1:
            body.append(_doc_literal(sym.doc1))
        body.extend(sym.fields)
        for line in body:
            out.append(pad + "    " + line)
        count = len(body)
        if sym.qualname not in used:
            used.add(sym.qualname)
            for child in kids.get(sym.qualname, []):
                _emit(child, kids, used, pad + "    ", out)
                count += 1
        if count == 0:
            out.append(pad + "    ...")
        return
    span = "# L%d-%d" % (sym.start, sym.end)
    if sym.kind == "function" and sym.doc1:
        out.extend([head + ":", "%s    %s  %s" % (pad, _doc_literal(sym.doc1), span), pad + "    ..."])
    else:
        out.append("%s: ...  %s" % (head, span))


def render_outline(fi: FileIndex, with_imports: bool = False) -> str:
    """Valid-Python outline: docstring, constants, classes, signatures with line spans."""
    out: List[str] = []
    if fi.module_doc1:
        out.append(_doc_literal(fi.module_doc1))
    if with_imports:
        seen: Set[str] = set()
        for rec in fi.imports:
            line = _import_line(rec)
            if line not in seen:
                seen.add(line)
                out.append(line)
    out.extend(fi.constants)
    kids = _kid_map(fi)
    used: Set[str] = set()
    for sym in fi.symbols:
        if "." not in sym.qualname:
            _emit(sym, kids, used, "", out)
    return "\n".join(out)


def _kid_map(fi: FileIndex) -> Dict[str, List[Symbol]]:
    kids: Dict[str, List[Symbol]] = {}
    for sym in fi.symbols:
        if "." in sym.qualname:
            kids.setdefault(sym.qualname.rpartition(".")[0], []).append(sym)
    return kids


def render_class_outline(fi: FileIndex, qualname: str) -> str:
    """Outline of one class (its fields and method signatures), nested classes included."""
    out: List[str] = []
    cls = next(s for s in fi.symbols if s.qualname == qualname)
    _emit(cls, _kid_map(fi), set(), "", out)
    return "\n".join(out)


resolve_rec = _resolve_rec


# ---------------------------------------------------------------------- slice

Report = Tuple[str, List[str], List[str]]


def split_target(target: str) -> Tuple[str, Optional[str]]:
    """Split `path.py:spec` into (path, spec); a Windows drive colon is not a separator."""
    start = 2 if len(target) > 2 and target[1] == ":" and target[0].isalpha() and target[2] in "\\/" else 0
    idx = target.find(":", start)
    return (target, None) if idx == -1 else (target[:idx], target[idx + 1:])


def _raw_report(rel: str, text: str, loc: int, warnings: List[str]) -> Report:
    shown = text.split("\n")
    if shown[-1] == "":
        shown.pop()
    shown = shown[:RAW_LINES]
    warnings.append("showing raw lines")
    return "\n".join(["RAW %s (first %d of %d lines)" % (rel, len(shown), loc)] + shown), [], warnings


def _quoted_near(spec: str, names: List[str]) -> str:
    close = difflib.get_close_matches(spec, names, n=3, cutoff=0.6)
    return ", ".join(close) if close else "(none; use slice.py FILE for the outline)"


def _class_header_line(lines: List[str], cls: Symbol) -> int:
    for number in range(cls.start, cls.end + 1):
        if lines[number - 1].lstrip().startswith("class "):
            return number
    return cls.start


def _body(lines: List[str], first: int, last: int, max_lines: int, rel: str) -> Tuple[List[str], List[str]]:
    """Exact lines first..last (1-based), cut at max_lines with a visible marker."""
    chosen = lines[first - 1:last]
    if len(chosen) <= max_lines:
        return chosen, []
    marker = "TRUNCATED at %d lines; use slice %s:%d-%d for the rest" % (max_lines, rel, first + max_lines, last)
    return chosen[:max_lines] + [marker], [marker]


def _ambiguous(spec: str, matches: List[Symbol]) -> str:
    shown = ", ".join("%s (L%d)" % (s.qualname, s.start) for s in matches[:5])
    more = ", ..." if len(matches) > 5 else ""
    names = [s.qualname for s in matches]
    advice = "use a line range" if len(set(names)) < len(names) else "use the full qualname"
    return "AMBIGUOUS: '%s' matches %d symbols: %s%s; %s" % (spec, len(matches), shown, more, advice)


def slice_report(path: Path, rel: str, spec: Optional[str], with_imports: bool = False,
                 context: int = 0, with_class: bool = False, max_lines: int = 400) -> Report:
    """(text, omitted, warnings) for `slice.py`: outline, symbol source, or line range."""
    text = read_text(path)
    lines = text.split("\n")
    total = _count_lines(text)
    warnings: List[str] = []
    if spec is not None and _RANGE.fullmatch(spec):
        first, last = (int(n) for n in spec.split("-"))
        if first < 1 or first > last:
            raise UsageError("bad line range: %s (use a-b with 1 <= a <= b)" % spec)
        if first > total:
            return "OUT OF RANGE: %s has %d lines" % (rel, total), [], warnings
        if last > total:
            warnings.append("range clamped to %d lines" % total)
        return _window_report(rel, "", lines, first, min(last, total), total, context, None, max_lines, warnings)
    fi = parse_file(rel, text, os.path.getsize(path), warnings)
    if not fi.parse_ok:
        return _raw_report(rel, text, fi.loc, warnings)
    if spec is None:
        body = render_outline(fi, with_imports)
        return "\n".join(["OUTLINE %s (%d lines)" % (rel, fi.loc)] + ([body] if body else [])), [], warnings
    matches = [s for s in fi.symbols if s.qualname == spec] or [
        s for s in fi.symbols if s.qualname.endswith("." + spec)]
    if not matches:
        names = sorted({s.qualname for s in fi.symbols})
        return "NOT FOUND: '%s'. Closest in this file: %s" % (spec, _quoted_near(spec, names)), [], warnings
    if len(matches) > 1:
        return _ambiguous(spec, matches), [], warnings
    sym = matches[0]
    header_line = None
    if with_class:
        parent = sym.qualname.rpartition(".")[0]
        owner = next((s for s in fi.symbols if s.kind == "class" and s.qualname == parent), None)
        header_line = _class_header_line(lines, owner) if owner else None
    return _window_report(rel, "::" + sym.qualname, lines, sym.start, sym.end, total, context,
                          header_line, max_lines, warnings)


def _window_report(rel: str, label: str, lines: List[str], first: int, last: int, total: int,
                   context: int, header_line: Optional[int], max_lines: int, warnings: List[str]) -> Report:
    lo, hi = max(1, first - context), min(total, last + context)
    note = ""
    if context:
        note += " (context %d: L%d-%d)" % (context, lo, hi)
    if header_line is not None:
        note += " (+ class header L%d)" % header_line
    body, omitted = _body(lines, lo, hi, max_lines, rel)
    if header_line is not None:
        body = [lines[header_line - 1]] + body
    head = "SLICE %s%s L%d-%d%s" % (rel, label, first, last, note)
    return "\n".join([head] + body), omitted, warnings
