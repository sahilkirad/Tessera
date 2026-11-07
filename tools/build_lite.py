"""Dev-only: build the SUBSCRIPTION zip (SKILL.md + references only, no scripts) in release/.

The subscription listing ships text only. The tool itself is the PyPI package `tessera-skill`
(see tools/build_pypi.py); this SKILL.md tells the agent to run the pinned release with `uvx`.
The lite texts are generated from the normal skill texts, so there is one source of truth.
Usage: python tools/build_lite.py   -> release/tessera-subscription.zip
"""
from __future__ import annotations

import re
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_pypi import PACKAGE, VERSION  # noqa: E402
from build_zip import FIXED_TIME, SKILL, parse_frontmatter  # noqa: E402

ROOT = SKILL.parent
DIST = ROOT / "release"
STAGE = DIST / "lite_src"
RUN = "uvx %s@%s" % (PACKAGE, VERSION)
NAME = "tessera"
COMMANDS = "pack|find|map|slice|deps"


def once(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise SystemExit("expected exactly one %r, found %d" % (old[:60], text.count(old)))
    return text.replace(old, new)


def commands(text: str) -> str:
    """`pack.py ...` -> a full uvx command, `pack.py` alone -> the subcommand name."""
    text = re.sub(r"python3 <skill_dir>/scripts/(%s)\.py" % COMMANDS, RUN + r" \1", text)
    text = re.sub(r"`(%s)\.py(?= )" % COMMANDS, "`" + RUN + r" \1", text)
    return re.sub(r"\b(%s)\.py\b" % COMMANDS, r"\1", text)


def skill_text(text: str) -> str:
    text = once(text, "Python repositories only; offline, standard library only, no installs.",
                "Python repositories only; standard library only, run through uvx (needs uv installed).")
    text = once(text, "The scripts sit next to this SKILL.md; `<skill_dir>` is the folder containing it. Use `python3`, or `python`, or `py` on Windows, whichever works. Always pass",
                "Run the tool with `uvx` (part of uv, https://docs.astral.sh/uv/). If `uvx` is missing, "
                "`pipx run --spec %s==%s %s <command> ...` does the same. "
                "Run only `%s` at exactly version %s, never another package. "
                "The first call downloads the tool, so it needs internet access once. "
                "If neither `uvx` nor `pipx` is installed, ask the user to install uv, or read the files normally. "
                "File paths such as `path/file.py` are relative to `--root`; put paths that contain spaces in quotes. Always pass" % (PACKAGE, VERSION, PACKAGE, PACKAGE, VERSION))
    text = once(text, "(numbers in the README)", "(numbers in BENCHMARK.md)")
    text = once(text, "each shell command the scripts run. The scripts only read files.", "each shell command the tool runs. The tool only reads files.")
    text = commands(text)
    return once(text, "- Python only.", "- The first run downloads the tool from PyPI, so it needs internet access once and `uv` (or `pipx`) installed.\n- Python only.")


def plain_text(text: str, header: str = "") -> str:
    return header + commands(text)


def check(skill: str) -> None:
    fields = parse_frontmatter(skill)
    body = skill.split("\n---\n", 1)[1]
    if sorted(fields) != ["description", "name"] or fields["name"] != NAME:
        raise SystemExit("bad frontmatter")
    for bad in ("<skill_dir>", "scripts/", "%", "python3 "):
        if bad in body:
            raise SystemExit("lite SKILL.md still contains %r" % bad)
    if len(fields["description"]) > 1000 or RUN not in body:
        raise SystemExit("description too long or run command missing")


def main() -> int:
    skill = skill_text((SKILL / "SKILL.md").read_text(encoding="utf-8"))
    check(skill)
    workflow = plain_text((SKILL / "references" / "workflow.md").read_text(encoding="utf-8"),
                          "Commands below are written as `pack`, `find`, `map`, `slice`, `deps`: run each as `%s <command> ...` and add `--root <repo>`.\n\n" % RUN)
    files = {"SKILL.md": skill, "LICENSE": (SKILL / "LICENSE").read_text(encoding="utf-8"),
             "BENCHMARK.md": plain_text((SKILL / "BENCHMARK.md").read_text(encoding="utf-8")),
             "references/workflow.md": workflow}
    DIST.mkdir(exist_ok=True)
    target = DIST / (NAME + "-subscription.zip")
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel in sorted(files):
            (STAGE / rel).parent.mkdir(parents=True, exist_ok=True)
            (STAGE / rel).write_text(files[rel], encoding="utf-8")
            info = zipfile.ZipInfo(rel, FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zf.writestr(info, files[rel].encode("utf-8"))
    print("%s: %d files, %d bytes; run command: %s" % (target, len(files), target.stat().st_size, RUN))
    return 0


if __name__ == "__main__":
    sys.exit(main())
