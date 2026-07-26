# Gap Register

> **Status:** CURRENT_STATUS  
> **Authority:** Ordered gap and dependency register  
> **Owner:** Market Regime Alpha maintainers  
> **Last Updated:** 2026-07-26  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** Current-State.md, ../roadmap/Phase-D-Work-Packages.md  
> **Code Evidence:** Derived from full repository audit

| Gap | Priority | Current state | Dependency | Exit condition |
|---|---|---|---|---|
| Platform Registry/Governance not on main | P0 | Draft PR #12 | review/rebase | merged and post-merge CI verified |
| Unique daily source manifest/snapshot | P0 | designed | data/time contracts | immutable DailyResearchSnapshot produced |
| Stock/ETF universe and mappings | P0 | partial contracts | provider/reference data | daily PIT snapshots with quality reports |
| Market/ETF/theme/capital context | P1 | partial/none | universe/mappings | canonical snapshots and ablations |
| Multi-model daily Prediction Ledger | P1 | candidate runners exist | platform registry | all shadow models run and freeze full ranks |
| CandidateRecommendation presentation | P1 | designed | prediction ledger | structured reasons/risks generated |
| EntryAssessment | P1 | target infrastructure only | Candidate and intraday evidence | ENTER/WAIT/REJECT assessed and evaluated |
| Canonical PositionSnapshot/manual records | P1 | Legacy only | manual execution domain | actual fills own position state |
| Holding and Exit | P1 | designed/Legacy | position authority | independent targets/models/assessments |
| Outcome matching and rolling scorecards | P1 | partial diagnostics | frozen predictions | automated 5/20/60-day results |
| Failure Attribution/Codex Evidence Pack | P2 | designed | review ledger | proposals generated without model mutation |
| Portfolio/execution simulation | P2 | Legacy only | validated component models | T+1/cost/capacity-aware simulator |
| Qualified Xuntou formal run | External P0 | blocked | XtQuant/v4 bundle | real partition run and verified artifact |
| QuantDesk workbench | P3 | not started | stable APIs/contracts | UI consumes canonical artifacts only |
