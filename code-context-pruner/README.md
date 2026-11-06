# code-context-pruner

A free, offline skill that teaches AI coding agents to explore a Python repository cheaply: find the right code, view outlines instead of whole files, pull exact functions, trace imports, and pack a token-budgeted context in one call.

You do not type commands. Give your agent a task ("why is the discount missing in the receipt?"); the agent matches the skill, loads `SKILL.md`, and runs the scripts. Agents do not always pick a skill by themselves. If yours does not, say "use the code-context-pruner skill".

## Requirements
- Python 3.10 or newer (tested on 3.10 and 3.13). Standard library only: no pip installs, no API keys, no network.
- Python repositories only in this version. On a repository without Python files the tool says it supports Python only.
- The scripts are called as `python3`, `python` or `py` (Windows), whichever your machine has.

## Install
Put the folder named `code-context-pruner` (with `SKILL.md` inside it) where your agent loads skills. The folder name must match the `name:` in `SKILL.md`.

| Agent | Skills folder | Status |
|---|---|---|
| Claude Code | `~/.claude/skills/code-context-pruner/` | per Agensi's install guides |
| Gemini CLI | `~/.gemini/skills/` or `.gemini/skills/` in a project | per Agensi's install guides |
| Codex CLI | `~/.codex/skills/` or `.codex/skills/` in a project | per Agensi's install guides |
| Cursor | not verified | check Cursor's own docs |

Your agent may ask permission before each shell command the scripts run; the scripts only read files.

## What it does
- `pack.py`: one call, returns the best matching code in full, outlines of related files, and a footer listing the items that did not fit. Never exceeds its token budget (hard cap 8000, estimated).
- `map.py`: ranked overview of the repo. `find.py`: keyword search. `slice.py`: outline, exact function, or line range. `deps.py`: imports (and `--reverse` for importers).
- Deterministic output, read-only, no network, no subprocess, no file writes.

## Measured results
15 tasks on four public Python repos (click, jinja, sqlparse, tinydb), run on 2026-11-04. Details: `BENCHMARK.md`.

| | agent-style keywords | plain keywords |
|---|---|---|
| Token reduction vs reading the whole files (median) | 69.4% | 70.1% |
| Needed functions delivered as full code | 79.4% | 61.8% |
| Needed functions present in any form (full or outline) | 77.5% | 60.0% |
| Median size of the bundle | 1540 tokens | 1958 tokens |
| Token reduction vs grepping and opening the top 5 files (median) | 94.0% | 95.1% |

- An ideal reader who already knows the exact lines needs fewer tokens than the bundle: it adds context and lists what did not fit.
- If a function you need is missing and you can name it, run `pack.py` again with only its qualified name (for example `Group.invoke`). In the benchmark this found 42 of 42 missed functions. `find.py "<name>"` had it in the top 8 in 41 of 42 cases, and `slice.py path:Class.method` worked in 38 of 38 cases where the file path was shown.
- Speed: every call builds the index from scratch. On Django (2,937 Python files) one laptop took a median of 5.7 s for `map.py`, 7.2 s for `pack.py` and 18.5 s for `find.py`; on click (91 files) about 0.5 s.

## Limits
- Token counts are estimates (calibrated against OpenAI's cl100k_base tokenizer; other models count differently).
- Keyword search only: no embeddings. The agent supplies meaning through the words it picks; low-confidence searches print the repo's vocabulary and no code.
- The OMITTED footer lists only items that were found but did not fit. Code the search ranked too low is not listed, so an empty OMITTED does not prove the bundle is complete.
- Dynamic imports are not traced and runtime-generated code is invisible. Callers are reported at file level only.
- A file that uses syntax newer than the Python running the tool cannot be parsed; it is listed in the warnings.
- Agents may not always choose to use a skill.

## License
MIT License, see `LICENSE`.
