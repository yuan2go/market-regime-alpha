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
| Formal Protocol / Frozen Calendar | Operational engineering complete | the CLI accepts only a Formal Protocol reference; Target, Calendar, Dataset, Universe, Historical Sample, Feature, Factor, Model, Threshold, Cost, Calibration, Strategy, Entry/Holding/Exit and Evaluation are reloaded from PostgreSQL owners and preserved in immutable owner-resolution receipts; no current formal protocol evidence |
| Formal Forecast computation | Operational engineering complete | caller supplies only Formal Protocol, Formal PIT, symbol and idempotency scope; PostgreSQL owners resolve DecisionTime and all Model/Configuration/Code/Data/Feature/Factor/Threshold/Target lineage, PostgreSQL assigns materialization time, deterministic replay is required, and unsupported executors return `NOT_ESTIMABLE`; legacy submitted values are exploratory-only |
| Provider Fact Qualification V2 | Operational engineering complete | exact Provider×Contract×Fact owner; current BaoStock/Tencent scopes are `REJECTED`, never silently promoted |
| Historical Sample Qualification | Owner writer implemented | reloads Protocol/PIT request/Target/Provider/Targeted Outcome owners and requires exact Dataset, symbol, label interval/value and complete selected-Fact lineage; current evidence absent, so no qualified sample exists |
| Model Registry and Research/Shadow selection | Implemented | PostgreSQL Governance |
| Production model qualification | Closed | owner resolution incomplete; always not qualified |
| Market/ETF/Theme/Capital State | Implemented | PostgreSQL State owner; models remain unvalidated |
| StateSeries / Dynamic Pool / Candidate | Implemented | PostgreSQL receipt and CAS authority |
| Free Historical Sample pipeline | Operationally implemented | BaoStock retrospective decisions/outcomes; PostgreSQL `UNQUALIFIED`, `FREE_DATA_EXPLORATORY` only |
| Minute / Signal / PathForecast | Operationally wired for free Research/Shadow | Historical Registry samples may produce exploratory uncalibrated Forecast; no samples fails closed; Production excluded |
| ResearchDailySummary | Implemented | canonical Research/Shadow summary projection |
| Opportunity / Thesis / Portfolio / Risk | Implemented mechanics | human decision support; no actual Position creation |
| Manual Fill / fill-derived Position | Implemented | only observed Fill creates actual Position |
| Research Shadow | Operational loop implemented | `run-day` freeze and `settle-day` T+1 Outcome/Target/Panel/Enrichment/Calibration engineering; prospective proof remains false |
| Prospective attestation | Implemented mechanics | owner-checked, always `prospective_proven=false` |
| Evaluation Dataset / Panel V2 / Factor Extraction | Implemented | immutable engineering evidence |
| Factor catalog / de-dup / ablation / liquidity-capacity | Implemented harness | versioned lineage and provenance; exploratory assumptions are not facts or calibration |
| Calibration | Qualification owner implemented, evidence absent | exact Forecast/Label/Target and FIT/VALIDATION/Locked-OOS bindings are replayed from PostgreSQL; no Formal OOS input exists and every current result remains `calibrated=false` |
| Formal Evaluation / Locked OOS | Family owner writer and two-level consumption Authority implemented, evidence absent | one immutable Hypothesis Family contains all registered Targets and the metric/slice/sensitivity/fold catalog; each raw subject/session/outcome path unlocks once, Target observations consume within that first family, and correction spans the complete family including `NOT_ESTIMABLE` planned folds; revisions or Model/Forecast/Dataset/Protocol substitution cannot make raw OOS pristine; no current qualified PIT/sample observations |
| Entry research / Holding / Exit qualification | Owner writer implemented, evidence absent | replays Locked-OOS Strategy Shadow Entry→Fill→Position→Exit→Outcome, economic/provenance floors and independent approval; no Canonical `ENTER` unlock |
| Strategy Shadow | Operational loop implemented | Entry/Fill/Position/Holding/Exit/Outcome via Continuous CLI; simulated ledger, no real mutation |
| Portfolio Strategy Shadow | Operational engineering complete | Top1/3/5 Equal/Score/Risk, Cash/NAV/exposure/turnover/cost/capacity/drawdown/attribution and A-share constraints; no real mutation |
| Operator surface convergence | Implemented | six installed scripts and six installed CLI module guards; typed Phase C owner freeze, Protocol freeze, Formal Forecast compute and Formal family evaluation are subcommands of existing CLIs with RBAC, audit and idempotency; no generic artifact registrar |
| Holding/Exit validation | Included in owner-resolved C6 gate | current Formal OOS/Calibration/qualified outcomes absent; `holding_exit_validated=false` |
| Prospective Strategy Shadow qualification | Operational engineering complete | post-policy-lock, `LIVE_TRUSTED`/`LIVE_ACQUISITION` sessions only; exact session/outcome/portfolio replay and Provider failure floors; zero current qualifying sessions |
| Production Admission | Persisted owner-resolved blocker | every PIT/OOS/economic/calibration/cost/Entry/Holding/Shadow/auth/operator/Broker floor is re-read; current decision can only remain `BLOCKED` and never implies Broker authority |
| Controlled Execution readiness | Persisted fail-closed gate | checks Broker contract, paper/read-only/reconciliation/preview/risk/kill-switch/human approval/tiny-capital/auth floors; no Order mutation path is enabled |
| Principal/RBAC/Approval/Audit | Engineering complete | append-only PostgreSQL roles, serialized bootstrap/last-Admin invariants, revocation and separation; CLI resources and allowed/denied invocations are audited, non-Admin Shadow/recovery mutations require exact independent approval, and Production mode is rejected before Journal mutation; external authentication is not bound |
| Recovery/DR | Operational engineering complete | expired leases use `resume`; due `PENDING`/Provider retries use canonical `run-day`; Shadow settlement/strategy recovery, replay and isolated PostgreSQL/artifact backup-restore verification are explicit; deployment drill evidence pending |
| Broker integration | Prohibited/currently absent | no live adapter authority |
