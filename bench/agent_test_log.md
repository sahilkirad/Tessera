# Agent test log (manual, run by Sahil)

These runs are anecdotal: n=5 tasks per agent, one run each, no repeats. Do not quote them as statistics.

## How to run
1. Pick a Python repo (for example a clone in `bench/repos/`), and 5 realistic tasks (mix: lookup, bug, explore, feature, test).
2. For each agent (Gemini CLI, plus Claude Code or Cursor): run every task twice, once WITHOUT the skill installed and once WITH it.
3. Do not name the skill in the prompt for the "activated" check. If you must nudge ("use the code-context-pruner skill"), write that in notes and count it as not activated.
4. Record the token figure the agent UI reports, and judge correctness against a note you wrote BEFORE the run.

Pass criteria: activated on at least 4 of 5 tasks without being named; correctness with the skill equal to or better than without; tokens lower with the skill on most tasks. If activation is low, change the SKILL.md `description` trigger words first, before touching code.

## Results

| agent | task | skill? | skill activated (Y/N) | tokens reported by agent UI | answer correct (Y/N) | notes |
|---|---|---|---|---|---|---|
| gemini-cli | 1 | no | n/a | | | |
| gemini-cli | 1 | yes | | | | |
| gemini-cli | 2 | no | n/a | | | |
| gemini-cli | 2 | yes | | | | |
| gemini-cli | 3 | no | n/a | | | |
| gemini-cli | 3 | yes | | | | |
| gemini-cli | 4 | no | n/a | | | |
| gemini-cli | 4 | yes | | | | |
| gemini-cli | 5 | no | n/a | | | |
| gemini-cli | 5 | yes | | | | |
| claude-code | 1 | no | n/a | | | |
| claude-code | 1 | yes | | | | |
| claude-code | 2 | no | n/a | | | |
| claude-code | 2 | yes | | | | |
| claude-code | 3 | no | n/a | | | |
| claude-code | 3 | yes | | | | |
| claude-code | 4 | no | n/a | | | |
| claude-code | 4 | yes | | | | |
| claude-code | 5 | no | n/a | | | |
| claude-code | 5 | yes | | | | |

## Task list (fill in before running)
1.
2.
3.
4.
5.

## Summary (fill in after)
- Activation rate per agent:
- Correctness with vs without:
- Token difference with vs without:
- What broke (tool output wording, SKILL.md text, activation) and what was changed:
