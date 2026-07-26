# Current Capability Matrix

> **Status:** CURRENT_STATUS  
> **Authority:** Canonical implementation-status matrix  
> **Owner:** Market Regime Alpha maintainers  
> **Last Updated:** 2026-07-26  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** Current-State.md, Gap-Register.md, ../audit/Repository-Audit-Baseline-2026-07-26.md  
> **Code Evidence:** main@96e41a12d86b3b5f7472c2d4e44011736b087b6b

| capability | status | code_evidence | test_evidence | runtime_evidence | document_evidence | missing_evidence | blocker | next_action |
|---|---|---|---|---|---|---|---|---|
| Historical Trading Calendar | IMPLEMENTED_AND_VERIFIED | `data/trading_calendar.py` | calendar tests | contract/test only; no daily service | Constitution 04; R3/R4 docs | operational daily integration |  | Integrate in WP-D2 |
| PIT Universe | IMPLEMENTED_AND_VERIFIED | `universe/contracts.py`, `artifacts.py` | universe tests | artifact construction tested | R5/PIT docs | complete stock/ETF production snapshots |  | WP-D2 |
| Eligibility | IMPLEMENTED_AND_VERIFIED | `universe/eligibility_policy.py`, `eligibility_artifacts.py` | eligibility tests | v1/v2 policies tested | R5 eligibility docs | liquidity/limit/orderability breadth |  | WP-D2 |
| Provider Artifact/Dataset contracts | IMPLEMENTED_AND_VERIFIED | `data/contracts.py`, provider artifacts | data/provider tests | eligibility ceilings tested | Data Constitution | daily source manifest |  | WP-D1 |
| Xuntou Adapter/v4 semantics | IMPLEMENTED_AND_VERIFIED | `research/xuntou_provider_adapter.py`, `xuntou_pit_v4_*` | adapter/preflight/qualification tests | no real runtime in audit env | Xuntou specs/evidence | real qualified bundle | external XtQuant/runtime | Export and qualify input |
| Candidate Dataset | IMPLEMENTED_AND_VERIFIED | `candidates/dataset.py`, `panel.py` | candidate dataset/panel tests | complete-population semantics tested | Candidate/R5 docs | daily ledger integration |  | WP-D4 |
| Feature Materialization | IMPLEMENTED_AND_VERIFIED | `features/contracts.py`, baselines | feature tests | contract/materialization tested | Factor Constitution | persistent registry/more approved factors |  | WP-D0/D3 |
| B0 | IMPLEMENTED_AND_VERIFIED | `candidates/baselines.py` | baseline tests | deterministic ranks | Candidate Research | economic/OOS authority |  | WP-D4/D11 |
| B1 | IMPLEMENTED_AND_VERIFIED | `candidates/composite_baseline.py` | composite tests | descriptive/exploratory runs | Candidate/MR2 docs | formal OOS/model winner |  | WP-D4/D11 |
| B2+ | NOT_STARTED | none | none | none | model ladder only | implementation/validation |  | After WP-D0 |
| Candidate Directional Diagnostic | IMPLEMENTED_AND_VERIFIED | `candidates/directional_accuracy.py` | diagnostic tests | artifact semantics tested | WP3 docs | longer qualified PIT evidence |  | WP-D8/D11 |
| PIT Replication | BLOCKED_EXTERNAL_INPUT | `research/pit_replication_*` | success/reader/tamper tests | actual run publishes blocker only | PIT charters/protocols | real metrics/partition evidence | qualified v4 input/runtime | WP-D11 |
| Entry Path Target | IMPLEMENTED_AND_VERIFIED | `strategies/entry/contracts.py`, `materialization.py` | Entry path tests | target infrastructure only | Entry Path spec | Entry model/Gate/Assessment |  | WP-D5 |
| DailyResearchSnapshot | DESIGNED_ONLY | spec only | none | none | new spec | canonical code/runtime |  | WP-D1/D2 |
| CandidateRecommendation | DESIGNED_ONLY | spec only | none | CandidatePrediction exists only | new spec | application projection/ledger |  | WP-D4 |
| EntryAssessment | DESIGNED_ONLY | spec only | none | Entry target only | new spec | model/assessment runtime |  | WP-D5 |
| Position State | LEGACY_ONLY | `dividend_t/models.py` | Legacy characterization tests | Legacy runtime only | Lifecycle research | canonical actual-fill authority |  | WP-D6 |
| Holding Assessment | DESIGNED_ONLY | spec only | none | none | new spec | model/runtime |  | WP-D7 |
| Exit Assessment | LEGACY_ONLY | `dividend_t/sell_side.py`, `risk.py` | Legacy tests | Legacy behavior only | Exit Research/spec | canonical target/model/runtime |  | WP-D7 |
| Manual Trade Record | DESIGNED_ONLY | spec only | none | none | new spec | write API and persistence |  | WP-D6 |
| Recommendation Outcome | PARTIALLY_IMPLEMENTED | target materializers/diagnostics | research tests | separate paths only | new spec | unified daily ledger |  | WP-D8 |
| Daily Review | DESIGNED_ONLY | spec only | none | none | new spec | daily/rolling runtime |  | WP-D8 |
| Portfolio Decision | NOT_STARTED | Legacy position sizing only | Legacy tests | none canonical | Strategy Constitution | canonical policy/simulator |  | WP-D9 |
| Model Registry/Experiment Governance | CONTRACT_ONLY | Draft PR #12 | PR #12 CI passed | not on main | Current State/roadmap | merged main evidence | PR not merged | WP-D0 |
| Codex Feedback | DESIGNED_ONLY | none canonical | none | none | Failure Attribution | Evidence Pack/proposal workflow |  | WP-D10 |
| QuantDesk | NOT_STARTED | none in repo | none | none | integration boundary | API/UI integration | external project/scope | WP-D12 |
| Legacy dividend_t | LEGACY_ONLY | `dividend_t/**`, Legacy web/schedulers | extensive Legacy tests | operational/replay paths | Legacy docs | canonical extraction evidence |  | Strangler program |
