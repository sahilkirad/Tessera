# Benchmark summary

Estimates only (token counts are heuristic). Repos: click@2247b35, jinja@5ef7011, sqlparse@60cdc64, tinydb@edff96a.
Targets: median reduction vs B1 >= 60%; recall_full >= 85%. Headline = a holdout split only.

## HOLDOUT (headline): holdout2 / agent queries

### all repos (n=15)
- reduction vs B1 (whole files, the claim baseline): n=15 median 69.4% mean 62.9% p25 45.4% range 8.3% to 96.6%
- reduction vs B2 (grep and open 5 files): n=15 median 94.0% mean 92.8% p25 92.3% range 74.7% to 98.6%
- reduction vs B3 (exact line ranges, the hard baseline): n=15 median -273.2% mean -275.9% p25 -341.3% range -1085.6% to -2.1%
- recall_full (need=full entries, micro): 79.4%; per-task: n=15 median 100.0% mean 81.1% p25 58.3% range 33.3% to 100.0%
- recall_any (all entries, FULL or OUTLINE, micro): 77.5%
- pack tokens: n=15 median 1540.0 mean 1742.8 p25 1336.0 range 864.0 to 3167.0
- cold pack time (index + pack), ms: n=15 median 320.9 mean 728.7 p25 123.4 range 73.6 to 2707.9
- LOW confidence: 0% of tasks
- deterministic: 15/15; budget-limited: 9; recall misses: 6 (one escalation step fixed 1)

### click (n=4)
- reduction vs B1 (whole files, the claim baseline): n=4 median 77.8% mean 80.0% p25 72.6% range 67.8% to 96.6%
- reduction vs B2 (grep and open 5 files): n=4 median 97.7% mean 97.8% p25 97.4% range 97.3% to 98.6%
- reduction vs B3 (exact line ranges, the hard baseline): n=4 median -225.3% mean -384.6% p25 -524.8% range -1085.6% to -2.1%
- recall_full (need=full entries, micro): 70.0%; per-task: n=4 median 83.3% mean 75.0% p25 58.3% range 33.3% to 100.0%
- recall_any (all entries, FULL or OUTLINE, micro): 63.6%
- pack tokens: n=4 median 1478.5 mean 1571.8 p25 1392.5 range 1316.0 to 2014.0
- cold pack time (index + pack), ms: n=4 median 2358.0 mean 2163.2 p25 1955.4 range 1228.8 to 2707.9
- LOW confidence: 0% of tasks
- deterministic: 4/4; budget-limited: 4; recall misses: 2 (one escalation step fixed 0)

### jinja (n=4)
- reduction vs B1 (whole files, the claim baseline): n=4 median 81.5% mean 70.9% p25 65.2% range 33.3% to 87.3%
- reduction vs B2 (grep and open 5 files): n=4 median 94.3% mean 94.7% p25 93.7% range 92.8% to 97.5%
- reduction vs B3 (exact line ranges, the hard baseline): n=4 median -315.4% mean -360.5% p25 -391.7% range -532.1% to -279.0%
- recall_full (need=full entries, micro): 77.8%; per-task: n=4 median 75.0% mean 75.0% p25 50.0% range 50.0% to 100.0%
- recall_any (all entries, FULL or OUTLINE, micro): 80.0%
- pack tokens: n=4 median 2257.0 mean 2168.2 p25 1899.5 range 992.0 to 3167.0
- cold pack time (index + pack), ms: n=4 median 361.6 mean 364.1 p25 336.9 range 320.9 to 412.3
- LOW confidence: 0% of tasks
- deterministic: 4/4; budget-limited: 3; recall misses: 2 (one escalation step fixed 1)

### sqlparse (n=3)
- reduction vs B1 (whole files, the claim baseline): n=3 median 36.4% mean 33.0% p25 22.4% range 8.3% to 54.3%
- reduction vs B2 (grep and open 5 files): n=3 median 87.4% mean 84.7% p25 81.1% range 74.7% to 92.1%
- reduction vs B3 (exact line ranges, the hard baseline): n=3 median -132.6% mean -213.7% p25 -313.8% range -495.0% to -13.5%
- recall_full (need=full entries, micro): 85.7%; per-task: n=3 median 100.0% mean 88.9% p25 83.3% range 66.7% to 100.0%
- recall_any (all entries, FULL or OUTLINE, micro): 77.8%
- pack tokens: n=3 median 1913.0 mean 1865.0 p25 1726.5 range 1540.0 to 2142.0
- cold pack time (index + pack), ms: n=3 median 155.8 mean 160.2 p25 151.2 range 146.6 to 178.1
- LOW confidence: 0% of tasks
- deterministic: 3/3; budget-limited: 1; recall misses: 1 (one escalation step fixed 0)

### tinydb (n=4)
- reduction vs B1 (whole files, the claim baseline): n=4 median 67.2% mean 60.1% p25 55.7% range 27.6% to 78.4%
- reduction vs B2 (grep and open 5 files): n=4 median 92.5% mean 92.1% p25 91.5% range 88.7% to 94.7%
- reduction vs B3 (exact line ranges, the hard baseline): n=4 median -102.0% mean -129.3% p25 -188.5% range -273.2% to -40.2%
- recall_full (need=full entries, micro): 87.5%; per-task: n=4 median 100.0% mean 87.5% p25 87.5% range 50.0% to 100.0%
- recall_any (all entries, FULL or OUTLINE, micro): 90.0%
- pack tokens: n=4 median 1262.0 mean 1396.8 p25 1092.0 range 864.0 to 2199.0
- cold pack time (index + pack), ms: n=4 median 83.5 mean 85.2 p25 75.4 range 73.6 to 100.2
- LOW confidence: 0% of tasks
- deterministic: 4/4; budget-limited: 1; recall misses: 1 (one escalation step fixed 0)

### profile: lookup (n=3)
- reduction vs B1 (whole files, the claim baseline): n=3 median 69.4% mean 74.8% p25 68.6% range 67.8% to 87.2%
- reduction vs B2 (grep and open 5 files): n=3 median 97.4% mean 96.5% p25 96.0% range 94.7% to 97.5%
- reduction vs B3 (exact line ranges, the hard baseline): n=3 median -344.8% mean -567.9% p25 -715.2% range -1085.6% to -273.2%
- recall_full (need=full entries, micro): 100.0%; per-task: n=3 median 100.0% mean 100.0% p25 100.0% range 100.0% to 100.0%
- recall_any (all entries, FULL or OUTLINE, micro): 100.0%
- pack tokens: n=3 median 1168.0 mean 1158.7 p25 1080.0 range 992.0 to 1316.0
- cold pack time (index + pack), ms: n=3 median 412.3 mean 895.3 p25 244.2 range 76.0 to 2197.6
- LOW confidence: 0% of tasks
- deterministic: 3/3; budget-limited: 2; recall misses: 0 (one escalation step fixed 0)

### profile: bug (n=6)
- reduction vs B1 (whole files, the claim baseline): n=6 median 69.6% mean 64.0% p25 43.6% range 33.3% to 96.6%
- reduction vs B2 (grep and open 5 files): n=6 median 92.6% mean 90.8% p25 89.7% range 74.7% to 98.6%
- reduction vs B3 (exact line ranges, the hard baseline): n=6 median -78.3% mean -101.8% p25 -127.7% range -279.0% to -2.1%
- recall_full (need=full entries, micro): 85.7%; per-task: n=6 median 100.0% mean 86.1% p25 75.0% range 50.0% to 100.0%
- recall_any (all entries, FULL or OUTLINE, micro): 83.3%
- pack tokens: n=6 median 1539.5 mean 1709.0 p25 1448.2 range 1356.0 to 2202.0
- cold pack time (index + pack), ms: n=6 median 249.1 mean 739.4 p25 114.1 range 90.9 to 2518.4
- LOW confidence: 0% of tasks
- deterministic: 6/6; budget-limited: 5; recall misses: 2 (one escalation step fixed 0)

### profile: explore (n=2)
- reduction vs B1 (whole files, the claim baseline): n=2 median 70.8% mean 70.8% p25 62.6% range 54.3% to 87.3%
- reduction vs B2 (grep and open 5 files): n=2 median 93.0% mean 93.0% p25 92.5% range 92.1% to 94.0%
- reduction vs B3 (exact line ranges, the hard baseline): n=2 median -390.5% mean -390.5% p25 -442.7% range -495.0% to -286.0%
- recall_full (need=full entries, micro): 60.0%; per-task: n=2 median 58.3% mean 58.3% p25 54.2% range 50.0% to 66.7%
- recall_any (all entries, FULL or OUTLINE, micro): 66.7%
- pack tokens: n=2 median 2227.0 mean 2227.0 p25 2184.5 range 2142.0 to 2312.0
- cold pack time (index + pack), ms: n=2 median 249.5 mean 249.5 p25 213.8 range 178.1 to 320.9
- LOW confidence: 0% of tasks
- deterministic: 2/2; budget-limited: 0; recall misses: 2 (one escalation step fixed 0)

### profile: feature (n=4)
- reduction vs B1 (whole files, the claim baseline): n=4 median 51.7% mean 48.2% p25 22.8% range 8.3% to 81.3%
- reduction vs B2 (grep and open 5 files): n=4 median 93.5% mean 93.1% p25 91.2% range 87.4% to 98.0%
- reduction vs B3 (exact line ranges, the hard baseline): n=4 median -249.0% mean -260.9% p25 -386.4% range -532.1% to -13.5%
- recall_full (need=full entries, micro): 66.7%; per-task: n=4 median 75.0% mean 70.8% p25 45.8% range 33.3% to 100.0%
- recall_any (all entries, FULL or OUTLINE, micro): 60.0%
- pack tokens: n=4 median 1963.5 mean 1989.5 p25 1650.8 range 864.0 to 3167.0
- cold pack time (index + pack), ms: n=4 median 263.8 mean 827.2 p25 128.3 range 73.6 to 2707.9
- LOW confidence: 0% of tasks
- deterministic: 4/4; budget-limited: 2; recall misses: 2 (one escalation step fixed 1)

## HOLDOUT (headline): holdout2 / naive queries

### all repos (n=15)
- reduction vs B1 (whole files, the claim baseline): n=15 median 70.1% mean 62.3% p25 41.4% range 6.0% to 94.6%
- reduction vs B2 (grep and open 5 files): n=15 median 95.1% mean 94.8% p25 92.6% range 89.1% to 98.7%
- reduction vs B3 (exact line ranges, the hard baseline): n=15 median -217.5% mean -283.1% p25 -337.2% range -1092.8% to 16.8%
- recall_full (need=full entries, micro): 61.8%; per-task: n=15 median 50.0% mean 60.0% p25 50.0% range 0.0% to 100.0%
- recall_any (all entries, FULL or OUTLINE, micro): 60.0%
- pack tokens: n=15 median 1958.0 mean 1808.4 p25 1175.0 range 708.0 to 3160.0
- cold pack time (index + pack), ms: n=15 median 360.2 mean 957.0 p25 164.7 range 65.4 to 2510.4
- LOW confidence: 0% of tasks
- deterministic: 15/15; budget-limited: 9; recall misses: 11 (one escalation step fixed 1)

### click (n=4)
- reduction vs B1 (whole files, the claim baseline): n=4 median 74.4% mean 76.4% p25 66.3% range 62.3% to 94.6%
- reduction vs B2 (grep and open 5 files): n=4 median 97.8% mean 97.9% p25 97.7% range 97.5% to 98.4%
- reduction vs B3 (exact line ranges, the hard baseline): n=4 median -276.3% mean -427.0% p25 -528.9% range -1092.8% to -62.6%
- recall_full (need=full entries, micro): 80.0%; per-task: n=4 median 83.3% mean 79.2% p25 62.5% range 50.0% to 100.0%
- recall_any (all entries, FULL or OUTLINE, micro): 81.8%
- pack tokens: n=4 median 2141.0 mean 1966.0 p25 1852.0 range 1324.0 to 2258.0
- cold pack time (index + pack), ms: n=4 median 2428.2 mean 2343.8 p25 2321.7 range 2008.3 to 2510.4
- LOW confidence: 0% of tasks
- deterministic: 4/4; budget-limited: 4; recall misses: 2 (one escalation step fixed 0)

### jinja (n=4)
- reduction vs B1 (whole files, the claim baseline): n=4 median 80.8% mean 73.3% p25 67.1% range 40.7% to 90.9%
- reduction vs B2 (grep and open 5 files): n=4 median 94.8% mean 95.5% p25 94.4% range 93.7% to 98.7%
- reduction vs B3 (exact line ranges, the hard baseline): n=4 median -285.3% mean -329.7% p25 -382.9% range -530.7% to -217.5%
- recall_full (need=full entries, micro): 55.6%; per-task: n=4 median 58.3% mean 54.2% p25 37.5% range 0.0% to 100.0%
- recall_any (all entries, FULL or OUTLINE, micro): 50.0%
- pack tokens: n=4 median 2277.5 mean 2105.8 p25 1645.5 range 708.0 to 3160.0
- cold pack time (index + pack), ms: n=4 median 367.2 mean 819.0 p25 355.3 range 340.7 to 2200.9
- LOW confidence: 0% of tasks
- deterministic: 4/4; budget-limited: 3; recall misses: 3 (one escalation step fixed 1)

### sqlparse (n=3)
- reduction vs B1 (whole files, the claim baseline): n=3 median 38.5% mean 28.9% p25 22.2% range 6.0% to 42.1%
- reduction vs B2 (grep and open 5 files): n=3 median 91.6% mean 91.6% p25 90.4% range 89.1% to 93.9%
- reduction vs B3 (exact line ranges, the hard baseline): n=3 median -125.1% mean -265.1% p25 -389.5% range -653.9% to -16.4%
- recall_full (need=full entries, micro): 42.9%; per-task: n=3 median 50.0% mean 38.9% p25 25.0% range 0.0% to 66.7%
- recall_any (all entries, FULL or OUTLINE, micro): 44.4%
- pack tokens: n=3 median 1961.0 mean 2055.0 p25 1725.5 range 1490.0 to 2714.0
- cold pack time (index + pack), ms: n=3 median 167.5 mean 389.2 p25 164.7 range 161.8 to 838.4
- LOW confidence: 0% of tasks
- deterministic: 3/3; budget-limited: 2; recall misses: 3 (one escalation step fixed 0)

### tinydb (n=4)
- reduction vs B1 (whole files, the claim baseline): n=4 median 71.6% mean 62.4% p25 57.4% range 19.2% to 87.2%
- reduction vs B2 (grep and open 5 files): n=4 median 93.5% mean 93.3% p25 91.4% range 90.9% to 95.5%
- reduction vs B3 (exact line ranges, the hard baseline): n=4 median -106.6% mean -106.1% p25 -199.7% range -227.8% to 16.8%
- recall_full (need=full entries, micro): 62.5%; per-task: n=4 median 50.0% mean 62.5% p25 50.0% range 50.0% to 100.0%
- recall_any (all entries, FULL or OUTLINE, micro): 60.0%
- pack tokens: n=4 median 995.0 mean 1168.5 p25 924.2 range 805.0 to 1879.0
- cold pack time (index + pack), ms: n=4 median 84.2 mean 134.2 p25 75.8 range 65.4 to 302.8
- LOW confidence: 0% of tasks
- deterministic: 4/4; budget-limited: 0; recall misses: 3 (one escalation step fixed 0)

### profile: lookup (n=3)
- reduction vs B1 (whole files, the claim baseline): n=3 median 73.2% mean 77.2% p25 70.4% range 67.6% to 90.9%
- reduction vs B2 (grep and open 5 files): n=3 median 98.4% mean 97.5% p25 96.9% range 95.4% to 98.7%
- reduction vs B3 (exact line ranges, the hard baseline): n=3 median -227.8% mean -512.7% p25 -660.3% range -1092.8% to -217.5%
- recall_full (need=full entries, micro): 66.7%; per-task: n=3 median 50.0% mean 66.7% p25 50.0% range 50.0% to 100.0%
- recall_any (all entries, FULL or OUTLINE, micro): 66.7%
- pack tokens: n=3 median 1026.0 mean 1019.3 p25 867.0 range 708.0 to 1324.0
- cold pack time (index + pack), ms: n=3 median 340.7 mean 948.7 p25 209.9 range 79.2 to 2426.1
- LOW confidence: 0% of tasks
- deterministic: 3/3; budget-limited: 2; recall misses: 2 (one escalation step fixed 1)

### profile: bug (n=6)
- reduction vs B1 (whole files, the claim baseline): n=6 median 66.2% mean 65.6% p25 46.1% range 38.5% to 94.6%
- reduction vs B2 (grep and open 5 files): n=6 median 95.3% mean 95.1% p25 94.2% range 90.9% to 97.7%
- reduction vs B3 (exact line ranges, the hard baseline): n=6 median -93.8% mean -107.1% p25 -190.1% range -237.0% to 16.8%
- recall_full (need=full entries, micro): 71.4%; per-task: n=6 median 58.3% mean 69.4% p25 50.0% range 50.0% to 100.0%
- recall_any (all entries, FULL or OUTLINE, micro): 66.7%
- pack tokens: n=6 median 1918.5 mean 1774.0 p25 1587.2 range 805.0 to 2258.0
- cold pack time (index + pack), ms: n=6 median 338.6 mean 908.8 p25 201.3 range 89.3 to 2510.4
- LOW confidence: 0% of tasks
- deterministic: 6/6; budget-limited: 4; recall misses: 4 (one escalation step fixed 0)

### profile: explore (n=2)
- reduction vs B1 (whole files, the claim baseline): n=2 median 63.9% mean 63.9% p25 53.0% range 42.1% to 85.7%
- reduction vs B2 (grep and open 5 files): n=2 median 91.4% mean 91.4% p25 90.3% range 89.1% to 93.7%
- reduction vs B3 (exact line ranges, the hard baseline): n=2 median -493.7% mean -493.7% p25 -573.8% range -653.9% to -333.6%
- recall_full (need=full entries, micro): 40.0%; per-task: n=2 median 33.3% mean 33.3% p25 16.7% range 0.0% to 66.7%
- recall_any (all entries, FULL or OUTLINE, micro): 33.3%
- pack tokens: n=2 median 2655.5 mean 2655.5 p25 2626.2 range 2597.0 to 2714.0
- cold pack time (index + pack), ms: n=2 median 1519.7 mean 1519.7 p25 1179.0 range 838.4 to 2200.9
- LOW confidence: 0% of tasks
- deterministic: 2/2; budget-limited: 1; recall misses: 2 (one escalation step fixed 0)

### profile: feature (n=4)
- reduction vs B1 (whole files, the claim baseline): n=4 median 47.5% mean 45.5% p25 15.9% range 6.0% to 81.1%
- reduction vs B2 (grep and open 5 files): n=4 median 93.1% mean 93.9% p25 91.6% range 91.6% to 98.0%
- reduction vs B3 (exact line ranges, the hard baseline): n=4 median -265.6% mean -269.6% p25 -388.3% range -530.7% to -16.4%
- recall_full (need=full entries, micro): 55.6%; per-task: n=4 median 58.3% mean 54.2% p25 37.5% range 0.0% to 100.0%
- recall_any (all entries, FULL or OUTLINE, micro): 60.0%
- pack tokens: n=4 median 1994.5 mean 2028.2 p25 1711.8 range 964.0 to 3160.0
- cold pack time (index + pack), ms: n=4 median 261.0 mean 754.5 p25 137.7 range 65.4 to 2430.4
- LOW confidence: 0% of tasks
- deterministic: 4/4; budget-limited: 2; recall misses: 3 (one escalation step fixed 0)

## Per-task results

| id | style | split | profile | conf | tokens | B1 | red B1 | recall_full | recall_any | ms | note |
|---|---|---|---|---|---|---|---|---|---|---|---|
| click-02 | naive | holdout2 | bug | MEDIUM | 2258 | 41860 | 95% | 0.50 | 0.67 | 2008 | recall miss |
| click-02 | agent | holdout2 | bug | MEDIUM | 1418 | 41860 | 97% | 1.00 | 0.67 | 1229 |  |
| click-04 | naive | holdout2 | feature | MEDIUM | 2028 | 10751 | 81% | 0.67 | 0.67 | 2430 | recall miss |
| click-04 | agent | holdout2 | feature | MEDIUM | 2014 | 10751 | 81% | 0.33 | 0.33 | 2708 | recall miss |
| click-06 | naive | holdout2 | bug | HIGH | 2254 | 5973 | 62% | 1.00 | 1.00 | 2510 |  |
| click-06 | agent | holdout2 | bug | HIGH | 1539 | 5973 | 74% | 0.67 | 0.67 | 2518 | recall miss |
| click-07 | naive | holdout2 | lookup | MEDIUM | 1324 | 4091 | 68% | 1.00 | 1.00 | 2426 |  |
| click-07 | agent | holdout2 | lookup | HIGH | 1316 | 4091 | 68% | 1.00 | 1.00 | 2198 |  |
| jinja-02 | naive | holdout2 | explore | MEDIUM | 2597 | 18211 | 86% | 0.00 | 0.00 | 2201 | recall miss |
| jinja-02 | agent | holdout2 | explore | MEDIUM | 2312 | 18211 | 87% | 0.50 | 0.67 | 321 | recall miss |
| jinja-04 | naive | holdout2 | feature | MEDIUM | 3160 | 13094 | 76% | 1.00 | 1.00 | 360 |  |
| jinja-04 | agent | holdout2 | feature | MEDIUM | 3167 | 13094 | 76% | 0.50 | 0.50 | 381 | recall miss, escalation fixes |
| jinja-05 | naive | holdout2 | bug | HIGH | 1958 | 3302 | 41% | 0.67 | 0.67 | 374 | recall miss |
| jinja-05 | agent | holdout2 | bug | HIGH | 2202 | 3302 | 33% | 1.00 | 1.00 | 342 |  |
| jinja-07 | naive | holdout2 | lookup | MEDIUM | 708 | 7780 | 91% | 0.50 | 0.50 | 341 | recall miss, escalation fixes |
| jinja-07 | agent | holdout2 | lookup | HIGH | 992 | 7780 | 87% | 1.00 | 1.00 | 412 |  |
| sqlparse-02 | naive | holdout2 | explore | HIGH | 2714 | 4688 | 42% | 0.67 | 0.67 | 838 | recall miss |
| sqlparse-02 | agent | holdout2 | explore | HIGH | 2142 | 4688 | 54% | 0.67 | 0.67 | 178 | recall miss |
| sqlparse-04 | naive | holdout2 | feature | HIGH | 1961 | 2086 | 6% | 0.00 | 0.33 | 162 | recall miss |
| sqlparse-04 | agent | holdout2 | feature | HIGH | 1913 | 2086 | 8% | 1.00 | 0.67 | 147 |  |
| sqlparse-06 | naive | holdout2 | bug | MEDIUM | 1490 | 2423 | 39% | 0.50 | 0.33 | 168 | recall miss |
| sqlparse-06 | agent | holdout2 | bug | MEDIUM | 1540 | 2423 | 36% | 1.00 | 1.00 | 156 |  |
| tinydb-02 | naive | holdout2 | bug | MEDIUM | 1879 | 6288 | 70% | 1.00 | 1.00 | 303 |  |
| tinydb-02 | agent | holdout2 | bug | MEDIUM | 2199 | 6288 | 65% | 1.00 | 1.00 | 91 |  |
| tinydb-04 | naive | holdout2 | feature | MEDIUM | 964 | 1193 | 19% | 0.50 | 0.50 | 65 | recall miss |
| tinydb-04 | agent | holdout2 | feature | MEDIUM | 864 | 1193 | 28% | 1.00 | 1.00 | 74 |  |
| tinydb-05 | naive | holdout2 | lookup | HIGH | 1026 | 3823 | 73% | 0.50 | 0.50 | 79 | recall miss |
| tinydb-05 | agent | holdout2 | lookup | HIGH | 1168 | 3823 | 69% | 1.00 | 1.00 | 76 |  |
| tinydb-07 | naive | holdout2 | bug | HIGH | 805 | 6288 | 87% | 0.50 | 0.33 | 89 | recall miss |
| tinydb-07 | agent | holdout2 | bug | HIGH | 1356 | 6288 | 78% | 0.50 | 0.67 | 100 | recall miss |

## Notes added after the run (derived from holdout2_results.json; the run itself was not repeated)

- Run once on frozen code (scripts and references matched `frozen_manifest.json` before and after). Repos: click@2247b35, jinja@5ef7011, sqlparse@60cdc64, tinydb@edff96a.
- Run date 2026-11-04. Labels were audited by four independent AI reviewer agents (`holdout2_label_audit.md`: 40 labels, 0 factual errors, none changed). Spot-check: not performed by the author; labels audited only by four independent AI reviewer agents.
- n is small (15 tasks per query style, 4 repos, 30 task-style runs). Read ranges, not only medians. The tool was tuned on dev, dev2 and the first holdout, never on holdout2.
- Targets: median reduction vs B1 >= 60% (met in both styles); recall_full >= 85% (NOT met: agent 79.4%, naive 61.8%).
- Tasks where the pack was as large as or larger than whole files (B1): 0 of 30 runs. Versus the exact needed line ranges (B3, the hard baseline) the pack is larger in almost every run: median -273.2% (agent) and -217.5% (naive); only one naive run was smaller (best case +16.8%).
- Budget-limited runs: agent 9 of 15, naive 9 of 15 (the footer says what was omitted).
- LOW-confidence rate: 0% in both styles.
- Confidence HIGH, agent queries: 8 runs, recall_full 16/19 = 84.2%.
- Confidence MEDIUM, agent queries: 7 runs, recall_full 11/15 = 73.3%.
- Confidence HIGH, naive queries: 6 runs, recall_full 9/15 = 60.0%.
- Confidence MEDIUM, naive queries: 9 runs, recall_full 12/19 = 63.2%.
- Misses (recall_full < 1.0) are flagged in the per-task table above; the profile `test` has no holdout2 task.
