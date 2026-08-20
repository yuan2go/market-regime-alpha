# Phase E2 Historical Evidence Expansion Report

> **Status:** SUPERSEDED
> **Methodology Status:** `METHODOLOGY_INVALIDATED / SUPERSEDED`
> **Evidence Code Revision:** `92f63e99226fe1b697cf4307b737f53c5599f14b`
> **Evidence Date:** 2026-08-13
> **Authority Ceiling:** `EXPLORATORY / PIT_INCOMPLETE / FORMAL_OOS=false / CALIBRATED=false`
> **Superseded By:** Golden Loop V2 exact-rational tie-aware methodology and `docs/references/Golden-Loop-V2-Research-Correctness-Report.md`

> **Current-use restriction:** This report remains immutable provenance for corpus,
> Runtime and negative-result audit. Its V1 signed ranking, layer-lift and
> Portfolio interpretations are `METHODOLOGY_INVALIDATED` and must not re-enter
> a current Alpha conclusion.

## Result

Phase E2 expands the six-stock Pilot Corpus to one frozen historical CSI 300
cross-section with real index and ETF context. The same Canonical Decision-Time
kernels now materialize Price through Forecast observations over 19 Decision
Sessions without a second Storage Authority or a second Historical algorithm.

This is useful real-data research evidence, not proof of general Alpha. The
minute evidence window is one month, the constituent snapshot is one frozen
index cohort, Provider publication history is incomplete, and costs,
fillability, impact and capacity remain engineering assumptions.

## Frozen owners and corpus

| Item | Exact value |
|---|---|
| Historical constituent owner | `free-research-universe:899e219c9c6a61a9ff8308ab0c3c0acb2d16fa94578b2b1a22a60bac9c4b8e57` |
| Constituent effective date | 2026-06-15 |
| Equity members | 300 real CSI 300 constituents |
| Context instruments | `000300.SH` index and `510300.SH` ETF |
| Raw owner | `historical-data-owner-3aadafec0d72b0c5dcaffc24` / `sha256:3aadafec0d72b0c5dcaffc246e65d49fd1990b66f2dae163b601b0cb080fcf25` |
| Normalized owner | `historical-data-owner-19156c83f5d4f79b516ab65f` / `sha256:19156c83f5d4f79b516ab65fdb3a6d46ba76ad585ccfaf54ae91910c33c306cd` |
| Historical run | `historical-research-run-5e7880f7288e4346a7a507af` / `sha256:5e7880f7288e4346a7a507aff1d6ca5aaed7c023a1574c5abb720f207455172b` |
| Physical package hashes | Raw `sha256:36902b7770003c0d35945918c769186f4f0a08eca6b2b86ff4f4edbcebec9b62`; Normalized `sha256:26cef40d9b1e0f7eb215740504ec279fbfc36557482848e6bbe02fd6b9d0b5b5` |
| Provider requests | 906 exact symbol/timeframe intervals; 904 non-empty and two retained empty results |
| Daily | 110,845 rows, 2025-01-02 through 2026-07-14, 128 partitions |
| 5-minute | 302,928 rows, 2026-06-15 through 2026-07-14, 128 partitions |
| Total normalized | 413,773 rows, 256 partitions |
| Artifact bytes | 67,039,503 Parquet bytes: 9,849,412 Raw plus 57,190,091 Normalized |
| Decision / Outcome window | 19 Decision Sessions, 2026-06-16 through 2026-07-13; T+1 Outcomes through 2026-07-14 |
| Panel | 5,700 persisted rows; 5,690 estimable T+1 10:30 samples; ten missing targets remain explicit |

The corpus is raw-unadjusted BaoStock history. Retrieval time remains the true
2026 archive time and is never rewritten to event time. Two empty requests are
facts rather than acquisition failures: 2025 ETF Daily history and index
5-minute history were unavailable from the exact Provider requests.
Normalized missingness is retained: Amount and Volume are absent on 179 rows,
bar-level listing status on all 413,773 rows, and 5-minute ST status on all
302,928 minute rows. Decision eligibility resolves lifecycle and Daily ST/
trading facts from their actual owners; it does not convert these missing bar
fields into observations.

## Selective read and materialization

PostgreSQL remains the only business Authority. It resolves the exact owner,
immutable Artifact Root locator, manifest, physical package hash and a new
partition access index keyed by owner, timeframe, overlapping date range and
stable symbol bucket. The Artifact Root stores bytes only.

The read path:

1. reloads the exact owner/index and validates manifest identity;
2. selects only overlapping timeframe/date/symbol-bucket partitions in
   PostgreSQL;
3. verifies every selected Parquet checksum;
4. applies Arrow predicates and a seven-column projection in bounded record
   batches;
5. reconstructs selected typed records, rechecks exact record ID/hash and
   physical projections, and returns canonical order;
6. fails closed on row ceiling, corruption, duplicate identity or projection
   divergence.

The immutable v1 Parquet encoding keeps canonical `record_json`, so that column
must remain projected to preserve exact record identity. The implementation
still removes five redundant columns from the scan and traverses Arrow columns
and batches vectorially before typed-record construction. Decision-Time
materialization retains one bounded Daily projection plus an LRU of only the
previous/current/T+1 minute windows; it no longer loads the complete 413,773-row
package object graph.

Current-code measurements:

| Measurement | Result |
|---|---|
| Daily selective scan | 110,845/110,845 candidate rows; 128 partitions; 16,522,564 verified bytes; 128 Arrow batches; max batch 2,430; 8.09 s |
| Two-session minute scan | 28,896 returned from 158,832 candidate rows; 64 partitions; 21,303,830 verified bytes; 64 Arrow batches; max batch 960; 1.98 s |
| Combined benchmark process | 10.68 s; 578,469,888-byte peak RSS; zero swap |
| Interrupted + resumed execution | 19 sessions / 114 receipts; 1,030.95 s resume; 952,352,768-byte peak RSS; zero swap |
| Exact replay | 1,091.70 s; 1,183,744,000-byte peak RSS; zero swap |
| Research Evidence build | 65.17 s; 1,626,341,376-byte peak RSS; zero swap |

The test suite also compares selective output with full-owner filtering across
multiple dates, symbols, timeframes and partitions, and forces two-row Arrow
batches. Corruption, unbounded queries and deterministic ordering fail closed.

## Historical security and classification facts

The Universe is an `INDEX` selector with exact CSI 300 membership provenance;
it is not mislabeled as `FULL_A`. Membership comes from one real effective-dated
historical constituent response, never from the current Security Master. The
experiment freezes that cohort to prevent cross-session universe drift.

| Fact | Coverage and treatment |
|---|---|
| Listing date | 300/300 Provider lifecycle facts |
| Listing status | 300/300 owner-resolved at each Decision |
| Listing age | 300/300 derived only from owner listing date and Decision date |
| Delisting date | 0/300 observed in this live cohort; effective-date projection and post-delisting exclusion are tested |
| ST | 300/300 latest-available completed Daily observations at the 10:30 Decision cutoff; the current incomplete Daily bar is never used |
| Suspension/trading status | 300/300 current intraday-presence-derived non-suspension observations; absence remains unknown rather than being inferred as suspension |
| Industry | 0/300; `UNKNOWN`, because only current classification was available |
| Market cap | 0/300; `NOT_ESTIMABLE`, because no Decision-time published share owner exists |

Current classification is never projected backwards. Unknown membership,
listing or trading eligibility fails closed. This removes the Pilot's known
current-master retrospective projection path, but a single frozen historical
index cohort still does not represent an all-A-share PIT membership history.

## Context and Alpha-chain coverage

`000300.SH` is consumed by Market Regime and `510300.SH` by Theme. The ETF owner
reports 349 available Daily index observations and 106 available Daily ETF
observations. Capital covers 300 symbols
per session using the existing price/volume-based model inference; it is not a
claim about hidden institutional intent or a direct capital-flow observation.

Across the 19 sessions, ETF is `AVAILABLE` 19/19 times. Market Regime is
estimable on nine sessions (six `RISK_NEUTRAL`, three `RISK_OFF`) and truthfully
`DATA_INSUFFICIENT` on ten. Theme records eight `STARTING`, one
`STRENGTHENING` and ten `WEAKENING` observations. Candidate persists all 5,700
cross-sectional decisions: ten `SELECTED`, 244 `WATCHLIST`, and 5,446
`REJECTED`. Those selections produce ten Signal snapshots and ten Forecast
objects. Every Signal is `INACTIVE`; every Forecast remains
`DATA_INSUFFICIENT`, with only 2--18 usable same-symbol path samples against the
frozen minimum of 20. Candidate/Signal/Forecast are therefore observable rather
than structurally absent, while Forecast value and lift remain not estimable.

## Frozen cumulative ablation

No threshold or methodology was changed in response to the Pilot or this run.
The table reports the `ALL` slice from the durable `ALPHA_ABLATION` owner.
Incremental lift is the change in gross top-k return from the preceding frozen
variant; cost/net values still contain engineering assumptions.

| Variant | RankIC | Gross | Cost | Net | Incremental lift | Finding |
|---|---:|---:|---:|---:|---:|---|
| Price | 0.064539 | 0.007097 | 0.002100 | 0.004997 | `NOT_ESTIMABLE` baseline | exploratory baseline |
| + Volume | 0.040527 | 0.004409 | 0.002100 | 0.002309 | -0.002688 | `NEGATIVE` |
| + Market Regime | 0.032630 | 0.011415 | 0.002100 | 0.009315 | +0.007006 | exploratory `POSITIVE` |
| + ETF | 0.031339 | 0.011601 | 0.002100 | 0.009501 | +0.000187 | `INCONCLUSIVE` |
| + Theme | 0.031448 | 0.013058 | 0.002100 | 0.010958 | +0.001456 | exploratory `POSITIVE` |
| + Capital | 0.055713 | 0.014415 | 0.002100 | 0.012315 | +0.001358 | exploratory `POSITIVE` |
| + Dynamic Pool | 0.051734 | 0.015277 | 0.002100 | 0.013177 | +0.000862 | exploratory `POSITIVE` |
| + Candidate | 0.052781 | 0.014474 | 0.002100 | 0.012374 | -0.000802 | `NEGATIVE` |
| + Signal | 0.052802 | 0.014474 | 0.002100 | 0.012374 | 0.000000 | no incremental value |
| + Forecast | 0.052802 | 0.014474 | 0.002100 | 0.012374 | `NOT_ESTIMABLE` | insufficient path samples |

The registry classifies the cumulative result `INCONCLUSIVE`. Volume and
Candidate reduce the tested gross return; Signal adds exactly zero; Forecast
cannot be estimated. Those layers should not be described as validated Alpha.
Volume/Candidate deserve a separately frozen redefinition or downgrade;
inactive Signal should be deprioritized until it has meaningful active-state
coverage; Forecast needs a longer predeclared sample window, not a lower
threshold selected from this result. Market Regime, Theme, Capital and Dynamic
Pool lifts are exploratory positives only. ETF's +0.000187 is too small and
short-window-dependent to support retention on value grounds.

## Strategy economics

| Checkpoint | Gross | Cost | Net | Turnover | Capacity ceiling |
|---|---:|---:|---:|---:|---:|
| OPEN | -0.003446 | 0.002100 | -0.005546 | 1.9677 | CNY 308.1m |
| 09:45 | -0.003244 | 0.002100 | -0.005344 | 1.9504 | CNY 308.1m |
| 10:00 | -0.003262 | 0.002100 | -0.005362 | 1.9504 | CNY 308.1m |
| 10:30 | -0.003009 | 0.002100 | -0.005110 | 1.9504 | CNY 308.1m |
| 11:30 | -0.002997 | 0.002100 | -0.005097 | 1.9504 | CNY 308.1m |
| CLOSE | -0.002644 | 0.002100 | -0.004745 | 1.9504 | CNY 308.1m |

Gross return and path observations are empirical for this corpus. Commission,
stamp duty, spread/slippage, impact, participation, fillability and capacity
remain `ENGINEERING_ASSUMPTION`. Raw-unadjusted tradable prices are preserved;
the corpus lacks a complete corporate-action cash-flow owner, so total-return
economics and corporate-action-day attribution are not established.

Every checkpoint is empirically gross-negative before assumed cost. The
Strategy Economics owner is therefore `NEGATIVE`. The separate full-chain
cross-sectional Portfolio metric is gross +0.014474, assumed cost 0.002100,
net +0.012374, turnover 0.4389 and maximum drawdown -0.130944. That
`POSITIVE` exploratory owner does not override checkpoint economics: the two
owners answer different ranking-versus-executable-path questions, and their
disagreement is evidence against an economic-value claim.

## Recovery, replay and correctness audit

| Check | Result |
|---|---|
| Partial interruption | Public CLI stopped after seven committed stages, leaving a durable `RUNNING` run |
| Fresh-process resume | `COMPLETE`, 19/19 sessions and 114/114 receipts |
| Canonical replay | `matched=true`; `sha256:e802d73187077250927aa59a47829fb893fddc144216de7e94cd7051451298fd`; 1,091.70 s; zero swap |
| Independent uninterrupted run | `COMPLETE`, 19/19 sessions and 114/114 receipts; 1,264.43 s; 936,476,672-byte peak RSS; zero swap |
| Resumed vs uninterrupted equality | Eight ordered canonical sets match exactly; digests below |
| Decision-time cutoff | 209/209 Decision-side components satisfy `source_max_event_time <= decision_time`; zero violations |
| T+1 Outcome separation | 19/19 Outcome components end on the exact frozen next session; zero date violations |
| Missing target preservation | 5,700 Panel rows, ten explicit missing T+1 10:30 targets, 5,690 estimable samples |
| Cross-run lineage | 609 internal component-to-component bindings resolve to this run; zero resolve to another run |

The independent comparison ran in a PostgreSQL clone containing the same frozen
corpus/policy/target/experiment owners. Only Historical run results were removed
in that disposable database before running the exact same command without an
interruption ceiling. These digests cover the ordered exact identities/hashes,
statuses, source bindings and metric values; they are comparison digests, not
new business identities:

| Canonical set | Count | Resumed digest | Uninterrupted digest |
|---|---:|---|---|
| Run | 1 | `a07b4ab15917f5a11c64193f859fd50b` | `a07b4ab15917f5a11c64193f859fd50b` |
| Sessions | 19 | `bbc1cf2b558b465f08eba285f0210e2d` | `bbc1cf2b558b465f08eba285f0210e2d` |
| Stage receipts | 114 | `c060608459f81160e006e2457c1a97b9` | `c060608459f81160e006e2457c1a97b9` |
| Components | 247 | `e3591c58e17cb8d3f2ccefcde1d4435c` | `e3591c58e17cb8d3f2ccefcde1d4435c` |
| Component bindings | 780 | `956140967d7fc295c8e91dbca1184ae9` | `956140967d7fc295c8e91dbca1184ae9` |
| Evidence owners | 5 | `dab56378753d2a94a855dfce63ccfa7e` | `dab56378753d2a94a855dfce63ccfa7e` |
| Evidence metrics | 1,876 | `627c4ddf927877fb1a25067e00b0d463` | `627c4ddf927877fb1a25067e00b0d463` |
| Evidence bindings | 175 | `9a0a1c473f71827c82b8a89f6e770cdb` | `9a0a1c473f71827c82b8a89f6e770cdb` |

No known temporal, survivorship or lineage correctness mismatch remains in the
implemented boundary. Remaining empirical limitations are not silently closed:

- Provider retrieval/publication history is not Formal PIT;
- one effective-date index cohort is not longitudinal all-A membership;
- Industry and market cap are missing rather than backfilled;
- corporate-action cash flows, fillability, impact and capacity lack empirical
  owners;
- the 19-session minute window is too short for generalization, calibration or
  Formal OOS claims.

## Durable evidence owners and interpretation

- Corpus Summary — `INCONCLUSIVE`:
  `historical-evidence-618d6153009d6eff34d23975` /
  `sha256:618d6153009d6eff34d239755fe4457a35605a3ecdcff698d88c726ca526e147`.
- Alpha Ablation — `INCONCLUSIVE`:
  `historical-evidence-448eb838a91148f69075c5df` /
  `sha256:448eb838a91148f69075c5df6bd9a175d8a7c54281ca41fafde3ac96fbfcadfb`.
- Strategy Economics — `NEGATIVE`:
  `historical-evidence-ed5035c426426a114edd47ea` /
  `sha256:ed5035c426426a114edd47eae6e42e1906977d7e0e0521d9fc65303a9f7fa6c7`.
- Portfolio Performance — exploratory `POSITIVE`:
  `historical-evidence-8e189cac5a58706b87cacc9a` /
  `sha256:8e189cac5a58706b87cacc9aa506fedb91fef3cfc746c0dd2d1f55b9006da96d`.
- Exploratory Model — `NOT_ESTIMABLE` because 19 temporal sessions are below
  its frozen floor: `historical-evidence-251f717492b2d62ac8f2dcef` /
  `sha256:251f717492b2d62ac8f2dcefc7934e5025abe8bf71897491894dc45dda76d77a`.

Positive, negative, inconclusive and not-estimable outcomes are all immutable
registry facts. A positive exploratory ablation or Portfolio result cannot
promote a Model, change Risk, unlock Formal OOS, establish calibration or
authorize trading.

## Phase E status

Phase E2 is complete as a locally PostgreSQL-validated expanded Historical
Evidence vertical slice. It proves that the Canonical Runtime can operate on a
real 300-stock cross-section with real index/ETF context and bounded selective
materialization. It does not complete Historical Alpha Evidence Production.

The highest-value next work is a separately frozen longitudinal constituent
history with Decision-time share/industry/corporate-action facts, a materially
longer minute observation window, and owner-resolved empirical execution inputs.
Only after that boundary exists should a pre-registered Formal PIT / Locked OOS
program be considered; the existing qualification gates remain closed.

## Validation gates

| Gate | Result |
|---|---|
| `uv sync --frozen --extra dev --extra postgres` | PASS |
| Migration 070 fresh/upgrade/schema and affected PostgreSQL tests | PASS |
| Full PostgreSQL `python -m pytest -q` | PASS; only existing pandas fragmentation warnings |
| `python -m pytest -q tests/platform` with explicit PostgreSQL URL | PASS, 33 tests |
| Docs inventory/link checker and its tests | PASS |
| `python -m ruff check .` | PASS |
| `python -m mypy` | PASS, 394 source files |
| `python -m build` | PASS, sdist and wheel |
| Public CLI partial/resume/replay/evidence and independent uninterrupted execution | PASS |
| Dual standards/spec review after repairs | PASS; no remaining P1/P2 |
| `git diff --check` | PASS |

One explicit platform-test invocation initially omitted the required
`MARKET_REGIME_ALPHA_TEST_DATABASE_URL` and failed closed before constructing
PostgreSQL repositories. Re-running the same gate with the required explicit
URL passed all 33 tests; the full suite had already passed with that URL.
