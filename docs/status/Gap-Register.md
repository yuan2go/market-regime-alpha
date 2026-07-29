# Gap Register

> **Status:** CURRENT_STATUS  
> **Authority:** Ordered gap and dependency register  
> **Owner:** Market Regime Alpha maintainers  
> **Last Updated:** 2026-07-30
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** Current-State.md, ../roadmap/Phase-D-Work-Packages.md, ../architecture/09-Platform-Architecture-V2.md, ../audit/Run-First-Daily-Platform-Delivery.md, ../audit/WP-D3-Public-Live-Semantic-Closure.md, ../audit/WP-D3-1-Real-Decision-Evidence-Delivery.md, ../audit/WP-PAV2-Platform-Architecture-V2-Delivery.md
> **Code Evidence:** Derived from `feat/platform-architecture-v2-research-layer@64cacd2`

| Gap | Priority | Current state | Dependency | Exit condition |
|---|---|---|---|---|
| Platform governance persistence remainder | P1 | minimum registration/restore/data-evidence/PredictionRun boundary hardened; daily Runtime Journal durable | current platform code/tests | durable Model Registry and Experiment Governance with concurrency/recovery authority |
| Public LIVE current-status and Decision-window closure | P0 | History/Status/Quote V3 stages, exact-date BaoStock status and scheduling CLI implemented; off-window real LIVE/Archive remain verified `DATA_BLOCKED` | observe BaoStock current row and Tencent Quote inside controlled 14:55 schedule | real Archive reaches `OUTCOME_PENDING` with stable replay and nonempty Features/B0/B1 |
| Public-source formal availability/PIT | P0 | historical public retrieval semantics are explicit and EXPLORATORY; no invented availability/finality | provider/reference data | qualified availability and formal PIT status/inventory evidence |
| Operational 100–300 A-share universe | BLOCKED_P0 | content-addressed configurable policy contract; fixed 20-symbol smoke runtime only | successful real WP-D3 Archive plus approved membership/mapping/liquidity source | configured operational pool with every symbol eligible or excluded and stable replay |
| Run-first exploratory daily vertical slice | DELIVERED_P0E | recoverable Phase D loop operational on delivery branch | implemented contracts and fixture/public evidence | completed: single/10-session replay, frozen predictions/outcomes/reviews, verified LIVE blocker and stable hashes |
| Platform V2 Research Layer MVP | DELIVERED_P1 | six-layer boundaries plus executable Market/Theme/Capital/Candidate pipeline, Artifact Reader and deterministic Replay | typed fixture or historical immutable Archive | completed engineering slice; remains EXPLORATORY and offline |
| Market/ETF/theme/capital operational evidence | P1 | deterministic V0 snapshots implemented from typed observations; weights and thresholds unvalidated | PIT theme mappings and qualified historical observations | historical Archive evaluation, ablation and calibrated operating protocol |
| Signal Engine MVP | P1 | versioned SignalSnapshot boundary only | qualified CandidateSet and Signal research protocol | executable, replayable Signal model with incremental evaluation |
| Next-session Forecast | P1 | strict uncalibrated contract only | Signal evidence, frozen Target and calibration protocol | out-of-sample calibrated forecast; model score never substituted for probability |
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
