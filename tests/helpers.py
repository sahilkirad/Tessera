"""Test helpers: put scripts on sys.path and build synthetic repos in temp dirs."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from typing import Dict, Union

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "code-context-pruner" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def make_repo(files: Dict[str, Union[str, bytes]]) -> tempfile.TemporaryDirectory:
    """Create a temp repo; `files` maps POSIX relative paths to text or bytes."""
    tmp = tempfile.TemporaryDirectory()
    for rel, content in files.items():
        path = Path(tmp.name, *rel.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content if isinstance(content, bytes) else content.encode("utf-8"))
    return tmp


def root_of(tmp) -> str:
    """Real path of a repo, given the TemporaryDirectory or the str from `with ... as`."""
    return os.path.realpath(getattr(tmp, "name", tmp))
