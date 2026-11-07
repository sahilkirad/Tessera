---
name: tessera
description: Finds the relevant functions and classes in a Python repository by keyword and returns them as one token-budgeted bundle of exact code, file outlines and a list of items that did not fit, so you read less than whole files. Use it when you are asked to fix a bug, add a feature, write a test, find where something is defined, trace a flow, or explain how part of a Python codebase works, and BEFORE you read whole files, run broad greps or list directories. Python repositories only; offline, standard library only, no installs.
---

# Tessera

Read code in layers. Start cheap, go deeper only when needed. Never read a whole large file first.

The scripts sit next to this SKILL.md; `<skill_dir>` is the folder containing it. Use `python3`, or `python`, or `py` on Windows, whichever works. Always pass `--root <repo>` (the repository you are working in).

## Default: one call

```
python3 <skill_dir>/scripts/pack.py "kw1 kw2 kw3 kw4" --root <repo> --task bug
```

Pick 3-6 identifier-like keywords. If the task names a function or class, include its name in the query. Add likely synonyms yourself (discount, coupon, promo; auth, login, token). You supply the meaning; the tool filters the repo by name, path, parameter and docstring words.

How to read the result:
- `=== FULL path::Name Lstart-end` is the exact code.
- `=== OUTLINE` is signatures and line spans only; `=== MENTION` is a one-line pointer to a file.
- `=== TRUNCATED` is the top match cut to fit the budget; the last line says which `slice.py` range gives the rest.
- `OMITTED` lists items that were found but did not fit. Treat it as a to-do: fetch what the task needs with `slice.py`. Code the search ranked too low is not listed anywhere, so an empty or short `OMITTED` does not prove the bundle is complete.
- `WARNINGS` lists files it could not parse or skipped (ignored, huge, binary).
- `TOKENS` is an estimate, not an exact count.

Pick `--task` by what you are doing (it sets the token budget):
- `lookup`: "where is X?", "what does Y do?" (smallest)
- `test`: write or fix a test, small one-file bug
- `bug`: bug that touches several files
- `explore`: understand how an area or flow works
- `feature`: add a feature or refactor (largest)

Start with the smallest that fits. If the output says `BUDGET-LIMITED`, decide whether the omitted items matter; if they do, fetch them with `slice.py` or rerun with the suggested `--task` or `--budget`. Do not raise the budget "just in case". The hard cap is 8000 tokens.

## When something you need is missing

If you know the function's name (the task names it, or an OUTLINE, MENTION or OMITTED line showed it), run `python3 <skill_dir>/scripts/pack.py "Class.method" --root <repo>` with ONLY that qualified name. In the benchmark this found all 42 functions that a first pack had missed. Keep the name in your first query too, and use the name-only query as the retry.

Other paths that worked:
- `find.py "method_name" --root <repo>`: the symbol was in the top 8 results in 41 of 42 cases, and in the top 20 in all 42.
- `slice.py path/file.py:Class.method --root <repo>`: worked in 38 of 38 cases where the file path had appeared in the pack output.
- `map.py <folder>` listed the name in only 20 of 42 cases; do not rely on it for this.

## If you need more

- Repo overview: `python3 <skill_dir>/scripts/map.py [folder] --root <repo>`
- Find symbols: `python3 <skill_dir>/scripts/find.py "kw1 kw2" --root <repo>`
- Outline of a file: `python3 <skill_dir>/scripts/slice.py path/file.py --root <repo>`
- Exact function: `python3 <skill_dir>/scripts/slice.py path/file.py:Class.method --root <repo>`
- Line range: `python3 <skill_dir>/scripts/slice.py path/file.py:40-88 --root <repo>`
- What a file imports (2 levels): `python3 <skill_dir>/scripts/deps.py path/file.py --root <repo>`
- Who imports a file: `python3 <skill_dir>/scripts/deps.py path/file.py --reverse --root <repo>`

## When confidence is LOW

No code is printed, so nothing misleading is shown. The tool prints the repo's own vocabulary and a few candidate names. Choose better keywords from it and retry. Maximum 2 retries, then use `map.py` on a folder.
Example: "discount coupon" is LOW, the vocabulary shows "adjustment, invoice", so retry "adjustment invoice receipt".

## Rules

- Do not open whole files until pack, outline or slice proved insufficient.
- Names beat guesses: if `slice.py` says AMBIGUOUS or NOT FOUND, use the qualified name it suggests.
- If `OMITTED` names only a file, or you do not know a method's qualified name, run `slice.py path/file.py` for the outline first, then `slice.py path/file.py:Class.method`.
- Callers are not traced at symbol level. For "who calls this?" use `deps.py --reverse` (files), then search inside those files.
- For tiny repos (under about 10 files) just read the files.
- More detail and worked examples: `references/workflow.md`.

## Known limitations

Measured on 15 tasks in 4 Python repos (numbers in the README):
- Python only. On a repository without Python files the tool says it supports Python only.
- About 8 of 10 needed functions arrived as full code with identifier-style keywords, about 6 of 10 with plain words. If you can name a missing function, see "When something you need is missing"; otherwise retry with different keywords or use `find.py`.
- A large function can be omitted or shown cut short when it does not fit the budget; `OMITTED` and `TRUNCATED` say so.
- The confidence label (HIGH, MEDIUM, LOW) measures how well the words matched, not whether the bundle is complete.
- Dynamic imports and runtime-generated code are not traced. Callers are reported per file, not per function.
- Token numbers are estimates; each model counts differently.
- Cold start builds the index on every call: on Django (2,937 Python files) one laptop took about 5 to 7 s per call when idle (median of 3 runs: `map.py` 5.4 s, `pack.py` 6.3 s, `find.py` 6.2 s); the first call after a cold start took 20 s or more, and a run under load took 15 to 20 s per call. On click (91 files): about 0.5 s.
- Agents may not pick this skill by themselves. If yours does not, say "use the Tessera skill".
- Your agent may ask permission before each shell command the scripts run. The scripts only read files.
