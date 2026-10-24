# code-context-pruner: instructions for Claude Code

You are building `code-context-pruner`: an offline, stdlib-only Python **skill** (SKILL.md + scripts) that lets AI coding agents explore Python repositories using far fewer tokens. It will be listed for free on Agensi.io, a marketplace for SKILL.md skills. Owner: Sahil.

Full product context is in `docs/PRODUCT.md`. Read it ONCE, at the start of Step 1. Do not re-read it later.

## Non-negotiable rules
1. Python 3.9+ floor (tested on oldest and newest installed), standard library only. No third-party imports in anything under `code-context-pruner/`.
2. Shipped scripts must NEVER use: network modules, `subprocess`, `os.system`/`os.popen`, `os.environ`/`os.getenv`, `eval`/`exec`/`compile`, `pickle`/`marshal`/`base64`/`ctypes`, or write files. Agensi's automated security scan flags these. `tests/test_scan_safety.py` enforces it (bare call/name nodes only; `re.compile` is fine). (`tools/` is dev-only and not shipped, so it may write reports.)
3. Parse with `ast`. Never guess a signature. Never silently drop content: every tool output ends with an OMITTED and WARNINGS footer.
4. Deterministic output: sorted paths, stable tie-breaks, no randomness, no timestamps.
5. Hard budget: `pack.py` estimated output (real footer included) must never exceed the resolved budget (explicit `--budget`, else `--task` profile, else 2000), no budget may exceed the hard cap of 8000, and below 200 it prints `BUDGET TOO SMALL (minimum 200)`. See docs/TOOL_SPECS.md.
6. Never invent numbers. Any savings claim in README, SKILL.md or the listing must come from `bench/results/` produced by `tools/measure.py`.
7. Do not expand scope. Out of scope for v1: other languages, embeddings or vector DBs, tree-sitter, git/diff tooling, caching (no cache, no text prefilter), dynamic-import tracing, MCP. Check `docs/DECISIONS.md` before proposing alternatives.
8. Never read or print secrets: `.env*`, `*.pem`, `*.key`, credentials files.

## How we work (token discipline)
- Work on ONE step at a time, only when Sahil says "start Step N".
- Before coding, read ONLY: this file, the Step N section of `docs/BUILD_PLAN.md`, and the spec sections that step names. Do not read other docs "just in case".
- Do not stop for plan approval. Implement the whole step directly, in one pass, following the spec. Keep narration to a few lines.
- When the step is done, report and STOP. Do not start the next step until I say so.
- Don't re-read files you just wrote. Don't echo whole files back. Cap command output (`-q`, `| head -40`).
- Run tests with `python -m unittest discover -s tests -q`. Fix failures before reporting.
- Report in 10 lines or fewer: what was built, tests passed/failed, deviations from spec, at most 1 open question.
- If a spec is ambiguous or wrong: pick the simplest option that satisfies the rules, add one line to `docs/DECISIONS.md`, and mention it in the report. Do not ask more than one question per step.
- Commit locally when tests pass: `git commit -m "step N: <summary>"`. Never push.
- End each report with: "Run /clear before the next step; all state is in files."

## Target layout
```
code-context-pruner/        <- the shippable skill (its contents become the zip root)
  SKILL.md
  scripts/  _core.py _index.py _rank.py map.py find.py slice.py deps.py pack.py
  references/workflow.md
  README.md  LICENSE (MIT)
tests/                      <- unittest, small synthetic fixtures built in tmp dirs
tools/                      <- dev-only: measure.py, build_zip.py, calibrate_tokens.py
bench/                      <- tasks/*.json, repos/ (git-ignored clones), results/
docs/                       <- specs (read only what the step needs)
CLAUDE.md
```

## Commands
- Tests: `python -m unittest discover -s tests -q`
- Run everything with the D-drive venv Python (`analyze-venv/Scripts/python.exe`) and keep temp files on D: (set TEMP/TMP to a D: folder).
- Run a tool: `python code-context-pruner/scripts/pack.py "query words" --root <repo> --budget 2000`
- Build zip (Step 7): `python tools/build_zip.py`

## Code style
- Type hints, `from __future__ import annotations`, small functions, short docstrings, no dead code.
- Each CLI script: `main(argv=None) -> int`, thin wrapper over functions in `_core/_index/_rank`. Logic lives in the underscore modules so `pack.py` can import it.
- Every CLI's `main` calls `setup_stdout()` first (UTF-8 stdout, `errors="replace"`).
- Output is compact plain text (cheaper than JSON). `--json` only for `find` and `pack` (used by `tools/measure.py`).
- Paths in output always use `/` and are relative to `--root`.

## Docs map (read on demand)
- `docs/ARCHITECTURE.md`: modules, data models, algorithms
- `docs/TOOL_SPECS.md`: CLI flags and exact output formats
- `docs/BUILD_PLAN.md`: Steps 1 to 7 with acceptance criteria
- `docs/TESTING_AND_BENCHMARK.md`: tests, benchmark protocol, agent tests
- `docs/SKILL_AND_PACKAGING.md`: SKILL.md draft, zip layout, Agensi checklist
- `docs/DECISIONS.md`: what was decided and what was rejected
