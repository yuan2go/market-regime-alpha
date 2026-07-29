# Run-First Daily Platform Baseline Audit

> **Status:** CURRENT_STATUS  
> **Authority:** Commit-bound implementation audit for the Run-First exploratory daily platform; code, tests and reproducible Artifacts remain implementation fact authority  
> **Owner:** Market Regime Alpha maintainers  
> **Last Updated:** 2026-07-28  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** ../architecture/decisions/ADR-001-Run-First-Phase-D-Daily-Platform-Boundaries.md, ../superpowers/plans/2026-07-28-run-first-exploratory-daily-platform.md, ../roadmap/work-packages/WP-D0-Platform-Governance-Kernel.md, ../roadmap/work-packages/WP-D2E-Tencent-Exploratory-Daily-Loop.md  
> **Code Evidence:** main@772ecfb09410588b5a406ad900d793a5850e60d5; `src/market_regime_alpha`; `tests`

## 1. Audited baseline and method

| Field | Observed value |
|---|---|
| repository | `yuan2go/market-regime-alpha` |
| synchronized branch | `main` |
| audited HEAD | `772ecfb09410588b5a406ad900d793a5850e60d5` |
| implementation branch | `feat/run-first-exploratory-daily-platform` |
| baseline working tree | clean |
| audit date | `2026-07-28`, Asia/Shanghai |

The required synchronization sequence was executed in order:

```text
git status --short       PASS (empty)
git fetch --all --prune  PASS
git switch main          PASS
git pull --ff-only       PASS (Already up to date)
git rev-parse HEAD       PASS (772ecfb09410588b5a406ad900d793a5850e60d5)
```

The actual HEAD equals the user-specified baseline, so no incremental-commit audit was required.
The documents, source trees and tests named in the implementation request were read before this
audit was written. The current code and tests were treated as fact authority; roadmap and
specification documents were used only to identify desired contracts and boundaries.

Observed baseline validation:

```text
python -m pytest -q tests/platform tests/daily_research tests/candidates
PASS (88 tests)

python -m mypy
PASS (138 source files)
```

The mypy result does not cover `src/market_regime_alpha/platform/**`; that omission is documented
in section 8.

Two ignored runtime Artifacts were inspected as reproducible workspace evidence:

| Artifact | Manifest SHA-256 | Relevant observation |
|---|---|---|
| `mr1-c06821bf7db2dc787244` | `101b616f876a7325c17ebaade82ee13d2d48e35257705b01b675288dd54e3f7e` | `EXPLORATORY`; includes `NEXT_SESSION_1030_RETURN` in `target_schema_ids` |
| `pit-replication-v2-21c5fb99c1dac32565e0` | `104538bd3f4080734a876f7fbae39ab820d07cb8c0bbaca6b441b152f5994b94` | verifiable `BLOCKED_EXTERNAL_PROVIDER_INPUT` with `NO_RESEARCH_RESULT` |

These runtime directories are intentionally ignored by `.gitignore`; the audit records their
observed identities and hashes rather than treating their locators as permanent repository paths.

## 2. Current Tencent script: real call chain

The current executable path is
`scripts/run_tencent_composite_exploratory.py::main`, not an application service.
Its observed call chain is:

```text
main()
  -> dividend_t.storage.load_watchlist(...)[0:20]
  -> _retrieved_at()
  -> current_git_revision()
  -> _config_hash()
  -> _run_id(retrieved_at, config_hash, watchlist_hash)
  -> build_default_acquirer()
       -> TencentMinuteProvider
       -> BaoStockADataProvider
       -> read_local_5min_cache
       -> fetch_tencent_latest_quotes
  -> TencentCompositeAcquirer.acquire()
  -> merge_acquisition()
  -> build_tencent_composite_dataset_contract()
  -> prepare_composite_data()
  -> run_tencent_composite_candidate_experiment()
       -> materialize_tencent_composite_slice() for 60 historical Decision Dates
       -> run_r5_target_baselines()
       -> four B0 controls and fixed B1-A..B1-E ablations
  -> refresh_dividend_t_from_composite()
  -> write_dividend_trend_snapshot()
  -> write_tencent_composite_run()
```

Code evidence:

- the Legacy watchlist import and load are at
  `scripts/run_tencent_composite_exploratory.py:32` and `:89`;
- acquisition, merge, quality preparation and Candidate experiment calls are at
  `scripts/run_tencent_composite_exploratory.py:105-150`;
- Legacy Dividend-T refresh and snapshot write are at
  `scripts/run_tencent_composite_exploratory.py:158-165`;
- the final research Artifact write is at
  `scripts/run_tencent_composite_exploratory.py:172`;
- the acquirer invokes local, BaoStock, Tencent and quote paths for one acquisition at
  `src/market_regime_alpha/research/tencent_composite_acquisition.py:51-149`;
- merge precedence is BaoStock < local < Tencent at
  `src/market_regime_alpha/research/tencent_composite_merge.py:21-23`, with the declared
  “Tencent-current, local-history, BaoStock-gap” rule at `:86`.

The script preserves source attempts, partitions and conflicts. That is useful provenance, but it
is a research-run manifest rather than a field-level SourceManifest with explicit event,
availability, finality and Decision-Time semantics.

## 3. Why the Tencent script is not a daily platform Runner

### 3.1 It is a multi-date experiment

`TencentCompositeCandidateRun` requires exactly 60 Decision Dates and three Target families
(`src/market_regime_alpha/research/tencent_composite_runner.py:33-49`). The runner materializes
all 60 historical slices and then runs the full B0/B1 ladder
(`src/market_regime_alpha/research/tencent_composite_runner.py:112-150`). A daily platform run
needs one Decision Date, an outcome-pending state, and later settlement.

### 3.2 Its identity is retrieval-time dependent

`_run_id()` includes a formatted `RetrievedAt`
(`scripts/run_tencent_composite_exploratory.py:324`). The same result-affecting command executed
again at another retrieval time receives another run identity and can reacquire all sources.
There is no pre-acquisition request identity, frozen-source run identity or journal mapping.

### 3.3 It has no durable state machine

The script checks for an existing output directory, runs sequentially in one process and publishes
only at the end. It has no SQLite Runtime Journal, stage receipts, compare-and-set transition,
lease, recovery cursor or separation between a resumable failure and a terminal data block.

### 3.4 LIVE and local Replay are not separated

`TencentCompositeAcquirer` requires a `local_reader` and invokes it for each symbol before the
BaoStock and Tencent paths (`src/market_regime_alpha/research/tencent_composite_acquisition.py:39-48`
and `:69-135`). This is explicit in the current research manifest but cannot satisfy a LIVE
profile that forbids local Archive fallback.

### 3.5 Its quality gate is research-window oriented

The gate defaults to 60 decisions, 21 warm-up sessions and 16 accepted symbols
(`src/market_regime_alpha/research/tencent_composite_quality.py:39-59`). It checks composite bar
coverage but does not prove all critical daily facts: field availability, trading status, PIT
membership and eligibility. It therefore cannot be reused as the sole daily fail-closed gate.

### 3.6 It bypasses canonical PIT Universe/Eligibility

`materialize_tencent_composite_slice()` constructs `CandidatePopulation` directly from accepted
symbols and a locally derived Universe ID
(`src/market_regime_alpha/research/tencent_composite_materialization.py:78-79` and `:290`).
The code truthfully records
`ACCEPTED_CURRENT_WATCHLIST_IS_NOT_PIT_TRADING_ELIGIBILITY` at `:109-110`, but it does not
materialize every smoke-pool symbol as eligible or excluded with reason.

### 3.7 It observes Targets in the same historical run

Target `observed_at` and `materialized_at` are both assigned the current retrieval time
(`src/market_regime_alpha/research/tencent_composite_materialization.py:193-202`). The explicit
limitation `HISTORICAL_TARGET_OBSERVED_AT_IS_RUN_RETRIEVAL_TIME` is correct for that retrospective
experiment, but a daily run must publish predictions before the future outcome exists and append
an immutable settlement later.

### 3.8 It mutates a Legacy output

The script refreshes and writes the Dividend-T trend snapshot. A Phase D daily application must
not import `dividend_t.storage`, write that snapshot, call a broker or mutate positions.

## 4. Reusable implementation

| Capability | Reusable authority | Required adaptation |
|---|---|---|
| Identity/time | `core.identity`, `core.time` | add new content-addressed run records without changing existing IDs |
| Calendar | `data.trading_calendar.TradingCalendarArtifact` | Provider profile must supply explicit sessions |
| Universe | `universe.artifacts`, `universe.eligibility_artifacts` | materialize smoke-policy membership and reason-complete eligibility |
| Candidate population | `candidates.contracts.CandidatePopulation` | build from canonical Universe/Eligibility outputs |
| Feature definitions/materializers | `features.rehearsal_baselines` | adapter input must carry explicit availability and source identity |
| Candidate dataset | `candidates.dataset.CandidateResearchDataset` | construct outcome-pending daily rows without reading future targets |
| B0 | `rank_candidates_by_feature` and `platform-b0-momentum-v1` | publish full-run equivalence evidence |
| B1 | `rank_candidates_by_transparent_composite` and `platform-b1-balanced-v1` | preserve 0.50/0.30/0.20 weights and tie breaking |
| Multi-model slice | `platform.multi_model_slice` | select only the existing B0/B1 specs; do not execute B2 |
| Tencent/BaoStock | direct adapters in `data_sources.a_share_bars` and normalization in Tencent composite modules | wrap in distinct LIVE Provider Profile; archive exact raw payload |
| Source conflicts | `tencent_composite_merge.CompositeSourceConflict` | project into canonical field-level conflict/reason evidence |
| Historical V1 Artifact patterns | staging, checksum and semantic verification patterns in `daily_research` | copy no contract identity; implement a new Phase D schema and reader route |
| 10:30 Target semantics | `MR1TargetId.NEXT_SESSION_1030_RETURN`, `build_mr1_targets` | one explicit Adapter to TargetProtocol, Outcome and Review |
| Blocked Artifact precedent | PIT replication blocked Artifact | use `DATA_BLOCKED` as verified normal terminal state |

The existing platform model IDs and weights are defined at
`src/market_regime_alpha/platform/multi_model_slice.py:122-144`. The adapter must invoke the same
ranking functions with the same specs; it must not reimplement scoring.

## 5. Legacy dependencies that must remain isolated

The new Runner must not import or write:

- `market_regime_alpha.dividend_t.storage`;
- `market_regime_alpha.dividend_t.trend_snapshot`;
- `market_regime_alpha.research.tencent_composite_dividend_t`;
- any broker, order, position or account module;
- `LocalCacheTencentProvider` or generic silent-fallback provider logic in LIVE mode;
- XtQuant/Xuntou runtime modules.

The existing script remains a compatibility entry point with its current characterization. It is
not silently redirected to the new daily Runner during this delivery.

## 6. Historical `daily_research` V1 versus current Phase D

Historical V1 is implemented and tested, but it is not the current canonical Phase D runtime.

| Concern | Historical V1 fact | Required Phase D fact |
|---|---|---|
| package | `market_regime_alpha.daily_research` | independent `market_regime_alpha.daily_decision` package |
| file set | six files defined by `DAILY_QUANT_DECISION_FILES` | new exact Phase D file set including Source, Quality, Universe, Feature and Prediction evidence |
| model binding | one snapshot model identity | complete immutable B0/B1 `PredictionRun` records |
| recommendation lineage | snapshot/model/target | Decision Snapshot + PredictionRun + model |
| entry semantics | V1 supports `ENTER` (`daily_research/entry.py:132`) | V0 plumbing gate forbids `ENTER` |
| outcome/review | absent | immutable successor Outcome/Review Artifact |
| reader | V1-specific semantic Reader | Versioned Reader Registry routes V1 and Phase D separately |

The V1 exact file set and non-overwrite/staged rename behavior are enforced at
`src/market_regime_alpha/daily_research/artifacts.py:28`, `:92`, and `:123-125`.
The Reader verifies the same exact set at
`src/market_regime_alpha/daily_research/reader.py:43-53` and `:131-136`.
Tests lock checksums, identity, semantic tamper detection and exact file routing in
`tests/daily_research/test_artifacts.py` and `tests/daily_research/test_reader.py`.

Therefore the following paths are frozen for this work:

```text
src/market_regime_alpha/daily_research/**
tests/daily_research/**
```

They receive zero modifications.

## 7. Platform Registry and Governance bypasses

### 7.1 Direct advanced registration

`ModelRegistry.register()` publicly accepts caller-selected `lifecycle_status` and
`evidence_level` (`src/market_regime_alpha/platform/model_registry.py:82-87`). A caller can create
an `ACTIVE` or evidence-bearing registration without traversing `_ALLOWED_TRANSITIONS`. New
registration must be fixed to `DRAFT + UNQUALIFIED`.

### 7.2 No distinct restore/import boundary

The registry has `register`, `get`, `transition` and query methods, but no validated historical
restore API. Tightening `register` without adding restore would make durable recovery depend on
replaying untrusted caller state or private mutation.

### 7.3 Data authority and model maturity are conflated

`ModelDefinition.supported_data_grades` is typed as `tuple[EvidenceLevel, ...]`
(`src/market_regime_alpha/platform/contracts.py:210`) and transition compatibility compares a
model's EvidenceLevel to that tuple
(`src/market_regime_alpha/platform/model_registry.py:128`). DataEligibility describes input
authority; EvidenceLevel describes research maturity. The fields must be separated without
changing model scoring.

### 7.4 Execution bypasses protocol registries

`run_multi_model_candidate_slice()` accepts raw model specs, a dataset and code revision and calls
ranking functions directly (`src/market_regime_alpha/platform/multi_model_slice.py:172` onward).
It does not bind model definition hash, Target Protocol, Evaluation Protocol, Experiment Protocol,
feature materialization identities or immutable publication identity.

### 7.5 Experiment budgets are process-local

Current governance tests prove an in-memory access counter, not restart or concurrency authority.
The daily work must place acquisition/runtime idempotency in a Repository Protocol and SQLite
journal. Automatic model promotion remains out of scope.

## 8. Current mypy coverage gap

`pyproject.toml:53` configures an explicit file list. Historical `daily_research` V1 is included at
`pyproject.toml:84-93`, but no `src/market_regime_alpha/platform/**` path is present.

Consequences:

- the observed `Success: no issues found in 138 source files` does not type-check Platform;
- new governance and PredictionRun contracts could regress without affecting mypy;
- the Platform work package must add each Platform module to the explicit list, including new
  Publisher/Reader modules.

The repository currently uses `ignore_missing_imports=true`, `follow_imports=silent` and does not
disallow all untyped definitions. This work adds scope, not stricter project-wide flags.

## 9. Minimum runnable boundary

The smallest accepted vertical boundary is:

```text
RunRequest
-> Provider Profile Router
-> immutable raw Source Archive
-> SourceManifest
-> fail-closed DataQualityReport
-> A-share smoke Universe + reason-complete Eligibility
-> existing baseline Feature Materializations
-> existing B0/B1 rankings
-> immutable PredictionRuns
-> separate top-5 Recommendations per model
-> entry-plumbing-gate-v0 WAIT/REJECT only
-> immutable Phase D Decision Artifact or verified DATA_BLOCKED Artifact
-> replay verification
-> immutable MR1 10:30 Outcome/Review successor Artifact
```

Identity boundary:

- `RunRequestId` is computed before acquisition and is the SQLite journal primary key;
- `DailyRunId` is computed after Source Freeze from the RunRequest semantics, code revision,
  configuration identity, canonical SourceManifest and every Source content hash;
- the journal stores `daily_run_id` as a mapped immutable field; its primary key is never replaced.

Authority boundary:

- immutable Artifact bytes are Evidence Authority;
- SQLite is Runtime Journal only;
- Parquet/DuckDB is an optional derived query projection and may be deferred;
- every successful or blocked run remains `DataEligibility.EXPLORATORY`;
- no result establishes formal OOS Alpha or trading authority.

Provider boundary:

- `public-composite-live-v1` uses BaoStock history plus Tencent same-day data and never reads local
  Archive;
- `public-composite-replay-v1` reads one identified SourceManifest plus immutable Archive and never
  performs network acquisition.

## 10. Capabilities explicitly not implemented

This delivery does not implement:

- a validated Entry model or any `ENTER` state;
- ManualTradeRecord or actual-position authority;
- Holding, Exit or Portfolio decisions;
- broker integration, orders or unattended trading;
- ETF, Theme or Capital Flow models;
- new Feature, Candidate model, Target, Universe or Dataset ontology;
- B2 execution, parameter search, weight changes or model-winner selection;
- automatic lifecycle promotion;
- formal PIT qualification or formal OOS Alpha;
- Xuntou/XtQuant ingestion or inferred Xuntou field semantics;
- QuantDesk, PostgreSQL service deployment or full-market production Universe.

## 11. Approved Target decision

`MR1TargetId.NEXT_SESSION_1030_RETURN` is the project's only identity for “next trading session
10:30 return”.

Evidence:

- enum identity at `src/market_regime_alpha/research/mr1_morning_pop.py:32`;
- exact endpoint mapping at `src/market_regime_alpha/research/mr1_morning_pop.py:58-64`;
- exact 5-minute endpoint convention at `src/market_regime_alpha/research/mr1_morning_pop.py:24`;
- materializer at `src/market_regime_alpha/research/mr1_morning_pop.py:85`;
- observed EXPLORATORY Artifact `mr1-c06821bf7db2dc787244`, whose manifest includes the exact
  Target identity.

Phase D may add an Adapter to `TargetProtocol`, Outcome Settlement and DailyReview. It may not
copy, rename or create a similar Target.

## 12. File-level implementation plan

The approved implementation is split into independently revertible commits.

### A. Baseline audit and ADR

- `docs/audit/Run-First-Daily-Platform-Baseline-Audit.md`
- `docs/architecture/decisions/ADR-001-Run-First-Phase-D-Daily-Platform-Boundaries.md`
- `docs/superpowers/plans/2026-07-28-run-first-exploratory-daily-platform.md`
- documentation index links only

### B. Platform minimum governance fix

- change `platform/contracts.py` to use `supported_data_eligibilities`;
- change `platform/model_registry.py` so `register()` always creates
  `DRAFT + UNQUALIFIED`;
- add a separately named, validating restore/import API;
- add Platform modules to `pyproject.toml` mypy scope;
- expand `tests/platform/test_platform_kernel.py`;
- do not change scoring code or weights.

### C. PredictionRun and B0/B1 adapter

- add Platform PredictionRun contracts, Publisher and semantic Reader;
- add adapter around the existing B0/B1 specs and ranking functions;
- add full population/prediction/rejection/score/rank/tie/coverage/identity equivalence tests.

### D. Runtime Journal and state machine

- add `application/daily_loop` command/state/repository modules;
- implement `RunRequestId`, post-freeze `DailyRunId`, transitions and SQLite repository;
- test duplicate requests, restart recovery and immutable ID mapping.

### E. Public Provider, SourceManifest and Quality Gate

- add separate public LIVE and REPLAY profiles under `data/providers/public_composite`;
- add canonical SourceManifest and DataQualityReport contracts;
- archive raw bytes content-addressably;
- test no network in replay and no local fallback in live.

### F. Smoke Universe and Feature pipeline

- add a versioned smoke Universe policy adapter;
- reuse canonical Universe/Eligibility and baseline Feature contracts;
- preserve every symbol as eligible or explicitly excluded.

### G. Recommendation and Entry plumbing

- add Phase D recommendation projection in the Candidate context;
- add `entry-plumbing-gate-v0` in the Entry context;
- permit only `WAIT_CONFIRMATION` or `REJECT`, with complete lineage.

### H. Phase D Artifact, Reader and Replay

- add independent `daily_decision` contracts/artifacts/readers;
- add Versioned Reader Registry without modifying V1;
- publish exact non-overwriting Decision or DATA_BLOCKED packages;
- test checksum, semantic tamper, report reconstruction and replay hashes.

### I. MR1 10:30 Outcome and DailyReview

- add an Adapter around the existing MR1 exact endpoint identity and materializer;
- publish immutable Outcome/Review successor evidence;
- leave T-day Prediction, Recommendation and Entry bytes unchanged.

### J. Operational evidence

- add CLI and deterministic replay fixtures;
- execute one-session and ten-session replay;
- execute public LIVE dry run or publish a verified blocked Artifact;
- update status documents only after observed acceptance evidence exists.

## 13. Stop conditions

Implementation stops for explicit direction only if it would:

- break a historical Artifact identity;
- change the frozen MR1 Target semantics;
- change B0/B1 score, rank, rejection, tie break or coverage;
- introduce a competing domain ontology;
- contradict a material implementation fact recorded in this audit.

Path adjustments, focused refactoring, additional tests and internal implementation details are
not stop conditions.
