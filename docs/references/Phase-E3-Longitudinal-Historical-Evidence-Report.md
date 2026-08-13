# Phase E3 Longitudinal Historical Evidence Report

> **Status:** CURRENT_RESEARCH_PROGRAM
> **Evidence Date:** 2026-08-14
> **Branch Base:** `origin/main@796b868c55bc9a3e58e427cbbfbba101a5936606`
> **Computation Revision:** `c52e011f3b76636d77ad3e0d23376c4bec1607fc`
> **Migration Head:** `084`
> **Qualification Ceiling:** `EXPLORATORY`, `PIT_INCOMPLETE`, `FORMAL_OOS=false`, `CALIBRATED=false`

## Outcome

Phase E3 runs the unchanged Phase E methodology over 126 Decision Sessions and
300 effective-dated CSI 300 members per session. It proves longitudinal cohort
switching, owner-resolved historical Industry/share/corporate-action facts,
bounded Decision and Evidence execution, explicit raw-return exclusions and a
durable long-window research result.

It does not prove Alpha. BaoStock returned successful but empty history for the
frozen `510300.SH` ETF context in every requested interval. The canonical ETF
layer is therefore `NOT_ESTIMABLE`, Capital remains `DATA_INSUFFICIENT`, all
37,800 Candidates are rejected, and no Signal or canonical Forecast is emitted.
The absence is preserved rather than substituted with the CSI 300 index or a
Daily-only series.

The fixed exploratory ridge challenger is estimable over the same owner-resolved
Panel and is slightly positive in later temporal validation. That result is not
the canonical Forecast, Formal OOS, calibration, economic evidence or model
qualification.

## Immutable Authority and corpus

| Owner | Exact identity |
|---|---|
| Constituent Timeline | `historical-constituent-timeline:af987d1d42d9137abaab010ca6047b8a09ea27cb6d2936480566ec2fc8bb9b58` |
| Historical Security Facts | `historical-security-facts:4fc1085c2579c2fae6028636d8c506b30f1f39884440a3ebf0dad57546aa28df` |
| Raw Provider Archive | `historical-data-owner-24e9dfe065796098a2c04c11` / `sha256:24e9dfe065796098a2c04c1156f2048afc454a29e842bbba7edd1dc039e6f7de` |
| Normalized Dataset | `historical-data-owner-c4cc4f5fd5a39248c116b3e7` / `sha256:c4cc4f5fd5a39248c116b3e72d83dac09cb7ee6466f8ef84f803e64b4c38ea77` |
| Experiment | `research-experiment-definition:c5235ae4ed7918878b1dd63aee7b4cb6e14d135b3c02b757923bbcc8350fa267` |
| Feature Configuration | `feature-set-aaea2725245b1656b94dd89c` |
| Economics Policy Set | `historical-strategy-economics-policy-set:5181e60fd842149a41c709fa7469b388b61aa68b02439f82b7d6cbfabf047042` |
| Context Instruments | `historical-context-instrument-set:d515dd6c78c63fcc8dd9703822af85ee0e3b67529333616b391ba731f07b5acf` |
| Resumed Run | `historical-research-run-b14ae344d2c3571d5ba842ce` / command `sha256:b14ae344d2c3571d5ba842ced7596e0a63e48495e4b8b24815ea8c3ed3baf6da` |

The real corpus covers Daily observations from 2024-06-03 through 2025-07-14
and 5-minute observations from 2025-01-02 through 2025-07-14. The run covers
126 Decision Sessions from 2025-01-02 through 2025-07-11; 2025-07-14 is used
only as the last T+1 Outcome session.

| Corpus measurement | Value |
|---|---:|
| Active equities per Decision | 300 |
| Equity union | 308 |
| Declared context | `000300.SH`, `510300.SH` |
| Expected symbols | 310 |
| Observed symbols | 309 |
| Provider requests/checkpoints | 2,790 / 2,790 successful |
| Raw records | 1,954,644 |
| Normalized records | 1,954,644 |
| Raw / normalized partitions | 1,080 / 1,080 |
| Raw package size | 41 MiB |
| Normalized package size | 249 MiB |
| Recovery checkpoints | 260 MiB |
| Full Artifact Root | 680 MiB |

Every request is archived through a content-verified checkpoint. Raw and
normalized physical hashes are respectively
`sha256:113b9e3b1b13fcd03234768e3ab3e40d9e617df223a07aaf23ec6e029978996d`
and
`sha256:99834f359901bbef139676bcffbbc918923c24c53e46429f69153707fc213e06`.
Intraday raw locators include month and cannot overwrite another monthly
request under one annual logical partition.

## Longitudinal Universe

The Timeline maps 127 queried trading sessions to 29 distinct effective-date
cohort owners. Each cohort contains exactly 300 included members. Weekly
Provider effective snapshots are not interpreted as weekly index changes:
membership differs at only two observed boundaries.

| Effective date | Added | Removed |
|---|---|---|
| 2025-03-10 | `601058.SH` | `600837.SH` |
| 2025-06-16 | `001391.SZ`, `002600.SZ`, `301236.SZ`, `302132.SZ`, `601077.SH`, `601825.SH`, `688047.SH` | `002007.SZ`, `002271.SZ`, `002555.SZ`, `002812.SZ`, `300450.SZ`, `600745.SH`, `603659.SH` |

Boundary-day Scope receipts bind the exact active snapshot ID and hash.
`600837.SH` has a retrieved lifecycle delisting date of 2025-03-04; it is
explicitly excluded for March 4 through March 7 even though the Provider cohort
does not remove it until March 10. No current member or classification is
backfilled into an earlier cohort. All 308 union symbols have retrieved listing
dates; two have delisting dates. Lifecycle dates can support listing age and
delisting exclusion but remain retrospective free-data facts, not Formal PIT.

Historical trading eligibility produces 37,778 included, 18 unknown and four
delisting-excluded symbol-sessions. Daily trading/ST observations are consumed
when present. Minute ST status is absent, and absent status remains unknown.

## Historical business facts

The exact fact owner contains 10,668 normalized facts and one fail-closed
coverage gap:

| Fact kind | Rows | Symbols | Effective range |
|---|---:|---:|---|
| Industry | 8,909 | 308 | 2024-12-30 to 2025-07-14 |
| Published share capital | 921 | 307 | 2024-12-31 to 2025-06-30 |
| Adjustment event | 229 | 206 | 2025-01-07 to 2025-07-14 |
| Dividend/split/rights event | 609 | 295 | 2024-03-29 to 2025-07-14 |

Industry is available on all 37,800 Panel rows across 42 observed classifications.
Decision-time market-cap buckets are available on 19,022 rows (50.32%): 15,351
large and 3,671 mid cap. The remaining 18,778 rows are `NOT_ESTIMABLE` because
no published-at-Decision share row is available. Rows published after a
Decision remain in the owner for later dates but cannot enter the temporal
projection.

The sole coverage gap is a conflicting `300760.SZ` dividend response. It is
retained as an interval gap rather than choosing one value. No classification,
share, adjustment or corporate-action fact is synthesized.

## Bounded execution and recovery

Selected Parquet reads resolve exact timeframe/date/symbol buckets from the
PostgreSQL owner, verify selected files and physical hashes, project seven
columns, push predicates into Arrow and reconstruct records in bounded batches.
Daily reads are capped at the 180-calendar-day frozen lookback and retain at
most the 61 pre-Decision observations required by canonical features. Sparse or
suspended symbols cannot force a scan to package start. Previous/current/T+1
minute windows use bounded LRU entries.

At the 300-symbol cross-section, the largest physical Daily read verifies 240
bucket/year partitions, 13,728,693 bytes and 36,722 predicate-matching rows;
the largest 5-minute read verifies 120 monthly bucket partitions, 40,175,345
bytes and 14,400 rows. Arrow emits at most 952 Daily or 384 minute rows in one
physical batch in this corpus, below the declared 8,192-row ceiling. These are
per-window maxima, independent of the number of completed run sessions.

The terminal run contains 126 complete sessions, 756 complete stage receipts
and 1,638 content-addressed components: exactly 126 owners for each of the 13
Feature through Research Panel kinds. The real public CLI interruption stopped
after seven committed receipts. A fresh process resumed the same run to
`COMPLETE` without rewriting a receipt or owner.

| Operation | Wall time | Peak RSS | Swap | Result |
|---|---:|---:|---:|---|
| Universe range scan | 157.03 s | 197,132,288 B | 0 | 127 session responses / 29 cohorts |
| Security fact acquisition/recovery | 25.77 s | 361,775,104 B | 0 | 10,668 facts / one gap |
| Corpus acquire + publish | 2,452.87 s | 5,396,152,320 B | 0 | 1,954,644 records |
| Seven-receipt interrupted run | 30.38 s | 733,970,432 B | 0 | durable `RUNNING` |
| Fresh-process resume | 3,413.68 s | 1,412,218,880 B | 0 | `COMPLETE` |
| Streaming Evidence | 66.40 s | 378,732,544 B | 0 | 37,375 observations |
| Exact replay | 3,146.60 s | 1,214,398,464 B | 0 | `matched=true` |
| Independent uninterrupted | 4,021.03 s | 1,021,722,624 B | 0 | `COMPLETE` |
| Independent Evidence | 66.96 s | 371,392,512 B | 0 | same five owners |

Decision execution is bounded by session/window caches, and Evidence is bounded
by a four-component keyset batch plus at most 299 estimable observations in one
session cross-section. Evidence does not load the full normalized package,
Panel component set or observation graph.

Corpus acquisition/publishing still peaks at about 5.03 GiB because the
Provider archive publisher retains a full acquisition object graph before
partition publication. This is a real remaining engineering gap for 1--3 year
acquisition and prevents a claim that every Phase E3 process is bounded at the
Decision/Evidence ceiling.

## Temporal, lineage and missingness audit

| Audit | Result |
|---|---|
| Decision cutoff | zero violations across every Decision-side component: `source_max_event_time <= decision_time` |
| T+1 session order | 126/126 Outcome owners use the exact next trading session, 2025-01-03 through 2025-07-14 |
| Outcome isolation | T+1 labels exist only in Outcome/Panel; Decision Candidate/Signal/Forecast cannot read current Outcome |
| Target preservation | 37,375 estimable; 425 explicit missing rows; no missing row is silently selected away |
| Corporate actions | 2,082 of 226,800 six-checkpoint labels fail closed; 1,326 cross a known action and 756 intersect the coverage gap |
| Constituent drift | exact snapshot switches on both observed change boundaries; inactive cohort members are not context |
| Current classification | never backfilled; Industry comes only from the fact owner |
| Context identity | Market Regime consumes only `000300.SH`; Theme declares only `510300.SH` as ETF |
| Replay | `historical-replay-f21e7f11519bd96c339d716f`; `sha256:f21e7f11519bd96c339d716f1edb972f94ce0ee0625b9aad53c6dd73db22af29`; 126 recomputed sessions; zero mismatches |
| Resumed vs uninterrupted | all eight ordered Authority sets have identical counts and SHA-256 digests |

The independent database was restored from the owner-only Authority snapshot,
then its run-owned rows were removed before the same command was executed from
the beginning. The comparison excludes operational database timestamps but
includes every content-addressed payload and its canonical materialization
time. It is therefore a result-identity comparison, not a status-only check.

| Ordered set | Rows | Shared SHA-256 digest |
|---|---:|---|
| Run | 1 | `241dfd43544c949b2b8de9809608d4eee351b3e0fc5895aaedc1cfc9b64810ce` |
| Sessions | 126 | `7874bdb58e276eaae766559f4529c833b3f20a39734ee0a0608bf3041900dafc` |
| Stage receipts | 756 | `a4c58acddf573864c8b6c709a7eaf63055679fd3103106e1581a5d884468b008` |
| Components | 1,638 | `3d7a75c4a0175f3df991a79ef707be91c5a811aea07b62e937a97603c1b9dba0` |
| Component bindings | 6,174 | `abec7fee3e4e0768553700e1f932b8abfccc0e4c568518edc4489f87ebfb09e0` |
| Evidence owners | 5 | `554b8f9dc70e8d3d023cf79d464be55af4e979eec78387a14638d3654c9feefc` |
| Evidence metrics | 11,974 | `fa683065c98d21c18074f44cb91181c5bd114400952b70af97508f86cef77785` |
| Evidence bindings | 1,138 | `a507be445a65963db69852834455dea875c07199065046372a3a57d33542289a` |

For the frozen T+1 10:30 Panel, target statuses are 37,159 complete, 216
partial, 347 corporate-action-excluded and 78 unavailable. Complete and partial
labels supply the 37,375 estimable observations; excluded and unavailable labels
remain explicit. Across all six checkpoints, 223,244 labels are complete, 1,154
partial and 2,402 unavailable.

## Canonical chain coverage

| Layer | Observation coverage | Longitudinal result |
|---|---:|---|
| Price | 37,359 / 37,375 | available |
| Volume | 37,319 / 37,375 | available |
| Market Regime | 22,529 / 37,375 | available but regime-dependent |
| ETF | 0 / 37,375 | `NOT_ESTIMABLE`: no `510300.SH` observations |
| Theme | 37,077 / 37,375 | global proxy, not Industry theme ownership |
| Capital | 0 / 37,375 | `NOT_ESTIMABLE`: ETF amount expansion absent |
| Dynamic Pool | 37,375 / 37,375 | available |
| Candidate | 0 / 37,375 | `NOT_ESTIMABLE`: no selected Candidate |
| Signal | 0 / 37,375 | `NOT_ESTIMABLE`: no selected Candidate |
| Forecast | 0 / 37,375 | `NOT_ESTIMABLE`: no Signal, not a lowered sample floor |

Market Regime covers 50 `DATA_INSUFFICIENT`, 55 `RISK_NEUTRAL`, 19
`RISK_OFF` and two `RISK_ON` sessions. Theme covers `STARTING` 69,
`WEAKENING` 37, `STRENGTHENING` 11, `FAILED` six, `DIVERGING` two and one
`DATA_INSUFFICIENT` session. Capital is `DATA_INSUFFICIENT` in all 126
sessions.

All 37,800 Candidate records are rejected: 15,595 because Capital is not
qualified, 14,978 because Regime prohibits risk, 7,199 because Theme is not
qualified, 22 because Dynamic Pool excludes/marks eligibility unknown and six
because liquidity is insufficient. Signal diagnostics therefore contain
37,800 `NOT_EMITTED_NOT_SELECTED` states, and Forecast contains 37,800
`NOT_EMITTED_NO_SIGNAL` states. The frozen Forecast
`minimum_usable_samples=20` is unchanged; the maximum usable canonical sample
count is zero because there is no Signal to forecast.

## Ablation and stability

All figures below are T+1 10:30 cross-sectional research metrics. Cost and net
remain engineering-assumption economics.

| Variant | RankIC | Gross | Cost | Net | Incremental lift |
|---|---:|---:|---:|---:|---:|
| Price | -0.061679 | -0.000827 | 0.002100 | -0.002927 | `NOT_ESTIMABLE` baseline |
| + Volume | -0.059490 | -0.000982 | 0.002100 | -0.003083 | -0.000156 |
| + Market Regime | -0.051902 | -0.000876 | 0.002100 | -0.002976 | +0.000106 |
| + ETF | -0.051902 | -0.000876 | 0.002100 | -0.002976 | `NOT_ESTIMABLE` |
| + Theme | -0.042398 | -0.001212 | 0.002100 | -0.003313 | -0.000336 |
| + Capital | -0.042398 | -0.001212 | 0.002100 | -0.003313 | `NOT_ESTIMABLE` |
| + Dynamic Pool | -0.032604 | -0.001680 | 0.002100 | -0.003781 | -0.000468 |
| + Candidate | -0.032604 | -0.001680 | 0.002100 | -0.003781 | `NOT_ESTIMABLE` |
| + Signal | -0.032604 | -0.001680 | 0.002100 | -0.003781 | `NOT_ESTIMABLE` |
| + Forecast | -0.032604 | -0.001680 | 0.002100 | -0.003781 | `NOT_ESTIMABLE` |

The full-chain result is negative in every calendar month. Monthly net ranges
from -0.001838 in February to -0.006716 in March; monthly RankIC is negative
except May's economically negligible +0.001349. `RISK_ON` is positive but has
only two sessions/590 samples and cannot support a stable regime claim.
`RISK_OFF` gross is +0.000841 but net is -0.001259. `RISK_NEUTRAL` and
`DATA_INSUFFICIENT` are gross- and net-negative.

These results support deleting or demoting no canonical owner solely from this
one PIT-incomplete period. They do support deprioritizing ETF-dependent Capital,
Candidate, Signal and Forecast conclusions until a real intraday ETF source is
available; tuning their gates on this result would not repair the missing fact.

## Strategy Economics and ranking consistency

| Checkpoint | Gross | Cost | Net | MFE | MAE | Turnover | Capacity ceiling |
|---|---:|---:|---:|---:|---:|---:|---:|
| OPEN | +0.000068 | 0.002100 | -0.002033 | `NOT_ESTIMABLE` | `NOT_ESTIMABLE` | 1.9857 | CNY 97.95m |
| 09:45 | +0.000308 | 0.002100 | -0.001792 | +0.006823 | -0.006855 | 1.9799 | CNY 97.95m |
| 10:00 | +0.000530 | 0.002100 | -0.001570 | +0.008257 | -0.007890 | 1.9799 | CNY 97.95m |
| 10:30 | +0.000882 | 0.002100 | -0.001218 | +0.009648 | -0.008758 | 1.9799 | CNY 97.95m |
| 11:30 | +0.000869 | 0.002100 | -0.001232 | +0.011136 | -0.009735 | 1.9799 | CNY 97.95m |
| CLOSE | +0.001031 | 0.002100 | -0.001069 | +0.012939 | -0.011339 | 1.9799 | CNY 97.95m |

Every checkpoint is empirically gross-positive but net-negative after the
versioned cost policy. Commission, slippage, impact, fillability and capacity
remain `ENGINEERING_ASSUMPTION`; no broker/fill owner upgrades them to empirical
facts. Stamp-duty and commission rules are explicit in the frozen policy.

The full ranking path is worse: gross -0.001680, assumed cost 0.002100, net
-0.003781, turnover 0.5880 and maximum drawdown -0.39964. Ranking and the
executable checkpoint path use different portfolio/execution questions, but
both reject a current net-economic-value claim.

## Exploratory challenger

The fixed ridge challenger uses 100 earlier sessions/29,729 observations for
training and 26 later sessions/7,646 observations for validation. It excludes
the same 425 missing targets. Validation MSE is 0.000502153 versus the frozen
mean baseline's 0.000518944; validation hit rate is 0.57952 and RankIC is
0.015405. Its durable classification is `POSITIVE`, but the small improvement
is one retrospective temporal split and does not override the empty canonical
Forecast, negative economics or formal evidence gates.

## Durable evidence

| Evidence | Classification | Exact owner |
|---|---|---|
| Corpus Summary | `INCONCLUSIVE` | `historical-evidence-79b844fb5400f561f250cb7c` / `sha256:79b844fb5400f561f250cb7cdd1c1fe6180694eaced2ecf47c83c467a74348eb` |
| Alpha Ablation | `INCONCLUSIVE` | `historical-evidence-9256c62fe8ef87e9b6281c0b` / `sha256:9256c62fe8ef87e9b6281c0bb21408c4a4dfce502bed8b050ae9282e8f0549a3` |
| Strategy Economics | `NEGATIVE` | `historical-evidence-b6116b13062d0e854e37481f` / `sha256:b6116b13062d0e854e37481f21a6a7e36f454acb46e7067a55ba54bfa993f38a` |
| Portfolio Performance | `NEGATIVE` | `historical-evidence-bfda7dc66353b911083b58d1` / `sha256:bfda7dc66353b911083b58d1256c03bbbaf0b7391fc4cabdaff8e824186cd20c` |
| Exploratory Model | `POSITIVE` | `historical-evidence-6ed81f7aa1fc19bee5cd2347` / `sha256:6ed81f7aa1fc19bee5cd2347d2b5368803ba708bc37faa72ca102d5517ef074b` |

`NOT_ESTIMABLE` factor/Signal/Forecast metrics are persisted inside Corpus and
Ablation Evidence; they are not reclassified as zero or omitted.

## Phase E closure assessment

Phase E3 has terminal local replay and independent uninterrupted equality.
The longitudinal Runtime code and evidence are locally engineering-complete
once the repository quality gates below are terminal. Phase E itself remains
open as an empirical program because:

- the frozen ETF context has no real intraday observations, blocking the
  canonical Capital through Forecast path;
- corpus acquisition/publishing still peaks at about 5.03 GiB;
- current data is retrospective free history, not qualified Provider/PIT data;
- only one 6.5-month period and one index universe have been evaluated;
- costs, fills, impact and capacity remain assumptions;
- no Formal OOS, calibration, prospective or trading evidence exists.

The next work should resolve a real, traceable intraday ETF source and stream
corpus publication before extending to one to three years. It should not tune
Signal thresholds or Capital definitions to this result.

## Validation ledger

The terminal validation table will be completed only from current-HEAD output.
GitHub Actions remains `CI_NOT_RUN` until observed.

| Gate | Result |
|---|---|
| `uv sync --frozen --extra dev --extra postgres` | PASS |
| PostgreSQL migrations fresh/upgrade/idempotency/concurrency | PASS |
| Interruption/resume | PASS |
| Exact replay | PASS: 126 recomputed, zero mismatch |
| Independent uninterrupted equality | PASS: eight ordered sets identical |
| Corruption/adversarial tests | PASS |
| CLI | PASS: 13 focused tests |
| Platform | PASS: 33 tests |
| Full pytest | PASS: 2,941 tests |
| Ruff | PASS |
| mypy | PASS: 394 source files |
| build | PASS: sdist and wheel |
| docs links/tests | PASS |
| `git diff --check` | PASS |
| GitHub Actions | `CI_NOT_RUN` |

The first standalone migration/CLI invocation omitted the required
`MARKET_REGIME_ALPHA_TEST_DATABASE_URL` and failed during fixture setup before
executing product code. Both commands were rerun with the explicit PostgreSQL
URL; migration fresh/upgrade/idempotency/concurrency completed with 23 passing
tests and the CLI set completed with 13 passing tests. The terminal results
above are those correctly configured reruns; the initial setup failure is not
silently discarded.
