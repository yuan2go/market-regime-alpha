# Gap Register

> **Status:** CURRENT_STATUS
> **Authority:** Current unresolved engineering and evidence gaps
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-11
> **Code Evidence:** `src/market_regime_alpha`, `src/market_regime_alpha/persistence/postgres/schema.py`, `tests`

## P0 Authority and architecture correctness

| Gap | Current fact | Exit condition |
|---|---|---|
| Qualified Provider evidence | Provider×Contract×Fact writer exists; ten declared BaoStock/Tencent scopes resolve `REJECTED` because source qualification/evidence is absent | independently validated archive/version/revision/availability evidence satisfies the frozen V2 floor for each required Fact Kind |
| Formal PIT evidence | PIT owner/as-of/validation mechanics exist, but the working Phase C schema has zero qualified source/fact/evidence rows | qualified Provider decisions and complete historical facts produce satisfied Formal PIT evidence without inventing `available_at` |
| Qualified Historical Sample / Locked OOS | owner writers, protocol component resolution and durable underlying-evidence consumption replay exist; upstream Formal PIT/protocol observations are absent | exact qualified sample bindings and untouched Locked OOS folds meet frozen statistical/economic floors |
| Calibration / Entry / Holding / Exit evidence | owner writers replay exact partitions and Strategy outcomes; upstream OOS and qualified cost/provenance evidence are absent | frozen calibration and strategy protocols pass without OOS method selection or assumption-as-fact |
| Production evidence floor resolution | persisted owner re-reads all current floors; authentication, Formal evidence, sustained Shadow, cost/capacity and Broker owners remain missing | every floor is independently satisfied and explicitly approved; no automatic promotion |
| Controlled execution evidence | readiness gate exists and is persistently blocked | Broker contract, paper/read-only reconciliation, preview/risk/kill switch, authenticated human approval and separately authorized tiny-capital program exist |

## P1 remaining engineering completion

| Gap | Current fact | Exit condition |
|---|---|---|
| Exact-window sustained operation | mechanics pass locally; no sustained real 14:30-14:55 series | consecutive real runs replay with no duplicate Provider calls or fence violations |
| Free-data operator deployment evidence | run/settle/strategy/portfolio/report/recovery-audit/replay mechanics exist locally | repeated real PostgreSQL day cycles recover provider, partial-journal and missed-settlement scenarios under an operator runbook |
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
