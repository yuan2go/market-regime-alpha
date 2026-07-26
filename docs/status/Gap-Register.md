# Gap Register

> **Status:** CURRENT_STATUS  
> **Authority:** Ordered gap and dependency register  
> **Owner:** Market Regime Alpha maintainers  
> **Last Updated:** 2026-07-26  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** Current-State.md, ../roadmap/Phase-D-Work-Packages.md, ../audit/Post-Consolidation-Code-Audit-2026-07-26.md
> **Code Evidence:** Derived from current main code/tests at `772ecfb09410588b5a406ad900d793a5850e60d5`

| Gap | Priority | Current state | Dependency | Exit condition |
|---|---|---|---|---|
| Daily V1/Phase D contract convergence | P0 | historical V1 Artifact/Reader implemented but non-canonical; current Phase D contracts designed | fixed V1 characterization and current specs | one ADR and field matrix freeze V1, identify loss, and define one canonical V2/adapter boundary without changing V1 identity |
| Platform Kernel governance hardening | P0 | contracts and in-memory prototype merged | current platform code/tests | registration gates closed; data/evidence semantics separated; persistent/recoverable boundary defined; platform included in mypy; B0/B1 equivalence evidence published |
| Unique daily Source Manifest and quality gates | P0 | designed; provider contracts exist | data/time contracts | immutable Source Manifest and quality report produced |
| Stock/ETF universe and mappings | P0 | partial contracts | provider/reference data | daily PIT snapshots with quality reports |
| Tencent exploratory daily vertical slice | P0E | research components and non-canonical daily V1 exist; canonical orchestration absent | Source Manifest, Universe, canonical DailyResearchSnapshot | 10-session replay with frozen predictions, outcomes, blocked-day evidence and stable hashes |
| Market/ETF/theme/capital context | P1 | partial/none | universe/mappings | canonical snapshots and ablations |
| Multi-model daily Prediction Ledger | P1 | mechanical multi-model slice exists | hardened platform kernel and daily snapshot | all shadow models run and freeze complete ranks/rejections as immutable PredictionRuns |
| CandidateRecommendation presentation | P1 | designed | Prediction Ledger | structured reasons/risks generated without trade authority |
| EntryAssessment | P1 | target infrastructure only | Candidate and intraday evidence | ENTER/WAIT/REJECT assessed and evaluated |
| Canonical PositionSnapshot/manual records | P1 | Legacy only | manual execution domain | actual fills own position state |
| Holding and Exit | P1 | designed/Legacy | position authority | independent targets/models/assessments |
| Outcome matching and rolling scorecards | P1 | partial diagnostics | frozen predictions | automated 5/20/60-day results |
| Failure Attribution/Codex Evidence Pack | P2 | designed | review ledger | proposals generated without model mutation |
| Portfolio/execution simulation | P2 | Legacy only | validated component models | T+1/cost/capacity-aware simulator |
| Qualified Xuntou formal run | External P0 | blocked | XtQuant/v4 bundle | real partition run and verified artifact |
| QuantDesk workbench | P3 | not started | stable APIs/contracts | UI consumes canonical artifacts only |
