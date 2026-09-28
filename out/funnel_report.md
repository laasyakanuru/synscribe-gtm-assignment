# Funnel report

Run: 2026-09-28 · ACRA data downloaded: 2026-09-28 · seed: 20260928

| Stage | Count |
|---|---|
| 0. ACRA register, all entities | 2,117,243 |
| 1. Live local companies + foreign branches | 465,310 |
| 2a. Frame parents (data/frame.csv) | 1,629 |
|     qualified: MNC with a verified live Singapore entity | 898 |
|     not found in ACRA | 629 |
|     review matches only | 102 |
|     Singapore HQ, no mnc_basis given | 0 |
|     verified entities of qualified parents | 3,079 |
|     entities sent to 02_frame_review.csv | 3,038 |
| 2b. Foreign branches not in the frame (set aside: require_frame_match) | 1,639 |
| 2. Multinational entities carried forward | 3,079 |
| 3a. After not-a-buyer exclusions | 3,038 |
| 3b. After filter 1 (no commercial activity) | 3,035 |
| 3c. After filter 2 (secretarial address; frame matches only flagged) | 3,035 |
| 4. Candidate companies (one row per group) | 893 |
|    of which flagged for name-match review | 330 |
|    size segment: large | 839 |
|    size segment: mid | 54 |
|    global tier (Forbes Global 2000 or proxy) | 742 |
|    out of scope (not researched): large | 839 |
|    removed by prescreen (05b_prescreen_excluded.csv) | 8 |
| 5. LinkedIn checks (census) | 46 |
|    prescreen: pass | 25 |
|    prescreen: unsure | 21 |
| 6. Outbound: 2 not yet checked | 46 |

## Candidates by cell

| size_segment | industry_group | companies |
|---|---|---|
| large | High-trust | 52 |
| large | Other | 427 |
| large | Regulated | 234 |
| large | Technical | 126 |
| mid | High-trust | 3 |
| mid | Other | 14 |
| mid | Regulated | 21 |
| mid | Technical | 16 |


## Removed, by reason

| reason | entities |
|---|---|
| Not a buyer: Education | 17 |
| Not a buyer: Advertising | 10 |
| Not a buyer: Membership organisations | 7 |
| Not a buyer: Market research | 7 |
| No commercial activity: Holding companies | 3 |


## Filter 2 check: live entities sharing each multinational entity's address

Threshold: > 50 removed. Percentiles (p50/p75/p90/p95/p99): [18, 147, 532, 741, 2520]

| live entities at address | multinational entities |
|---|---|
| 0-1 | 398 |
| 2-5 | 630 |
| 6-20 | 555 |
| 21-50 | 362 |
| 51-100 | 230 |
| 101-500 | 485 |
| 500+ | 419 |

