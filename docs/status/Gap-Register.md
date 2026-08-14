# Gap Register

> **Status:** CURRENT_STATUS
> **Authority:** Current unresolved engineering and evidence gaps
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-14
> **Code Evidence:** `src/market_regime_alpha`, `src/market_regime_alpha/persistence/postgres/schema.py`, `tests`

## P0 Authority and architecture correctness

| Gap | Current fact | Exit condition |
|---|---|---|
| Qualified Provider evidence | Provider×Contract×Fact writer exists; ten declared BaoStock/Tencent scopes resolve `REJECTED` because source qualification/evidence is absent | independently validated archive/version/revision/availability evidence satisfies the frozen V2 floor for each required Fact Kind |
| Formal PIT evidence | PIT owner/as-of/validation mechanics exist, but the working Phase C schema has zero qualified source/fact/evidence rows | qualified Provider decisions and complete historical facts produce satisfied Formal PIT evidence without inventing `available_at` |
| Qualified Historical Sample / Locked OOS | owner writers, owner-computed Forecast receipts, frozen Hypothesis Family, one-time raw unlock and Target-observation consumption replay exist; upstream Formal PIT/protocol observations are absent | exact qualified sample bindings and the first untouched raw OOS unlock meet frozen family-level statistical/economic floors |
| Calibration / Entry / Holding / Exit evidence | owner writers replay exact partitions and Strategy outcomes; upstream OOS and qualified cost/provenance evidence are absent | frozen calibration and strategy protocols pass without OOS method selection or assumption-as-fact |
| Production evidence floor resolution | persisted owner re-reads all current floors; authentication, Formal evidence, sustained Shadow, cost/capacity and Broker owners remain missing | every floor is independently satisfied and explicitly approved; no automatic promotion |
| Controlled execution evidence | readiness gate exists and is persistently blocked | Broker contract, paper/read-only reconciliation, preview/risk/kill switch, authenticated human approval and separately authorized tiny-capital program exist |

## P1 remaining engineering completion

| Gap | Current fact | Exit condition |
|---|---|---|
| Longitudinal Strategy Path Outcome production | deterministic multi-horizon kernel and PostgreSQL owner exist; the Historical adapter runs both strategies but does not yet schedule 3/5/10/20-session outcome windows | exact historical owner windows automatically materialize version-scoped outcomes with missing/ambiguous paths retained, then replay exact hashes |
| Scheduled strategy feedback closure | Outcome→Attribution→Challenger→Qualification is executable and fail-closed, but invoked explicitly rather than by outcome availability | idempotent scheduled closure consumes only completed exact-version outcomes and exposes the same lineage through runtime inspection |
| Legacy Strategy/Portfolio simulation convergence | canonical Overnight Proposal now gates the older T+1 Shadow Entry and is frozen in its lineage, so Candidate no longer has two live Entry decision paths when a Multi-Strategy cycle exists; legacy Shadow artifact shapes and Portfolio Shadow still serve settlement/qualification consumers | migrate remaining consumers and remove only compatibility shapes whose historical replay and qualification reads have differential proof |
| Strategy risk depth | cross-strategy Top-K equal/score, budgets, name/gross caps and conflict reduction are implemented | empirical exposure/liquidity/cost evidence justifies additional constraints; no optimizer is added merely for completeness |
| Exact-window sustained operation | mechanics pass locally; no sustained real 14:30-14:55 series | consecutive real runs replay with no duplicate Provider calls or fence violations |
| Free-data operator deployment evidence | run/settle/scope/Historical/strategy/portfolio/performance/model/formal-assessment/report/recovery/replay mechanics exist locally | repeated real PostgreSQL day and multi-session archive cycles recover provider, partial-journal and missed-settlement scenarios under the operator runbook |
| Longitudinal historical evidence scale | Phase E3 runs 126 sessions over 29 exact CSI 300 cohorts and consumes Industry/share/corporate-action owners with bounded Decision/Evidence execution; `510300.SH` has no Provider observations, corpus publication peaks at 5.03 GiB, only 50.32% of Panel rows have Decision-time market cap, and costs/fills remain assumptions | acquire a real traceable intraday ETF series without substitution, stream acquisition/publication below the current full-graph peak, extend unchanged experiments to 1--3 years, and resolve execution inputs empirically before an Alpha/economics claim |
| Durable prospective sample | qualification owner excludes pre-policy, Replay and Fixture sessions and currently proves zero real sessions | the frozen policy accumulates enough post-lock trusted-clock/live-origin sessions with exact replay and acceptable incident/drift/Provider failure rates |
| State/Pool/Signal model validation preparation | mechanics and policies exist | frozen protocols and qualified inputs exist without parameter tuning in implementation code |
| External authentication binding | Principal/RBAC/role-separated Approval/Audit owners exist; CLI principal identifiers are not authenticated subjects | a deployed authentication provider binds verified subjects to durable Principals without adding Production permission |
| Backup/restore and observability deployment evidence | local isolated restore verification, preflight, metrics and recovery-audit exist | repeated restore and alert drills meet declared RPO/RTO on the deployed environment |
| Legacy retirement evidence | Canonical imports are clean, but legacy Readers/UI remain | consumer inventory proves which modules can be deleted without breaking replay/migration |

## External/evidence blockers

- qualified formal Provider and complete PIT fact history;
- operational PIT Theme/ETF membership and security-status coverage;
- formal locked OOS evidence and calibrated probabilities;
- sustained Strategy Shadow evidence;
- authenticated operator binding and broker readiness;
- any separately authorized live broker architecture.

These are blockers, not implicit future permissions.
