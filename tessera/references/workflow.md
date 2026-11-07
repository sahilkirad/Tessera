# Workflow notes for Tessera

Load this only when SKILL.md is not enough.

## Choosing keywords

- 3 to 6 words, identifier-like (`retry`, `session`, `cookie`, `signing`), not sentences.
- Names, paths, parameter names and the first docstring paragraph are searched. camelCase and snake_case are split, so `applyDiscount` finds `apply_discount`.
- A word of 4 or more letters also matches longer words that start with it (`discount` finds `discounts`).
- Rare words count more than common ones. Add one rare, specific word if results are generic.
- If a word appears in the `unmatched` list of `find.py`, it matched nothing in this repo: replace it with a synonym.
- If a first query missed a function whose exact name you know, retry with only the qualified name (see "When pack misses a function").

## Typical flows

Bug in one area:
1. `pack.py "kw1 kw2 kw3" --task bug --root R`
2. Read the FULL sections. If a function you need is under OMITTED, `slice.py file.py:Class.method`.
3. If you need callers, `deps.py file.py --reverse`.

Understand a flow:
1. `map.py --root R` for the top files, then `map.py folder --root R` to zoom in.
2. `pack.py "kw1 kw2" --task explore --root R`.
3. `slice.py file.py` for outlines of files that matter.

Edit a function:
1. `slice.py file.py:Class.method` for the exact current text (line numbers are looked up by name each time).
2. `slice.py file.py:Class.method --with-class` if the class header is needed.

## When pack misses a function

In the benchmark, 42 needed functions were missing from a first `pack.py` call. What found them:
1. `pack.py "Class.method" --root R` with ONLY the qualified name: 42 of 42.
2. `find.py "method_name" --root R`: in the top 8 results in 41 of 42 cases, top 20 in 42 of 42.
3. `slice.py path/file.py:Class.method --root R`: 38 of 38 where the file path had appeared in the pack output. `slice.py path/file.py` (outline) listed the name in 38 of 38.
4. `map.py folder --root R` listed the name in only 20 of 42: do not use it to find a known function.
If you cannot name the function, retry with different keywords, or use `find.py` and read its candidates.

## Reading BUDGET-LIMITED

`BUDGET-LIMITED: n relevant items omitted (a::X, b::Y). Rerun with --task bug or --budget 2500, or use slice.py.`
It means the budget ran out before every relevant item fit. The listed items are named. Either fetch just those with `slice.py`, or rerun once with the suggested budget. At the hard cap the message says so; use `slice.py` then.

## Limits to remember

- Python only. On a repository without Python files the tool says it supports Python only.
- Keyword search, no embeddings: you supply the meaning through the words you choose.
- Static analysis only: dynamic imports and runtime-generated code are not traced; unresolved imports are listed as EXTERNAL/UNRESOLVED in `deps.py`.
- Token counts are estimates (calibrated against one reference tokenizer; each model counts differently).
- Files that cannot be parsed (syntax errors, syntax newer than the Python running the tool) are listed in WARNINGS and shown as raw lines by `slice.py`.
- Ignored directories (virtualenvs, caches, root build and dist) and secret-looking files are never read; they are reported in WARNINGS.
