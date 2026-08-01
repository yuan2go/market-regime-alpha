# Gap Register

> **Status:** CURRENT_STATUS  
> **Authority:** Ordered gap and dependency register  
> **Owner:** Market Regime Alpha maintainers  
> **Last Updated:** 2026-08-01  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** Current-State.md, ../roadmap/Phase-D-Work-Packages.md, ../roadmap/work-packages/WP-PDL-Production-Decision-Lifecycle.md, ../architecture/09-Platform-Architecture-V2.md, ../architecture/10-Production-Decision-Lifecycle.md, ../audit/Run-First-Daily-Platform-Delivery.md, ../audit/WP-D3-Public-Live-Semantic-Closure.md, ../audit/WP-D3-1-Real-Decision-Evidence-Delivery.md, ../audit/WP-PAV2-Platform-Architecture-V2-Delivery.md, ../audit/Production-Decision-Lifecycle-Gap-Analysis.md, ../audit/Production-Decision-Lifecycle-Delivery.md
> **Code Evidence:** Current `main`; production-lifecycle target documents do not establish implementation.

| Gap | Priority | Current state | Dependency | Exit condition |
|---|---|---|---|---|
| Production Decision Lifecycle architecture baseline | DOCUMENTED | Requirements, Architecture 10, ADR-004, gap analysis, WP-PDL, runbook and Claude prompt committed | documentation set | completed as documentation only; runtime gaps below remain open |
| Platform governance persistence remainder | P1 | minimum registration/restore/data-evidence/PredictionRun boundary hardened; daily Runtime Journal durable | current platform code/tests | durable Model Registry and Experiment Governance with concurrency/recovery authority |
| Operational Research Bridge | DELIVERED_P1 | verified Daily and supplemental Artifacts compose through a fail-closed adapter and explicit-config run/replay CLI; duplicate execution is content-idempotent | qualified operational Theme/Capital/PIT mapping evidence | engineering slice complete; external evidence remains blocked without authority inflation |
| Public LIVE current-status and Decision-window closure | P0 | History/Status/Quote V3 stages, exact-date BaoStock status and scheduling CLI implemented; off-window real LIVE/Archive remain verified `DATA_BLOCKED` | observe BaoStock current row and Tencent Quote inside controlled 14:55 schedule | real Archive reaches `OUTCOME_PENDING` with stable replay and nonempty Features/B0/B1 |
| Public-source formal availability/PIT | P0 | historical public retrieval semantics are explicit and EXPLORATORY; no invented availability/finality | provider/reference data | qualified availability and formal PIT status/inventory evidence |
| Operational 100–300 A-share universe | BLOCKED_P0 | content-addressed configurable policy contract; fixed 20-symbol smoke runtime only | successful real WP-D3 Archive plus approved membership/mapping/liquidity source | configured operational pool with every symbol eligible or excluded and stable replay |
| Run-first exploratory daily vertical slice | DELIVERED_P0E | recoverable Phase D loop operational on delivery branch | implemented contracts and fixture/public evidence | completed: single/10-session replay, frozen predictions/outcomes/reviews, verified LIVE blocker and stable hashes |
| Platform V2 Research Layer MVP | DELIVERED_P1 | six-layer boundaries plus executable Market/Theme/Capital/Candidate pipeline, Artifact Reader and deterministic Replay | typed fixture or historical immutable Archive | completed engineering slice; remains EXPLORATORY and offline |
| Market/ETF/theme/capital operational evidence | P1 | deterministic V0 snapshots implemented from typed observations; weights and thresholds unvalidated | PIT theme mappings and qualified historical observations | historical Archive evaluation, overlap ablation and calibrated operating protocol |
| Theme and Capital historical lifecycle semantics | P1 | current V0 labels are direct score classifications without previous-state duration or hysteresis | historical typed observations and transition protocol | separate replayable lifecycle snapshots with validated transition behavior |
| Signal Engine MVP | P1 | versioned SignalSnapshot boundary only | qualified CandidateSet and Signal research protocol | executable, replayable Signal model with incremental evaluation |
| Multi-horizon PathForecast | P1 | strict next-session uncalibrated contract and EntryPath target infrastructure exist | Signal evidence, frozen path target and calibration protocol | replayable PathForecast with horizon, barriers, MFE/MAE, quantiles and honest calibration status |
| TradingOpportunity and TradingThesis | P1 | documented target only | CandidateSet, SignalSnapshot and PathForecast | durable stateful aggregates with expiry, invalidation, audit and concurrency tests |
| Independent Risk Authority | P1 | Market Regime exposure guidance exists; no canonical portfolio hard-risk decision | active thesis, current position/cash and approved limits | fail-closed RiskDecision with symbol/theme/gross/liquidity/T+1/loss-budget constraints |
| Multi-model daily Prediction Ledger | DELIVERED_P1 | B0/B1 complete immutable PredictionRuns published and replayed | existing model identities and rankers | completed for the fixed B0/B1 exploratory model set |
| CandidateRecommendation presentation | DELIVERED_P1 | per-model Top-5 structured reasons/risks without trade authority | PredictionRuns | completed for exploratory daily loop; fixed MR1 semantics preserved |
| Real Entry Model | P1 | plumbing gate only; eligible Candidates always WAIT_CONFIRMATION | Candidate, Signal and qualified decision-time evidence | validated Entry/Opportunity protocol with no authority inflation |
| Manual Execution Ledger | P1 | no canonical manual intent, order or fill authority | approved RiskDecision and operator identity | append-only ManualTradeRecord/Fill/correction ledger with idempotency and reconciliation |
| Canonical PositionSnapshot | P1 | Legacy only; no canonical actual-position authority | Manual Execution Ledger | PositionSnapshot rebuilt deterministically from actual fills |
| Holding and Exit | P1 | designed/Legacy | canonical position authority and current evidence | independent targets/models/assessments with ADD requiring fresh risk approval |
| Complete-trade attribution and rolling scorecards | P1 | append-only MR1 10:30 daily Outcome/Review implemented | authoritative positions, assessments and closed trades | selection/entry/holding/exit/sizing/execution attribution plus protocol-bound rolling scorecards |
| Authentication, permissions and operator audit | P1 | no confirmed canonical production implementation | application commands and role model | actor/permission enforcement for risk, manual records, reconciliation and model transitions |
| Operational metrics, trace and alerts | P1 | artifact/reason-code audit exists; no confirmed production telemetry stack | operational application services | source/stage/opportunity/risk/execution/position/model metrics, trace and alerts |
| Failure Attribution/Codex Evidence Pack | P2 | designed | review ledger | proposals generated without model mutation |
| Portfolio/execution simulation | P2 | Legacy only | validated component models and Risk Authority | T+1/cost/capacity-aware simulator using canonical target positions |
| Xuntou Provider shadow integration | External P0 | Provider boundary ready; qualified input still blocked | XtQuant/v4 bundle and Windows exporter | same-pipeline shadow run and ProviderComparisonReport without authority promotion |
| QuantDesk workbench | P3 | not started | stable application commands, queries and read models | UI consumes canonical artifacts and ledgers only |
| Future broker adapter | DEFERRED | not authorized by WP-PDL | sustained shadow/manual evidence and separate security/architecture approval | versioned approved-intent port, append-only execution events, reconciliation and kill switch |
