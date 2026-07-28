# Current Capability Matrix

> **Status:** CURRENT_STATUS  
> **Authority:** Canonical implementation-status matrix  
> **Owner:** Market Regime Alpha maintainers  
> **Last Updated:** 2026-07-28
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** Current-State.md, Gap-Register.md, ../audit/Run-First-Daily-Platform-Delivery.md
> **Code Evidence:** feat/run-first-exploratory-daily-platform@dc9f27a68d3febd4a461e3e299af6ccbba3e70d0

| capability | status | code_evidence | test_evidence | runtime_evidence | document_evidence | missing_evidence | blocker | next_action |
|---|---|---|---|---|---|---|---|---|
| Historical Trading Calendar | IMPLEMENTED_AND_VERIFIED | `data/trading_calendar.py` | calendar tests | contract/test only; no daily service | Constitution 04 | operational daily integration |  | WP-D2 |
| PIT Universe | IMPLEMENTED_AND_VERIFIED | `universe/contracts.py`, `artifacts.py` | universe tests | artifact construction tested | PIT docs | complete stock/ETF production snapshots |  | WP-D2 |
| Eligibility | IMPLEMENTED_AND_VERIFIED | `universe/eligibility_policy.py`, `eligibility_artifacts.py` | eligibility tests | v1/v2 policies tested | eligibility docs | liquidity/limit/orderability breadth |  | WP-D2 |
| Provider Artifact/Dataset contracts | IMPLEMENTED_AND_VERIFIED | `data/contracts.py`, `data/providers/public_composite/**`, `data/source_manifest.py` | data/provider/manifest tests | LIVE and Replay profiles; immutable Source Archive; verified LIVE blocker | Data Constitution; delivery audit | formal PIT/availability authority | public source semantics | Xuntou shadow/Formal PIT |
| Xuntou Adapter/v4 semantics | IMPLEMENTED_AND_VERIFIED | `research/xuntou_provider_adapter.py`, `xuntou_pit_v4_*` | adapter/preflight/qualification tests | no real runtime in audit env | Xuntou specs/evidence | real qualified bundle | external XtQuant/runtime | Export and qualify input |
| Candidate Dataset | IMPLEMENTED_AND_VERIFIED | `candidates/dataset.py`, `features/daily_pipeline.py` | candidate and daily-pipeline tests | complete outcome-pending daily population in Replay | Candidate Research; delivery audit | formal PIT population evidence | public-source authority | Xuntou shadow/Formal PIT |
| Feature Materialization | IMPLEMENTED_AND_VERIFIED | `features/contracts.py`, baselines, `features/daily_pipeline.py` | feature and daily-pipeline tests | daily smoke materialization and explicit missing-feature block | Factor Constitution; delivery audit | persistent registry/more approved factors |  | WP-D3 |
| B0 | IMPLEMENTED_AND_VERIFIED | `candidates/baselines.py`, `platform/candidate_prediction_adapter.py` | complete PredictionRun equivalence tests | 10-session immutable daily PredictionRuns | Candidate Research; delivery audit | economic/OOS authority |  | Formal PIT/OOS |
| B1 | IMPLEMENTED_AND_VERIFIED | `candidates/composite_baseline.py`, `platform/candidate_prediction_adapter.py` | complete PredictionRun equivalence tests | 10-session immutable daily PredictionRuns | Candidate Research; delivery audit | formal OOS/model winner |  | Formal PIT/OOS |
| B2 regularized statistical baseline | NOT_STARTED | none | none | none | model ladder | implementation/validation |  | After WP-D0 |
| Candidate Directional Diagnostic | IMPLEMENTED_AND_VERIFIED | `candidates/directional_accuracy.py` | diagnostic tests | artifact semantics tested | WP3 docs | longer qualified PIT evidence |  | WP-D8/D11 |
| PIT Replication | BLOCKED_EXTERNAL_INPUT | `research/pit_replication_*` | success/reader/tamper tests | actual run publishes blocker only | PIT charters/protocols | real metrics/partition evidence | qualified v4 input/runtime | WP-D11 |
| Entry Path Target | IMPLEMENTED_AND_VERIFIED | `strategies/entry/contracts.py`, `materialization.py` | Entry path tests | target infrastructure only | Entry Path spec | Entry model/Gate/Assessment |  | WP-D5 |
| Theory/Observable/Model contracts | IMPLEMENTED_AND_VERIFIED | `platform/contracts.py` | platform contract tests | in-process construction | Platform Kernel history/current audit | persistence and broader integration |  | WP-D0 hardening |
| Target/Evaluation Protocol | IMPLEMENTED_AND_VERIFIED | `platform/target_evaluation.py`, `daily_decision/target_adapter.py` | content-addressability/outcome tests | unique MR1 10:30 Target bound through settlement | Platform Kernel; delivery audit | broader registry persistence |  | WP-D0 remainder |
| Experiment Governance | IMPLEMENTED_PROTOTYPE | `platform/experiment_governance.py` | access-budget tests | in-memory only | Platform Kernel history/current audit | durable append-only access authority | process restart/concurrency | WP-D0 hardening |
| Model Registry | IMPLEMENTED_PROTOTYPE_HARDENED_BOUNDARY | `platform/model_registry.py` | registration/restore/lifecycle tests | in-memory only | ADR/delivery audit | durable Registry persistence/concurrency | process-local authority | WP-D0 remainder |
| Multi-model Candidate Prediction Ledger | IMPLEMENTED_EXPLORATORY | `platform/prediction_run.py`, publisher/Reader, B0/B1 adapter | identity/tamper/full equivalence tests | two runs per session across 10-session Replay | delivery audit | formal PIT/OOS authority; durable index beyond daily journal |  | Xuntou shadow/Formal PIT |
| Phase D Daily Decision Artifact | IMPLEMENTED_EXPLORATORY | `daily_decision/artifact.py`, Reader/registry | exact-file/tamper/reconstruction tests | 10 stable Replay hashes and verified LIVE blocker | delivery audit | operational public pool/formal PIT | source authority | Xuntou shadow |
| CandidateRecommendation | IMPLEMENTED_EXPLORATORY | `daily_decision/recommendation.py` | projection/lineage tests | separate per-model Top-5 in 10-session Replay | delivery audit | economic/OOS authority |  | Formal PIT/OOS |
| EntryAssessment | IMPLEMENTED_PLUMBING_ONLY | `daily_decision/entry.py` | WAIT/REJECT/no-ENTER tests | WAIT_CONFIRMATION or REJECT only | ADR/delivery audit | validated Entry model | explicitly not an Entry signal | Entry Model V1 Research |
| Position State | LEGACY_ONLY | `dividend_t/models.py` | Legacy characterization tests | Legacy runtime only | Lifecycle research | canonical actual-fill authority |  | WP-D6 |
| Holding Assessment | DESIGNED_ONLY | spec only | none | none | specification | model/runtime |  | WP-D7 |
| Exit Assessment | LEGACY_ONLY | `dividend_t/sell_side.py`, `risk.py` | Legacy tests | Legacy behavior only | Exit Research/spec | canonical target/model/runtime |  | WP-D7 |
| Manual Trade Record | DESIGNED_ONLY | spec only | none | none | specification | write API and persistence |  | WP-D6 |
| Recommendation Outcome | IMPLEMENTED_EXPLORATORY | `daily_decision/outcome.py`, `outcome_artifact.py` | outcome append/unresolved/tamper tests | MR1 10:30 settlement across 10 Replay sessions | delivery audit | formal PIT/OOS and broader horizons |  | Formal PIT/OOS |
| Daily Review | IMPLEMENTED_EXPLORATORY | `daily_decision/outcome.py`, `outcome_artifact.py` | review reconstruction tests | 10 immutable reviews with full fixture coverage | delivery audit | rolling 5/20/60 review and attribution |  | WP-D8 remainder |
| Daily Runtime Journal | IMPLEMENTED_EXPLORATORY | `application/daily_loop/**` | identity/state/idempotency/recovery tests | SQLite restart recovery; single/10-session Replay; LIVE blocker | ADR/delivery audit | leases/concurrent worker/postgres authority | single-process runtime | later service hardening |
| Historical daily_research V1 | FROZEN_COMPATIBILITY | `daily_research/**` | unchanged V1 tests | historical six-file semantics preserved | ADR/baseline audit | none in Phase D scope | must not mutate | Versioned Reader only |
| Portfolio Decision | NOT_STARTED | Legacy position sizing only | Legacy tests | none canonical | Strategy Constitution | canonical policy/simulator |  | WP-D9 |
| Codex Feedback | DESIGNED_ONLY | none canonical | none | none | Failure Attribution | Evidence Pack/proposal workflow |  | WP-D10 |
| QuantDesk | NOT_STARTED | none in repo | none | none | integration boundary | API/UI integration | external project/scope | WP-D12 |
| Legacy dividend_t | LEGACY_ONLY | `dividend_t/**`, Legacy web/schedulers | extensive Legacy tests | operational/replay paths | Legacy docs | canonical extraction evidence |  | Strangler program |
