# Capability Matrix

> **Status:** CURRENT_STATUS
> **Authority:** Current capability and evidence-ceiling matrix
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-11
> **Code Evidence:** `src/market_regime_alpha`, `src/market_regime_alpha/persistence/postgres/schema.py`, `tests`

| Capability | Engineering state | Current Authority / ceiling |
|---|---|---|
| Continuous scheduling, lease, fence, recovery | Implemented | one PostgreSQL Runtime; Research/Shadow only for free data |
| BaoStock/Tencent acquisition and archive | Implemented | recorded exploratory evidence, not Formal PIT |
| Full A-share Research Universe | Operational engineering complete | append-only BaoStock Security Master/Research Universe snapshots retain `UNKNOWN`; `PIT_INCOMPLETE` |
| ETF/Index/Industry/Theme Reference | Engineering complete | Declared/Derived/Proxy are distinct, versioned and lineage-bound; free mappings remain Proxy |
| Dataset and Feature materialization | Implemented | canonical content-addressed artifacts |
| Formal PIT mechanics | Implemented mechanics | real qualified Provider/fact coverage absent |
| Model Registry and Research/Shadow selection | Implemented | PostgreSQL Governance |
| Production model qualification | Closed | owner resolution incomplete; always not qualified |
| Market/ETF/Theme/Capital State | Implemented | PostgreSQL State owner; models remain unvalidated |
| StateSeries / Dynamic Pool / Candidate | Implemented | PostgreSQL receipt and CAS authority |
| Free Historical Sample pipeline | Operationally implemented | BaoStock retrospective decisions/outcomes; PostgreSQL `UNQUALIFIED`, `FREE_DATA_EXPLORATORY` only |
| Minute / Signal / PathForecast | Operationally wired for free Research/Shadow | Historical Registry samples may produce exploratory uncalibrated Forecast; no samples fails closed; Production excluded |
| ResearchDailySummary | Implemented | canonical Research/Shadow summary projection |
| Opportunity / Thesis / Portfolio / Risk | Implemented mechanics | human decision support; no actual Position creation |
| Manual Fill / fill-derived Position | Implemented | only observed Fill creates actual Position |
| Research Shadow | Operational loop implemented | `run-day` freeze and `settle-day` T+1 Outcome/Target/Panel/Enrichment; prospective proof remains false |
| Prospective attestation | Implemented mechanics | owner-checked, always `prospective_proven=false` |
| Evaluation Dataset / Panel V2 / Factor Extraction | Implemented | immutable engineering evidence |
| Factor catalog / de-dup / ablation / liquidity-capacity | Implemented harness | versioned lineage and provenance; exploratory assumptions are not facts or calibration |
| Calibration | Implemented fit/evaluation | `calibrated=false` |
| Formal Evaluation | Engineering complete metric runtime | cross-sectional IC/RankIC, Top-K/spread/hit/MFE/MAE/turnover/drawdown/lift, cluster CI and multiple testing; durable Formal OOS Authority disabled |
| Entry research | Implemented harness | Shadow decision only; no Canonical `ENTER` |
| Strategy Shadow | Operational loop implemented | Entry/Fill/Position/Holding/Exit/Outcome via Continuous CLI; simulated ledger, no real mutation |
| Portfolio Strategy Shadow | Operational engineering complete | Top1/3/5 Equal/Score/Risk, Cash/NAV/exposure/turnover/cost/capacity/drawdown/attribution and A-share constraints; no real mutation |
| Operator surface convergence | Implemented | six installed scripts and six installed CLI module guards; day/settle/strategy/portfolio/report/resume/replay under existing CLIs |
| Holding/Exit validation | Implemented engineering floors | `holding_exit_validated=false` |
| Production Admission | Projection only | always `BLOCKED`; no final writer |
| Principal/RBAC/Approval/Audit | Engineering complete | append-only PostgreSQL roles, revocation, separation and audit; external authentication not bound; no Production/Broker permission |
| Recovery/DR | Operational engineering complete | journal resume, recovery-audit, replay and isolated PostgreSQL/artifact backup-restore verification; deployment drill evidence pending |
| Broker integration | Prohibited/currently absent | no live adapter authority |
