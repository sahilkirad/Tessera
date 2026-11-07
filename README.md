# Tessera

A skill that helps AI coding agents explore a Python repository with far fewer tokens. Instead of opening whole files, the agent makes one call and gets the exact code it needs, outlines of related files, and a list of what did not fit.

Offline, standard library only, Python 3.10+, read-only. Python repositories only.

## How it works

```
python3 code-context-pruner/scripts/pack.py "retry session cookie" --root <repo> --task bug
```

The agent gets back:

- the best-matching functions and classes as exact code
- outlines of related files
- an `OMITTED` list of items that did not fit the token budget

Other commands: `map.py` (repo overview), `find.py` (symbol search), `slice.py` (outline, exact function or line range), `deps.py` (imports and importers).

## Install

Copy the `code-context-pruner/` folder into your agent's skills folder:

| Agent | Folder |
|---|---|
| Claude Code | `~/.claude/skills/` |
| Gemini CLI | `~/.gemini/skills/` |
| Codex CLI | `~/.codex/skills/` |

Then ask your agent to use the code-context-pruner skill.

## Results

15 tasks on four Python repos (click, jinja, sqlparse, tinydb). Details: `code-context-pruner/BENCHMARK.md`.

| | agent-style keywords | plain keywords |
|---|---|---|
| Token reduction vs reading whole files (median) | 69.4% | 70.1% |
| Needed functions delivered as full code | 79.4% | 61.8% |

## Limits

- Python only, keyword search (no embeddings).
- Token counts are estimates.
- The `OMITTED` list shows only what was found but did not fit.
- Dynamic imports are not traced.

## Repository

| Path | What |
|---|---|
| `code-context-pruner/` | the skill (this is what gets zipped) |
| `tests/` | unit tests: `python -m unittest discover -s tests -q` |
| `tools/` | benchmark and packaging tools (`measure.py`, `build_zip.py`) |
| `bench/tasks/` | benchmark tasks |
| `bench/results/` | headline benchmark results |

## License

MIT, see `LICENSE`.
