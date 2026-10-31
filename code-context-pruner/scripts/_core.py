"""File walking, ignore rules, safe paths, token estimate and output helpers."""
from __future__ import annotations

import argparse
import fnmatch
import math
import os
import re
import sys
import time
from pathlib import Path
from typing import Callable, List, Optional, Sequence, Tuple

MAX_FILE_BYTES = 1_000_000
BINARY_SNIFF_BYTES = 8192
SAFETY_PERCENT = 110
UNITS_PER_TOKEN = 2
ALPHA_CHARS = 6
DIGIT_CHARS = 3
MAX_OMITTED_ITEMS = 15
MAX_WARNINGS = 5

TASK_BUDGETS = {"lookup": 1500, "test": 2000, "bug": 2500, "explore": 3000, "feature": 3500}
DEFAULT_BUDGET = 2000
HARD_CAP = 8000
MIN_BUDGET = 200
BUDGET_TOO_SMALL = "BUDGET TOO SMALL (minimum 200)"
NO_PYTHON_FILES = "NO PYTHON FILES: code-context-pruner v1 supports Python only"
DEFAULT_MAX_SECONDS = 20.0

DEFAULT_DIR_NAMES = frozenset({
    ".git", ".hg", ".svn", ".venv", "node_modules", "__pycache__", ".mypy_cache",
    ".pytest_cache", ".ruff_cache", ".tox", ".nox", ".eggs", "site-packages",
    ".idea", ".vscode", "htmlcov",
})
DEFAULT_DIR_GLOBS = ("*.egg-info",)
ROOT_ONLY_DIRS = frozenset({"build", "dist"})
SECRET_FILE_GLOBS = (
    ".env*", "*.pem", "*.key", "*.p12", "id_rsa*", "credentials.json", "secrets.*",
)
DEFAULT_FILE_GLOBS = (
    "*.lock", "poetry.lock", "pipfile.lock", "*.pyc", "*.pyo", "*.so", "*.dll",
    "*.png", "*.jpg", "*.jpeg", "*.gif", "*.ico", "*.zip", "*.tar", "*.gz", "*.whl",
)


class PathError(Exception):
    """A path is outside the root, ignored, secret or missing (CLI exit code 3)."""


class UsageError(Exception):
    """Invalid command-line input (CLI exit code 2)."""


def setup_stdout() -> None:
    """Make stdout UTF-8 so unicode names never crash a Windows console."""
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is not None:
        reconfigure(encoding="utf-8", errors="replace")


# ---------------------------------------------------------------- ignore rules

class _Rule:
    """One compiled .gitignore line."""

    __slots__ = ("regex", "negated", "dir_only")

    def __init__(self, regex: "re.Pattern[str]", negated: bool, dir_only: bool) -> None:
        self.regex = regex
        self.negated = negated
        self.dir_only = dir_only


def _glob_to_regex(glob: str) -> str:
    """Translate gitignore glob syntax (`*`, `?`, `**`, `[...]`) to a regex body."""
    out: List[str] = []
    i, n = 0, len(glob)
    while i < n:
        c = glob[i]
        if c == "*":
            if glob.startswith("**", i):
                at_start = i == 0 or glob[i - 1] == "/"
                if at_start and glob.startswith("**/", i):
                    out.append("(?:.*/)?")
                    i += 3
                    continue
                if at_start and i + 2 == n:
                    out.append(".*")
                    i += 2
                    continue
            out.append("[^/]*")
        elif c == "?":
            out.append("[^/]")
        elif c == "[":
            end = glob.find("]", i + 2)
            if end == -1:
                out.append(re.escape(c))
            else:
                body = glob[i + 1:end].replace("\\", "\\\\")
                if body.startswith("!"):
                    body = "^" + body[1:]
                out.append("[" + body + "]")
                i = end
        elif c == "\\" and i + 1 < n:
            i += 1
            out.append(re.escape(glob[i]))
        else:
            out.append(re.escape(c))
        i += 1
    return "".join(out)


def _parse_rule(line: str) -> Optional[_Rule]:
    """Compile one ignore-file line; comments and blanks give None."""
    if line.endswith(" ") and not line.endswith("\\ "):
        line = line.rstrip(" ")
    if not line or line.startswith("#"):
        return None
    negated = line.startswith("!")
    if negated:
        line = line[1:]
    elif line.startswith("\\#"):
        line = line[1:]
    dir_only = line.endswith("/")
    line = line.rstrip("/")
    if not line:
        return None
    anchored = line.startswith("/") or "/" in line
    body = _glob_to_regex(line.lstrip("/"))
    pattern = "^" + body + "$" if anchored else "^(?:.*/)?" + body + "$"
    return _Rule(re.compile(pattern), negated, dir_only)


def _match_any(name: str, globs: Tuple[str, ...]) -> bool:
    lowered = name.lower()
    return any(fnmatch.fnmatchcase(lowered, g) for g in globs)


class IgnoreRules:
    """Built-in defaults plus root-level .gitignore and .prunerignore rules."""

    def __init__(self, lines: Optional[List[str]] = None, root: Optional[str] = None) -> None:
        self.root = root
        self._rules: List[_Rule] = []
        for line in lines or []:
            rule = _parse_rule(line.rstrip("\r\n"))
            if rule is not None:
                self._rules.append(rule)

    @classmethod
    def from_root(cls, root: str) -> "IgnoreRules":
        """Load `<root>/.gitignore` then `<root>/.prunerignore` (later lines win)."""
        lines: List[str] = []
        for name in (".gitignore", ".prunerignore"):
            path = os.path.join(root, name)
            if os.path.isfile(path):
                lines.extend(read_text(Path(path)).split("\n"))
        return cls(lines, root)

    def _user_ignored(self, rel: str, is_dir: bool) -> bool:
        ignored = False
        for rule in self._rules:
            if rule.dir_only and not is_dir:
                continue
            if rule.regex.match(rel):
                ignored = not rule.negated
        return ignored

    def dir_reason(self, rel: str, name: str) -> Optional[str]:
        """Why a directory is skipped (None if it is walked). `rel` is POSIX, no slash."""
        if name in DEFAULT_DIR_NAMES or _match_any(name, DEFAULT_DIR_GLOBS):
            return "default ignore"
        if "/" not in rel and name in ROOT_ONLY_DIRS:
            return "build output"
        if self.root is not None and os.path.isfile(os.path.join(self.root, rel, "pyvenv.cfg")):
            return "virtualenv"
        if self._user_ignored(rel, True):
            return "ignore rule"
        return None

    def file_reason(self, rel: str) -> Optional[str]:
        """Why a file is skipped (None if it is readable)."""
        name = rel.rsplit("/", 1)[-1]
        if _match_any(name, SECRET_FILE_GLOBS):
            return "secret"
        if _match_any(name, DEFAULT_FILE_GLOBS):
            return "default ignore"
        if self._user_ignored(rel, False):
            return "ignore rule"
        return None


def _rel_posix(root: str, path: str) -> str:
    rel = os.path.relpath(path, root)
    return "" if rel == "." else rel.replace(os.sep, "/")


def _is_binary(path: str) -> bool:
    with open(path, "rb") as handle:
        return b"\x00" in handle.read(BINARY_SNIFF_BYTES)


def _dir_warnings(skipped: List[Tuple[str, str, str]]) -> List[str]:
    """One warning per skipped directory; default-ignored names are counted per name."""
    by_name: dict = {}
    out: List[str] = []
    for rel, name, reason in skipped:
        if reason == "default ignore":
            by_name.setdefault(name, []).append(rel)
        else:
            out.append("skipped dir: %s/ (%s)" % (rel, reason))
    for name, rels in by_name.items():
        if len(rels) == 1:
            out.append("skipped dir: %s/ (default ignore)" % rels[0])
        else:
            out.append("skipped %d dirs named %s (default ignore)" % (len(rels), name))
    return sorted(out)


def find_repo_files(
    root: str, rules: Optional[IgnoreRules] = None, warnings: Optional[List[str]] = None
) -> List[str]:
    """Sorted POSIX relative paths of readable `.py` files; skips are added to `warnings`."""
    root = os.path.abspath(str(root))
    if rules is None:
        rules = IgnoreRules.from_root(root)
    files: List[str] = []
    skipped_dirs: List[Tuple[str, str, str]] = []
    notes: List[str] = []
    rule_ignored = 0
    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = _rel_posix(root, dirpath)
        kept = []
        for name in sorted(dirnames):
            rel = rel_dir + "/" + name if rel_dir else name
            if os.path.islink(os.path.join(dirpath, name)):
                skipped_dirs.append((rel, name, "symlink"))
                continue
            reason = rules.dir_reason(rel, name)
            if reason:
                skipped_dirs.append((rel, name, reason))
            else:
                kept.append(name)
        dirnames[:] = kept
        for name in sorted(filenames):
            if not name.endswith(".py"):
                continue
            rel = rel_dir + "/" + name if rel_dir else name
            full = os.path.join(dirpath, name)
            if rules.file_reason(rel):
                rule_ignored += 1
            elif os.path.islink(full) and not _inside(root, os.path.realpath(full)):
                notes.append("skipped file: %s (symlink outside root)" % rel)
            elif os.path.getsize(full) > MAX_FILE_BYTES:
                notes.append("skipped file: %s (over 1 MB)" % rel)
            elif _is_binary(full):
                notes.append("skipped file: %s (binary)" % rel)
            else:
                files.append(rel)
    if warnings is not None:
        warnings.extend(_dir_warnings(skipped_dirs))
        warnings.extend(sorted(notes))
        if rule_ignored:
            warnings.append("skipped %d .py files by ignore rules" % rule_ignored)
    return sorted(files)


# ----------------------------------------------------------------- safe paths

def _inside(root: str, path: str) -> bool:
    try:
        Path(path).relative_to(Path(root))
    except ValueError:
        return False
    return True


def safe_resolve(root: str, user_path: str, rules: Optional[IgnoreRules] = None) -> Path:
    """Resolve `user_path` under `root`; raise PathError if outside, ignored, secret or missing."""
    root_path = Path(root).resolve()
    candidate = Path(user_path)
    if not candidate.is_absolute():
        candidate = root_path / candidate
    resolved = candidate.resolve()
    if not _inside(str(root_path), str(resolved)):
        raise PathError("path is outside the root: %s" % user_path)
    if rules is None:
        rules = IgnoreRules.from_root(str(root_path))
    rel = _rel_posix(str(root_path), str(resolved))
    parts = rel.split("/") if rel else []
    for depth in range(1, len(parts)):
        sub = "/".join(parts[:depth])
        if rules.dir_reason(sub, parts[depth - 1]):
            raise PathError("path is in an ignored directory: %s" % rel)
    if parts:
        if resolved.is_dir():
            if rules.dir_reason(rel, parts[-1]):
                raise PathError("path is an ignored directory: %s" % rel)
        elif rules.file_reason(rel):
            raise PathError("path is ignored or secret: %s" % rel)
    if not resolved.exists():
        raise PathError("not found: %s" % user_path)
    return resolved


def read_text(path: Path) -> str:
    """Decode UTF-8 (replacing bad bytes), strip a BOM, normalize newlines to `\\n`.

    Always split the result with `text.split("\\n")`, never `splitlines()`: the latter
    also splits on form feed and breaks agreement with `ast` line numbers.
    """
    text = Path(path).read_bytes().decode("utf-8", errors="replace")
    if text.startswith("﻿"):
        text = text[1:]
    return text.replace("\r\n", "\n").replace("\r", "\n")


# ------------------------------------------------------------ token estimates

_TOKEN_RE = re.compile(
    r"(?P<a>[A-Za-z]+)|(?P<d>[0-9]+)|(?P<w>[ \t\r\n\f\v]+)|(?P<u>[^\x00-\x7f])|(?P<p>.)",
    re.DOTALL,
)
_CAMEL_RE = re.compile(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+")


def estimate_tokens(text: str) -> int:
    """Rough token ESTIMATE (each model tokenizes differently); non-zero for non-empty text."""
    return max(1, units_to_tokens(raw_units(text))) if text else 0


def raw_units(text: str) -> int:
    """Estimate in half-tokens; additive over parts joined by one newline (1 unit) each."""
    total = 0
    for match in _TOKEN_RE.finditer(text):
        kind, token = match.lastgroup, match.group()
        if kind == "a":
            total += UNITS_PER_TOKEN * sum(math.ceil(len(w) / ALPHA_CHARS) for w in _CAMEL_RE.findall(token))
        elif kind == "d":
            total += UNITS_PER_TOKEN * math.ceil(len(token) / DIGIT_CHARS)
        elif kind == "w":
            total += token.count("\n")
        elif kind == "u":
            total += 2 * UNITS_PER_TOKEN
        else:
            total += 1
    return total


def units_to_tokens(units: int) -> int:
    return -(-units // UNITS_PER_TOKEN)


def padded(tokens: int) -> int:
    """Apply the budget safety margin to an estimated token total."""
    return (tokens * SAFETY_PERCENT + 99) // 100


def printed_cost(text: str) -> int:
    """Padded token cost of `text` as printed (print adds a trailing newline)."""
    return padded(estimate_tokens(text + "\n"))


class Deadline:
    """Wall-clock limit checked between files; `None` means no limit."""

    def __init__(self, max_seconds: Optional[float]) -> None:
        self._end = None if max_seconds is None else time.monotonic() + max_seconds

    def expired(self) -> bool:
        return self._end is not None and time.monotonic() >= self._end


# -------------------------------------------------------------------- budgets

def resolve_budget(explicit: Optional[int], task: Optional[str]) -> Tuple[int, str, List[str]]:
    """Explicit budget beats task profile beats default; returns (budget, source, warnings)."""
    if task is not None and task not in TASK_BUDGETS:
        raise UsageError("unknown --task '%s' (use %s)" % (task, ", ".join(TASK_BUDGETS)))
    if explicit is not None:
        if explicit < 1:
            raise UsageError("--budget must be a positive number")
        if explicit > HARD_CAP:
            return HARD_CAP, "clamped", ["budget %d clamped to %d (hard cap)" % (explicit, HARD_CAP)]
        return explicit, "explicit", []
    if task is not None:
        return TASK_BUDGETS[task], "task", []
    return DEFAULT_BUDGET, "default", []


def next_budget(current: int) -> Optional[int]:
    """Next larger budget on the ladder, 1.5x steps above `feature`, None at the hard cap."""
    if current >= HARD_CAP:
        return None
    for value in sorted(TASK_BUDGETS.values()):
        if value > current:
            return value
    return min(math.ceil(current * 1.5 / 500) * 500, HARD_CAP)


# ------------------------------------------------------------- output helpers

def _capped(items: List[str], limit: int) -> List[str]:
    if len(items) <= limit:
        return list(items)
    return items[:limit] + ["+%d more" % (len(items) - limit)]


def footer(omitted: List[str], warnings: List[str],
           max_omitted: int = MAX_OMITTED_ITEMS, max_warnings: int = MAX_WARNINGS) -> str:
    """OMITTED (max 15 items) and WARNINGS (max 5) lines; an empty line is left out."""
    lines = []
    if omitted:
        lines.append("OMITTED: " + "; ".join(_capped(omitted, max_omitted)))
    if warnings:
        lines.append("WARNINGS: " + "; ".join(_capped(warnings, max_warnings)))
    return "\n".join(lines)


# ------------------------------------------------------------------------ CLI

class CliParser(argparse.ArgumentParser):
    """argparse that raises UsageError instead of printing usage and exiting."""

    def error(self, message: str):  # type: ignore[override]
        raise UsageError(message)


def make_parser(prog: str, description: str) -> CliParser:
    """Parser with the flags shared by every tool: --root and --max-seconds."""
    parser = CliParser(prog=prog, description=description)
    parser.add_argument("--root", default=".", help="repository root (default .)")
    parser.add_argument("--max-seconds", type=float, default=DEFAULT_MAX_SECONDS,
                        help="stop indexing after N seconds (default 20)")
    return parser


def require_root(root: str) -> str:
    """Absolute root path, or PathError if it is not a directory."""
    path = os.path.abspath(root)
    if not os.path.isdir(path):
        raise PathError("root is not a directory: %s" % root)
    return path


def run_guarded(fn: Callable[[Optional[Sequence[str]]], int], argv: Optional[Sequence[str]]) -> int:
    """Run a CLI body with UTF-8 stdout; map UsageError to exit 2 and PathError to exit 3."""
    setup_stdout()
    try:
        return fn(argv)
    except UsageError as exc:
        print("ERROR: %s" % exc)
        return 2
    except PathError as exc:
        print("ERROR: %s" % exc)
        return 3
