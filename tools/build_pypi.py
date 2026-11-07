"""Dev-only: stage the PyPI source tree for `tessera-skill` in release/pypi_src/.

The package carries the 8 shipped scripts UNCHANGED (hashes are checked against the frozen manifest) plus a
thin dispatcher, so `uvx tessera-skill@VERSION pack ...` runs the same code the benchmark measured.
Then build with:  python -m build release/pypi_src --outdir release/pypi
Usage: python tools/build_pypi.py
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "tessera"
STAGE = ROOT / "release" / "pypi_src"
MANIFEST = ROOT / "bench" / "results" / "frozen_manifest.json"
VERSION = "1.0.0"
PACKAGE = "tessera-skill"
MODULE = "tessera_skill"

PYPROJECT = '''[build-system]
requires = ["setuptools>=77"]
build-backend = "setuptools.build_meta"

[project]
name = "tessera-skill"
version = "%(version)s"
description = "Tessera: token-budgeted code context for AI coding agents exploring Python repositories (standard library only)."
readme = "README.md"
requires-python = ">=3.10"
license = "MIT"
license-files = ["LICENSE"]
authors = [{ name = "Sahil" }]
keywords = ["ai-agents", "code-search", "context", "tokens", "skill"]
classifiers = [
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.10",
    "Programming Language :: Python :: 3.13",
    "Operating System :: OS Independent",
    "Topic :: Software Development",
]

[project.scripts]
tessera-skill = "tessera_skill.__main__:main"

[tool.setuptools.packages.find]
where = ["src"]

[tool.setuptools.package-data]
tessera_skill = ["scripts/*.py"]
'''

README = """# tessera-skill

Command line behind the Tessera skill: finds the relevant functions and classes in a Python
repository and prints one token-budgeted bundle (exact code, outlines, and a list of what did not fit).
Python 3.10+, standard library only, read-only.

    uvx tessera-skill@%(version)s pack "retry session cookie" --root <repo> --task bug

Commands: `pack`, `find`, `map`, `slice`, `deps`. Add `--help` to any of them.
"""

INIT = '"""Tessera command line."""\n__version__ = "%(version)s"\n'

MAIN = '''"""Dispatcher: `tessera-skill <pack|find|map|slice|deps> [arguments]` runs the matching script unchanged."""
from __future__ import annotations

import runpy
import sys
from pathlib import Path
from typing import Optional, Sequence

COMMANDS = ("pack", "find", "map", "slice", "deps")


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] not in COMMANDS:
        print("usage: tessera-skill {%s} [arguments]   (add --help after a command)" % "|".join(COMMANDS))
        return 0 if not args or args[0] in ("-h", "--help") else 2
    script = Path(__file__).resolve().parent / "scripts" / (args[0] + ".py")
    sys.argv = [str(script)] + args[1:]
    try:
        runpy.run_path(str(script), run_name="__main__")
    except SystemExit as stop:
        return stop.code if isinstance(stop.code, int) else (0 if stop.code is None else 1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    frozen = json.loads(MANIFEST.read_text(encoding="utf-8"))["code"]
    if STAGE.exists():
        shutil.rmtree(STAGE)
    package = STAGE / "src" / MODULE
    (package / "scripts").mkdir(parents=True)
    for rel, digest in sorted(frozen.items()):
        source = SKILL / rel
        if sha(source) != digest:
            raise SystemExit("script changed since the freeze: " + rel)
        shutil.copyfile(source, package / rel)
        if sha(package / rel) != digest:
            raise SystemExit("copy mismatch: " + rel)
    shutil.copyfile(SKILL / "LICENSE", STAGE / "LICENSE")
    values = {"version": VERSION}
    (STAGE / "pyproject.toml").write_text(PYPROJECT % values, encoding="utf-8")
    (STAGE / "README.md").write_text(README % values, encoding="utf-8")
    (package / "__init__.py").write_text(INIT % values, encoding="utf-8")
    (package / "__main__.py").write_text(MAIN, encoding="utf-8")
    print("staged %d scripts (hashes match the freeze) in %s" % (len(frozen), STAGE))
    return 0


if __name__ == "__main__":
    sys.exit(main())
