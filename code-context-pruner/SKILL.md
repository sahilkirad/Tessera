---
name: code-context-pruner
description: Use when you need to fix a bug, add a feature, write a test, or explain code in a Python repository. Finds relevant functions and classes by keyword, shows file outlines (signatures only), extracts exact functions or line ranges, traces imports, and packs a token-budgeted context bundle in one call. Use it BEFORE reading whole files, running broad greps, or listing directories in a Python repo. Python repositories only; offline, standard library only, no installs.
---

# code-context-pruner

Read code in layers. Start cheap, go deeper only when needed. Never read a whole large file first.

The scripts sit next to this SKILL.md; `<skill_dir>` is the folder containing it. Use `python3`, or `python`, or `py` on Windows, whichever works. Always pass `--root <repo>` (the repository you are working in).

## Default: one call

```
python3 <skill_dir>/scripts/pack.py "kw1 kw2 kw3 kw4" --root <repo> --task bug
```

Pick 3-6 identifier-like keywords. Add likely synonyms yourself (discount, coupon, promo; auth, login, token). You supply the meaning; the tool filters the repo by name, path, parameter and docstring words.

How to read the result:
- `=== FULL path::Name Lstart-end` is the exact code.
- `=== OUTLINE` is signatures and line spans only; `=== MENTION` is a one-line pointer to a file.
- `=== TRUNCATED` is the top match cut to fit the budget; the last line says which `slice.py` range gives the rest.
- `OMITTED` lists what was left out. Treat it as a to-do: fetch what the task needs with `slice.py`.
- `WARNINGS` lists files it could not parse or skipped (ignored, huge, binary).
- `TOKENS` is an estimate, not an exact count.

Pick `--task` by what you are doing (it sets the token budget):
- `lookup`: "where is X?", "what does Y do?" (smallest)
- `test`: write or fix a test, small one-file bug
- `bug`: bug that touches several files
- `explore`: understand how an area or flow works
- `feature`: add a feature or refactor (largest)

Start with the smallest that fits. If the output says `BUDGET-LIMITED`, decide whether the omitted items matter; if they do, fetch them with `slice.py` or rerun with the suggested `--task` or `--budget`. Do not raise the budget "just in case". The hard cap is 8000 tokens.

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
- Callers are not traced at symbol level. For "who calls this?" use `deps.py --reverse` (files), then search inside those files.
- Dynamic imports are not traced. Not for non-Python repos (the tool says so). For tiny repos (under about 10 files) just read the files.
- Token numbers are estimates. More detail and worked examples: `references/workflow.md`.
