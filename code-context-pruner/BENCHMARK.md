# Benchmark

**Test:** 15 tasks on four public Python repos (click 2247b35, jinja 5ef7011, sqlparse 60cdc64, tinydb edff96a), run on 2026-11-04. For each task I listed the functions a good answer needs, then checked how many arrived from one `pack.py` call. Every task was run two ways: **agent-style** (keywords plus identifiers) and **plain** (keywords only).

## Results

| | agent-style | plain |
|---|---|---|
| Token reduction vs reading the whole files (median) | 69.4% | 70.1% |
| Needed functions delivered as full code | 79.4% | 61.8% |
| Needed functions present in any form (full or outline) | 77.5% | 60.0% |
| Median size of the bundle | 1540 tokens | 1958 tokens |
| Token reduction vs grepping and opening the top 5 files (median) | 94.0% | 95.1% |
| Searches with LOW confidence | 0% | 0% |

## When a needed function is missing

42 needed functions were missing from a first `pack.py` call. What found them:

| Follow-up | Found |
|---|---|
| `pack.py "Class.method"` (only the qualified name) | 42 of 42 |
| `find.py "method_name"` (in the top 8 results) | 41 of 42 |
| `slice.py path/file.py:Class.method` (when the file path was shown) | 38 of 38 |
| `map.py <folder>` listed the name | 20 of 42 |

## Speed

Every call builds the index from scratch. On Django (2,937 Python files), one laptop: median 5.7 s for `map.py`, 7.2 s for `pack.py`, 18.5 s for `find.py`. On click (91 files): about 0.5 s.

## Reproduce

`tools/measure.py` with the task files in `bench/tasks/` (source repository).
