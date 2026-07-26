# Current Capability Matrix

> **Status:** CURRENT_STATUS  
> **Authority:** Canonical implementation-status matrix  
> **Owner:** Market Regime Alpha maintainers  
> **Last Updated:** 2026-07-26  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** Current-State.md, Gap-Register.md, ../audit/Post-Consolidation-Code-Audit-2026-07-26.md
> **Code Evidence:** main@772ecfb09410588b5a406ad900d793a5850e60d5 for the audited implementation baseline; path:tests/daily_research/test_v1_characterization.py for convergence evidence

| capability | status | code_evidence | test_evidence | runtime_evidence | document_evidence | missing_evidence | blocker | next_action |
|---|---|---|---|---|---|---|---|---|
| Historical Trading Calendar | IMPLEMENTED_AND_VERIFIED | `data/trading_calendar.py` | calendar tests | contract/test only; no daily service | Constitution 04 | operational daily integration |  | WP-D2 |
| PIT Universe | IMPLEMENTED_AND_VERIFIED | `universe/contracts.py`, `artifacts.py` | universe tests | artifact construction tested | PIT docs | complete stock/ETF production snapshots |  | WP-D2 |
| Eligibility | IMPLEMENTED_AND_VERIFIED | `universe/eligibility_policy.py`, `eligibility_artifacts.py` | eligibility tests | v1/v2 policies tested | eligibility docs | liquidity/limit/orderability breadth |  | WP-D2 |
| Provider Artifact/Dataset contracts | IMPLEMENTED_AND_VERIFIED | `data/contracts.py`, provider artifacts | data/provider tests | eligibility ceilings tested | Data Constitution | daily Source Manifest |  | WP-D1 |
| Xuntou Adapter/v4 semantics | IMPLEMENTED_AND_VERIFIED | `research/xuntou_provider_adapter.py`, `xuntou_pit_v4_*` | adapter/preflight/qualification tests | no real runtime in audit env | Xuntou specs/evidence | real qualified bundle | external XtQuant/runtime | Export and qualify input |
| Candidate Dataset | IMPLEMENTED_AND_VERIFIED | `candidates/dataset.py`, `panel.py` | candidate dataset/panel tests | complete-population semantics tested | Candidate Research | daily ledger integration |  | WP-D4 |
| Feature Materialization | IMPLEMENTED_AND_VERIFIED | `features/contracts.py`, baselines | feature tests | contract/materialization tested | Factor Constitution | persistent registry/more approved factors |  | WP-D3 |
| B0 | IMPLEMENTED_AND_VERIFIED | `candidates/baselines.py` | baseline tests | deterministic ranks | Candidate Research | economic/OOS authority |  | WP-D4/D11 |
| B1 | IMPLEMENTED_AND_VERIFIED | `candidates/composite_baseline.py` | composite tests | descriptive/exploratory runs | Candidate Research | formal OOS/model winner |  | WP-D4/D11 |
| B2 regularized statistical baseline | NOT_STARTED | none | none | none | model ladder | implementation/validation |  | After WP-D0 |
| Candidate Directional Diagnostic | IMPLEMENTED_AND_VERIFIED | `candidates/directional_accuracy.py` | diagnostic tests | artifact semantics tested | WP3 docs | longer qualified PIT evidence |  | WP-D8/D11 |
| PIT Replication | BLOCKED_EXTERNAL_INPUT | `research/pit_replication_*` | success/reader/tamper tests | actual run publishes blocker only | PIT charters/protocols | real metrics/partition evidence | qualified v4 input/runtime | WP-D11 |
| Entry Path Target | IMPLEMENTED_AND_VERIFIED | `strategies/entry/contracts.py`, `materialization.py` | Entry path tests | target infrastructure only | Entry Path spec | Entry model/Gate/Assessment |  | WP-D5 |
| Theory/Observable/Model contracts | IMPLEMENTED_AND_VERIFIED | `platform/contracts.py` | platform contract tests | in-process construction | Platform Kernel history/current audit | persistence and broader integration |  | WP-D0 hardening |
| Target/Evaluation Protocol | IMPLEMENTED_AND_VERIFIED | `platform/target_evaluation.py` | content-addressability tests | in-process construction | Platform Kernel history/current audit | registry/persistence/runtime binding |  | WP-D0 hardening |
| Experiment Governance | IMPLEMENTED_PROTOTYPE | `platform/experiment_governance.py` | access-budget tests | in-memory only | Platform Kernel history/current audit | durable append-only access authority | process restart/concurrency | WP-D0 hardening |
| Model Registry | IMPLEMENTED_PROTOTYPE | `platform/model_registry.py` | lifecycle transition tests | in-memory only | Platform Kernel history/current audit | registration hardening, durable recovery | direct registration/persistence gaps | WP-D0 hardening |
| Multi-model Candidate Slice | IMPLEMENTED_PROTOTYPE | `platform/multi_model_slice.py` | three-model slice tests | fixture/in-process run | Research Platform Vertical Slice | protocol-bound immutable PredictionRun and outcomes | no daily ledger | WP-D0/WP-D4 |
| Daily Research V1 compatibility layer | IMPLEMENTED_NON_CANONICAL | `daily_research/**` | `tests/daily_research/**`, including frozen module/schema/JSON characterization | immutable package publication/semantic read tested | convergence ADR and historical V1 specification | production Adapter after stabilized WP-D0 contracts | field semantics differ from current Phase D specs | post-WP-D0 Adapter |
| Canonical Phase D DailyResearchSnapshot | DESIGNED_ONLY | spec only; V1 namesake is non-canonical | none for current contract | none | current specification | canonical code/runtime | V1 cannot be renamed into compliance | WP-D1/D2 |
| Canonical CandidateRecommendation | DESIGNED_ONLY | spec only; V1 namesake is non-canonical | none for current contract | CandidatePrediction and V1 compatibility object only | current specification | application projection/ledger | requires canonical PredictionRun | WP-D4 |
| Canonical EntryAssessment | DESIGNED_ONLY | spec only; V1 namesake is non-canonical | none for current contract | Entry target and V1 compatibility object only | current specification | model/assessment runtime | requires CandidateRecommendation and Entry evidence | WP-D5 |
| Position State | LEGACY_ONLY | `dividend_t/models.py` | Legacy characterization tests | Legacy runtime only | Lifecycle research | canonical actual-fill authority |  | WP-D6 |
| Holding Assessment | DESIGNED_ONLY | spec only | none | none | specification | model/runtime |  | WP-D7 |
| Exit Assessment | LEGACY_ONLY | `dividend_t/sell_side.py`, `risk.py` | Legacy tests | Legacy behavior only | Exit Research/spec | canonical target/model/runtime |  | WP-D7 |
| Manual Trade Record | DESIGNED_ONLY | spec only | none | none | specification | write API and persistence |  | WP-D6 |
| Outcome materialization and Candidate diagnostics | IMPLEMENTED_AND_VERIFIED | target materializers/diagnostics | research tests | separate research paths | Candidate/Validation research | canonical daily outcome binding |  | WP-D8 |
| Canonical RecommendationOutcome | DESIGNED_ONLY | specification only | none for current contract | none | current specification | unified daily outcome ledger | requires frozen PredictionRun/recommendation | WP-D8 |
| Daily Review | DESIGNED_ONLY | spec only | none | none | specification | daily/rolling runtime |  | WP-D8 |
| Portfolio Decision | NOT_STARTED | Legacy position sizing only | Legacy tests | none canonical | Strategy Constitution | canonical policy/simulator |  | WP-D9 |
| Codex Feedback | DESIGNED_ONLY | none canonical | none | none | Failure Attribution | Evidence Pack/proposal workflow |  | WP-D10 |
| QuantDesk | NOT_STARTED | none in repo | none | none | integration boundary | API/UI integration | external project/scope | WP-D12 |
| Legacy dividend_t | LEGACY_ONLY | `dividend_t/**`, Legacy web/schedulers | extensive Legacy tests | operational/replay paths | Legacy docs | canonical extraction evidence |  | Strangler program |
