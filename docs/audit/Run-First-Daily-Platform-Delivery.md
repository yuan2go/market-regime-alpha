# Run-First Exploratory Daily Platform Delivery

> **Status:** CURRENT_STATUS  
> **Authority:** Commit-bound delivery and runtime evidence report; verified immutable Artifacts, code and tests remain fact authority  
> **Owner:** Market Regime Alpha maintainers  
> **Last Updated:** 2026-07-28  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** Run-First-Daily-Platform-Baseline-Audit.md, ../architecture/decisions/ADR-001-Run-First-Phase-D-Daily-Platform-Boundaries.md, ../status/Current-State.md, ../status/Capability-Matrix.md, ../status/Gap-Register.md  
> **Code Evidence:** `feat/run-first-exploratory-daily-platform@dc9f27a68d3febd4a461e3e299af6ccbba3e70d0`; `src/market_regime_alpha`; `tests`

## 1. Delivery baseline

| Field | Observed value |
|---|---|
| base commit | `772ecfb09410588b5a406ad900d793a5850e60d5` |
| implementation branch | `feat/run-first-exploratory-daily-platform` |
| implementation evidence commit | `dc9f27a68d3febd4a461e3e299af6ccbba3e70d0` |
| baseline working tree | clean |
| delivery date | `2026-07-28`, Asia/Shanghai |

The branch contains separate, reversible commits for audit/ADR, Platform hardening,
PredictionRun, Runtime Journal, public Provider and quality gate, daily Universe/Feature
materialization, Recommendation/Entry projection, Phase D Artifact, Outcome/Review, CLI/replay
evidence and partial LIVE-source preservation. It has not been merged to `main`.

## 2. Implemented call chain

The executable Phase D path is:

```text
scripts/run_exploratory_daily_loop.py::main
  -> _run_command / _replay_command / _settle_command / _report_command
  -> application.daily_loop.runner.DailyLoopRunner
       -> run(command)
          -> DailyRunCommand.run_request_id
          -> SQLiteDailyRunRepository.create_or_get
          -> PublicCompositeLiveProfile.acquire
             or PublicCompositeReplayProfile.acquire
          -> publish_source_archive
          -> build_public_source_manifest
          -> evaluate_daily_data_quality
          -> DailyRunIdentity.from_source_freeze
          -> SQLiteDailyRunRepository.bind_daily_run_identity
          -> DATA_BLOCKED publication
             or reconcile_daily_universe
          -> materialize_daily_candidate_pipeline
          -> publish_b0_b1_prediction_runs
          -> project_candidate_recommendations
          -> build_decision_price_snapshot
          -> assess_entry_plumbing
          -> publish_phase_d_daily_decision_artifact
          -> load_verified_phase_d_daily_decision_artifact
       -> replay_daily_run(daily_run_id)
          -> verify Source Archive, PredictionRun and Phase D Artifact receipts
       -> settle_daily_run(daily_run_id)
          -> settle_mr1_1030_outcomes
          -> publish_daily_review_artifact
          -> load_verified_daily_review_artifact
       -> report_daily_run(daily_run_id)
          -> reconstruct report from a verified Artifact
```

The application layer orchestrates existing domain contracts. Provider code acquires, archives,
normalizes and declares semantics only; it does not rank Candidates, assess Entry or create
portfolio/order state.

## 3. Reused capabilities

| Capability | Reused code and identity |
|---|---|
| Calendar | explicit Provider trading sessions and existing Calendar/time contracts |
| Universe | `PITUniverseSnapshot`, `TradingEligibilitySnapshot`, existing membership and eligibility identities |
| Feature | existing R5 baseline definitions/materializers through `features.daily_pipeline` |
| Candidate Dataset | `CandidateResearchDataset` and complete Candidate population/rejection semantics |
| B0 | `rank_candidates_by_feature`, model `platform-b0-momentum-v1` |
| B1 | `rank_candidates_by_transparent_composite`, model `platform-b1-balanced-v1`, fixed `0.50/0.30/0.20` weights |
| Target | the sole `MR1TargetId.NEXT_SESSION_1030_RETURN` identity |
| Artifact | existing immutable/staged/checksum publication patterns, with a distinct Phase D schema |
| Reader | existing historical V1 Reader unchanged; a Versioned Reader Registry routes the new Phase D Reader separately |
| Tencent/BaoStock | direct Tencent quote and BaoStock history acquisition adapters, wrapped by the LIVE profile |

The B0/B1 adapter invokes the existing rankers and preserves the complete population,
predictions, rejections, scores, ranks, tie breaking, coverage, Target ID, Dataset ID and Feature
Materialization IDs. It neither tunes weights nor selects a winner after observing an outcome.

## 4. Added contracts and services

### Runtime and persistence

- `DailyRunCommand`, `RunMode`, `RunRequestId`, `DailyRunId` and `DailyRunIdentity`;
- `DailyRunStatus` and validated state transitions;
- `DailyRunRepository` Protocol, `DailyRunRecord` and immutable `StageReceipt`;
- `SQLiteDailyRunRepository` as Runtime Journal;
- request/run identity mapping without changing the SQLite primary key;
- idempotent completed-stage verification and restart recovery.

### Platform and Candidate evidence

- registration restricted to `DRAFT + UNQUALIFIED`;
- separate validated `restore_registration` boundary for historical import;
- `DataEligibility` separated from model `EvidenceLevel`;
- immutable, content-addressed `PredictionRun`;
- PredictionRun publisher and semantic Reader;
- B0/B1 PredictionRun adapter and full equivalence characterization;
- Platform and new daily modules included in mypy.

### Provider, Source and quality

- `public-composite-live-v1`: BaoStock history plus Tencent current quote/minute evidence, with
  no local fallback;
- `public-composite-replay-v1`: immutable caller-specified Source Archive only, with no network;
- raw payloads, hashes, retrieval/event/availability times, locator, unit, adjustment basis,
  finality, limitations and source conflicts;
- field-level `SourceManifest`;
- fail-closed `DataQualityReport`;
- partial successful LIVE acquisition evidence retained when a later source fails.

### Daily domain projections

- content-addressed 20-symbol A-share smoke policy and reason-complete reconciliation;
- configurable `DailyUniversePolicy` contract for later operational pools;
- daily Feature and outcome-pending Candidate Dataset materialization;
- per-model Top-5 `CandidateRecommendation`;
- Decision Price Snapshot;
- `entry-plumbing-gate-v0`, which emits only `WAIT_CONFIRMATION` or `REJECT`;
- exact 12-file `phase-d-daily-decision-artifact-v1`;
- staged, atomic, non-overwriting publisher, semantic Reader, tamper verification and report
  reconstruction;
- Versioned Reader Registry that preserves the historical V1 six-file contract unchanged;
- MR1 10:30 `TargetProtocol` adapter;
- append-only `RecommendationOutcome`, `DailyReviewReport` and exact seven-file review Artifact.

Parquet/DuckDB is deliberately deferred as an optional derived query projection. Immutable files
remain Evidence Authority and SQLite remains only the Runtime Journal.

## 5. Runtime evidence

Runtime evidence was generated from implementation commit `dc9f27a68d3febd4a461e3e299af6ccbba3e70d0`.
The `/tmp` locators below are ephemeral execution locators, not repository authorities; the
recorded IDs and hashes are the evidence identities.

### 5.1 One-session smoke Replay

| Field | Value |
|---|---|
| decision date | `2025-02-03` |
| pool | fixed 20-symbol A-share smoke pool |
| RunRequestId | `run-request-5e7e6ce37d5669edc6be432b` |
| DailyRunId | `daily-run-b9964f467cafce84a0ebb688` |
| Source Archive | `source-replay-900bef224d6b5442383e5441` |
| Decision Artifact | `daily-decision-c534515718be2c1c66d1d1f8` |
| Decision replay hash | `sha256:d0975349d2f2010173a79db54a63d2c34b6ffdf24f32d2fb347545f13cb91294` |
| Review Artifact | `daily-review-artifact-da4dfb1b136cedf856992bb5` |
| Review hash | `sha256:0f803a3352b2bf78610b1d961c0711fc42c3c761253d032e3114187b54cdb3e5` |
| outcome coverage | `1.0` |
| final status | `REVIEW_PUBLISHED` |

The original command and an identical repeat returned the same RunRequestId, DailyRunId,
Decision Artifact ID and hash. Settlement appended the review without modifying T-day evidence.

### 5.2 Ten-session Replay

Ten consecutive trading sessions produced exactly 10 Source Archives, 20 PredictionRuns, 10
Decision Artifacts and 10 Review Artifacts. Every review reached `REVIEW_PUBLISHED` with outcome
coverage `1.0`; replay after settlement reconstructed every original Decision hash.

| Decision date | DailyRunId | Decision Artifact | Decision replay hash | Review Artifact |
|---|---|---|---|---|
| `2025-02-03` | `daily-run-b063d5a7b2ffdaaac3d67455` | `daily-decision-25294980018e42dddf85ad9a` | `sha256:78c50c8af5a6dbec5fd5e35fa13954d9e6f69bbebc2c4ab14edc13340f204cfb` | `daily-review-artifact-716a7676923db14510b03e3a` |
| `2025-02-04` | `daily-run-e086cb156f53a6b006a39d72` | `daily-decision-83f2ccb7d216568d133ea904` | `sha256:8b1aa771db197a3bf50088a6e4ecca4f89c95c32c18eda8b0123b74ce7c5f6e9` | `daily-review-artifact-e2ba3086b42eb50f217b1b39` |
| `2025-02-05` | `daily-run-ab1e63fabd32f80ea2680e29` | `daily-decision-b930fb4e361be5365eaaa346` | `sha256:4752a378d11c8e7f45a8ebe9332aeca40211ab5edd67ad41bfd0b168f859c3fd` | `daily-review-artifact-1c6a2b2f1eb02f5aee8cdb63` |
| `2025-02-06` | `daily-run-3f48d5ad7fbc953121d13e3a` | `daily-decision-0b986b6e82af5f62c1335cc5` | `sha256:006f8579c4ea1d24e6121ba34b8329dfe223659ae4b063afd27a6fbdfed91c15` | `daily-review-artifact-143fae202a1f395eb20676f7` |
| `2025-02-07` | `daily-run-b92a2a39c6beb81244aff08e` | `daily-decision-64dd2055a631ab2536571cda` | `sha256:585afe29303ad59a75e5078cc0d1f2c322223ccf33d55439000d9a44bdd17a56` | `daily-review-artifact-869ed7ecc4c48a74b51a3b27` |
| `2025-02-10` | `daily-run-995cde1af1aea22d1f12492a` | `daily-decision-263ef7624078351aae02ee48` | `sha256:749bda8858d4e46eedec1dd7ecca4dfb159b48b62282faa0c89ecee44a5efc1d` | `daily-review-artifact-0c2a35082d2c2f466451b25f` |
| `2025-02-11` | `daily-run-4df3db977af0fe7549d4b4ed` | `daily-decision-755f48d36efd19193927f648` | `sha256:df9cad85bebe7a843fd2ad9dccef47c379b5f9a5eab7ce65f49c8f31f2822ca6` | `daily-review-artifact-efd9d11b5de99068f8339733` |
| `2025-02-12` | `daily-run-75adfaafd3d69756991600fc` | `daily-decision-aa44a5f83b8e07f745b874f0` | `sha256:9501cbb92eb1747493f5d6d5f50e051a613feca5d914696b12090fa99a25afba` | `daily-review-artifact-8a174159c5f255798cf99de6` |
| `2025-02-13` | `daily-run-21ec108fc730d10b08f2b461` | `daily-decision-5a4473a86c0a74af18683858` | `sha256:6a8271c216fe17e3e35630f80f245f3ee73a041bab44c2a1a7aa981d73b068a0` | `daily-review-artifact-eec4b4feab8acf243d5a2b8e` |
| `2025-02-14` | `daily-run-f779f921364f5b29d317054e` | `daily-decision-025c8d9c9c60a7af64b60e88` | `sha256:c7f40ee6139e2cbd2c08be34bf24ee87439a60b7c1ea4b3833c127ccd50ddb71` | `daily-review-artifact-9ea209bb6fd3b53e50ab0a70` |

### 5.3 LIVE dry run

The LIVE command used real external Provider calls, not a fixture:

- 20 BaoStock raw payloads;
- one Tencent raw payload;
- 58,540 normalized historical bars;
- 20 current quotes;
- profile `public-composite-live-v1`;
- no local Archive fallback.

It correctly terminated as `DATA_BLOCKED`: historical `AvailableTime` was not supplied by the
public source, current quote/event times were after the requested 14:55 Decision Time, Tencent
did not prove trading status, and formal PIT Universe Membership/Eligibility was unavailable.
This is a verified normal terminal state, not `FAILED`.

| Field | Value |
|---|---|
| RunRequestId | `run-request-cdc3523b75e289bd4648522b` |
| DailyRunId | `daily-run-d61494dc0461373158096caa` |
| Source Archive | `source-replay-0c1404914b674201064a804b` |
| blocked Decision Artifact | `daily-decision-62e9476ff09edd9cec961f0d` |
| replay hash | `sha256:95d355c6786751557c782f3c2c32559475e43e11ae59c60b56f90c1f16239db2` |
| terminal status | `DATA_BLOCKED` |

The blocked Artifact contains SourceManifest, DataQualityReport, reason codes and checksums. Its
PredictionRun, CandidateRecommendation and EntryAssessment collections are empty, and replay
returned the same hash.

## 6. Validation evidence

Observed on the implementation evidence commit:

```text
python scripts/check_docs_links.py                                      PASS
python -m pytest -q tests/platform                                     PASS
python -m pytest -q tests/application                                  PASS
python -m pytest -q tests/data                                         PASS
python -m pytest -q tests/universe                                     PASS
python -m pytest -q tests/candidates                                   PASS
python -m pytest -q                                                    PASS
python -m ruff check .                                                 PASS
python -m mypy                                                        PASS (180 source files)
python -m pip check                                                    PASS (No broken requirements found)
git diff --check                                                       PASS
```

The full suite observed `1059 passed, 8 subtests passed, 6 warnings`. The six warnings are
pre-existing pandas DataFrame fragmentation warnings from
`backtesting/run_top1000_screened_portfolio_backtest.py`; no test failed.

Focused tests cover identity determinism, transitions, duplicates, recovery, Provider separation,
no silent fallback, SourceManifest, quality blocking, Universe reconciliation, Feature failure,
B0/B1 equivalence, PredictionRun identity, Recommendation, Entry gate, Artifact tamper/Reader,
Outcome append, review reconstruction, single-day Replay, ten-session Replay and LIVE blocking.

## 7. Authority ceiling

The delivered capability is exactly:

```text
EXPLORATORY_DAILY_LOOP_OPERATIONAL
FORMAL_OOS_ALPHA_NOT_ESTABLISHED
TRADING_AUTHORITY_NOT_GRANTED
```

It does not establish model superiority, formal PIT/OOS Alpha, automated promotion, position
authority or execution authority. No code in the new Runner calls a broker, sends an order or
mutates an account/position.

## 8. Remaining gaps

The ordered remaining gaps are:

1. Real Entry Model;
2. ManualTradeRecord;
3. Position Authority;
4. Holding;
5. Exit;
6. Portfolio;
7. Xuntou Shadow;
8. Formal PIT;
9. QuantDesk.

The configurable 100–300-symbol operational public-data pool also still needs an approved
membership source and runtime configuration before it can replace the fixed smoke pool. This does
not change the authority order above.

## 9. Next work package

The next work package is:

```text
Xuntou Provider Shadow Integration
```

It must enter through the existing Provider result boundary and run as a shadow comparison. It
must not import `xtquant` in the application Runner, invoke Candidate/Entry from the Adapter,
promote a model or grant trading authority.
