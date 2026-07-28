# Gap Register

> **Status:** CURRENT_STATUS  
> **Authority:** Ordered gap and dependency register  
> **Owner:** Market Regime Alpha maintainers  
> **Last Updated:** 2026-07-28
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** Current-State.md, ../roadmap/Phase-D-Work-Packages.md, ../audit/Run-First-Daily-Platform-Delivery.md
> **Code Evidence:** Derived from `feat/run-first-exploratory-daily-platform@dc9f27a68d3febd4a461e3e299af6ccbba3e70d0`

| Gap | Priority | Current state | Dependency | Exit condition |
|---|---|---|---|---|
| Platform governance persistence remainder | P1 | minimum registration/restore/data-evidence/PredictionRun boundary hardened; daily Runtime Journal durable | current platform code/tests | durable Model Registry and Experiment Governance with concurrency/recovery authority |
| Public-source formal availability/PIT | P0 | immutable SourceManifest and fail-closed quality gate operational; LIVE dry run blocked truthfully | provider/reference data | qualified availability, trading status, PIT membership and eligibility evidence |
| Operational 100–300 A-share universe | P0 | content-addressed configurable policy contract; fixed 20-symbol smoke runtime | approved membership/mapping/liquidity source | configured operational pool with every symbol eligible or excluded and stable replay |
| Run-first exploratory daily vertical slice | DELIVERED_P0E | recoverable Phase D loop operational on delivery branch | implemented contracts and fixture/public evidence | completed: single/10-session replay, frozen predictions/outcomes/reviews, verified LIVE blocker and stable hashes |
| Market/ETF/theme/capital context | P1 | partial/none | universe/mappings | canonical snapshots and ablations |
| Multi-model daily Prediction Ledger | DELIVERED_P1 | B0/B1 complete immutable PredictionRuns published and replayed | existing model identities and rankers | completed for the fixed B0/B1 exploratory model set |
| CandidateRecommendation presentation | DELIVERED_P1 | per-model Top-5 structured reasons/risks without trade authority | PredictionRuns | completed for exploratory daily loop |
| Real Entry Model | P1 | plumbing gate only; eligible Candidates always WAIT_CONFIRMATION | Candidate and qualified intraday evidence | validated Entry model with frozen protocol; no authority inflation |
| Canonical PositionSnapshot/manual records | P1 | Legacy only | manual execution domain | actual fills own position state |
| Holding and Exit | P1 | designed/Legacy | position authority | independent targets/models/assessments |
| Outcome matching and rolling scorecards | P1 | append-only MR1 10:30 daily Outcome/Review implemented | frozen predictions | automated 5/20/60-session review and attribution |
| Failure Attribution/Codex Evidence Pack | P2 | designed | review ledger | proposals generated without model mutation |
| Portfolio/execution simulation | P2 | Legacy only | validated component models | T+1/cost/capacity-aware simulator |
| Xuntou Provider shadow integration | External P0 | Provider boundary ready; qualified input still blocked | XtQuant/v4 bundle and Windows exporter | same-pipeline shadow run and ProviderComparisonReport without authority promotion |
| QuantDesk workbench | P3 | not started | stable APIs/contracts | UI consumes canonical artifacts only |
