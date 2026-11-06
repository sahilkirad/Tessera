"""Dev-only: write or verify bench/results/frozen_manifest.json.

The manifest has two parts:
  code   SHA-256 of every file under code-context-pruner/scripts/, taken BEFORE the holdout2 run. These must
         never change; `verify-code` fails if one does.
  text   SHA-256 of the text files (SKILL.md, README.md, BENCHMARK.md, references, LICENSE) at the time of the
         last release polish. They changed after holdout2 on purpose: the texts quote its numbers and the
         recovery-path and timing measurements made afterwards.
Usage: freeze_check.py verify-code | verify-text | write-text
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "code-context-pruner"
MANIFEST = ROOT / "bench" / "results" / "frozen_manifest.json"
TEXT_NOTE = ("Text files changed after holdout2 (2026-11-04) on purpose: SKILL.md and README.md quote the holdout2 numbers, "
             "BENCHMARK.md was added with the recovery-path and cold-timing measurements, references/workflow.md got a "
             "corrected sentence and the recovery guidance. None of them is read by the scripts, so the holdout2 result "
             "does not depend on them.")


def hashes() -> dict[str, str]:
    """SHA-256 of every file under the skill folder, keyed by `/` relative path."""
    out = {}
    for path in sorted(SKILL.rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts:
            out[path.relative_to(SKILL).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out


def split(current: dict[str, str]) -> tuple[dict[str, str], dict[str, str]]:
    code = {k: v for k, v in current.items() if k.startswith("scripts/")}
    return code, {k: v for k, v in current.items() if k not in code}


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    current_code, current_text = split(hashes())
    frozen = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if args == ["write-text"]:
        frozen["text"] = current_text
        frozen["text_note"] = TEXT_NOTE
        MANIFEST.write_text(json.dumps(frozen, indent=2) + "\n", encoding="utf-8")
        print("wrote %d text hashes" % len(current_text))
        return 0
    wanted, now = (frozen["code"], current_code) if args == ["verify-code"] else (frozen["text"], current_text)
    bad = [k for k in sorted(set(wanted) | set(now)) if wanted.get(k) != now.get(k)]
    print(("MATCH (%d files)" % len(wanted)) if not bad else "MISMATCH: " + ", ".join(bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
