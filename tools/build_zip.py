"""Dev-only: build and validate the Agensi upload zip under release/.

Writes ONE zip from `tessera/`: release/<name>.zip with SKILL.md at the zip root.
Run: python tools/build_zip.py
"""
from __future__ import annotations

import io
import re
import sys
import unittest
import zipfile
from pathlib import Path
from typing import List, Tuple

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "tessera"
DIST = ROOT / "release"
MAX_BYTES = 50 * 1024 * 1024
FIXED_TIME = (2026, 1, 1, 0, 0, 0)
FORBIDDEN_PARTS = {"tests", "bench", "docs", "tools", "work", "handoff", "dist", "release", "__pycache__", ".git"}
FORBIDDEN_NAMES = (".env", ".pem", ".key", ".pyc", ".pyo")
REQUIRED = ("SKILL.md", "LICENSE", "README.md", "BENCHMARK.md")
EXPECTED_FILES = 13


def skill_files() -> List[Path]:
    """Every file to ship, sorted, without bytecode caches."""
    return sorted(p for p in SKILL.rglob("*") if p.is_file() and "__pycache__" not in p.parts)


def parse_frontmatter(text: str) -> dict[str, str]:
    match = re.match(r"---\n(.*?)\n---\n", text, re.S)
    if not match:
        raise SystemExit("SKILL.md has no frontmatter")
    return dict(line.split(": ", 1) for line in match.group(1).split("\n"))


def check_skill() -> Tuple[str, int]:
    """Validate SKILL.md and the file set; returns (name, description length)."""
    fields = parse_frontmatter((SKILL / "SKILL.md").read_text(encoding="utf-8"))
    if sorted(fields) != ["description", "name"]:
        raise SystemExit("frontmatter must hold only name and description, found %s" % sorted(fields))
    name = fields["name"]
    if not re.fullmatch(r"[a-z0-9-]+", name):
        raise SystemExit("bad name %r" % name)
    if name != SKILL.name:
        raise SystemExit("name %r does not match folder %r" % (name, SKILL.name))
    files = skill_files()
    rels = [p.relative_to(SKILL).as_posix() for p in files]
    if len(files) != EXPECTED_FILES:
        raise SystemExit("expected %d files, found %d" % (EXPECTED_FILES, len(files)))
    for need in REQUIRED:
        if need not in rels:
            raise SystemExit("missing " + need)
    for rel in rels:
        parts = set(rel.split("/"))
        if parts & FORBIDDEN_PARTS or rel.endswith(FORBIDDEN_NAMES) or rel.split("/")[-1].startswith(".env"):
            raise SystemExit("forbidden file in skill folder: " + rel)
    if sum(p.stat().st_size for p in files) >= MAX_BYTES:
        raise SystemExit("skill is 50 MB or more")
    return name, len(fields["description"])


def run_scan_safety() -> None:
    """Run tests/test_scan_safety.py in-process; abort on any failure."""
    sys.path.insert(0, str(ROOT / "tests"))
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"), pattern="test_scan_safety.py")
    result = unittest.TextTestRunner(verbosity=0, stream=io.StringIO()).run(suite)
    if not result.wasSuccessful() or result.testsRun == 0:
        raise SystemExit("scan-safety test failed")


def write_zip(target: Path, prefix: str) -> List[str]:
    """Deterministic zip (sorted, fixed timestamps); returns the member names."""
    names = []
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in skill_files():
            arcname = prefix + path.relative_to(SKILL).as_posix()
            info = zipfile.ZipInfo(arcname, FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zf.writestr(info, path.read_bytes())
            names.append(arcname)
    return names


def main(argv: List[str] | None = None) -> int:
    name, desc_len = check_skill()
    DIST.mkdir(exist_ok=True)
    run_scan_safety()
    target = DIST / (name + ".zip")
    names = write_zip(target, "")
    print("%s: %d files, %d bytes" % (target, len(names), target.stat().st_size))
    print("name=%s description_length=%d scan-safety=PASS" % (name, desc_len))
    return 0


if __name__ == "__main__":
    sys.exit(main())
