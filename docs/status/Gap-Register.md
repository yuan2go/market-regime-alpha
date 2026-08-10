# Gap Register

> **Status:** CURRENT_STATUS
> **Authority:** Current unresolved engineering and evidence gaps
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-11
> **Code Evidence:** `src/market_regime_alpha`, `src/market_regime_alpha/persistence/postgres/schema.py`, `tests`

## P0 Authority and architecture correctness

| Gap | Current fact | Exit condition |
|---|---|---|
| Owner-resolved Historical Sample qualification transitions | free-data writer and Registry Reader persist/consume `UNQUALIFIED` only; migration 046 remains closed | a separately authorized narrow writer reloads qualified PIT/OOS/Governance owners and binds exact lineage/time |
| Owner-resolved Formal OOS writer | metric harness is engineering-only | PostgreSQL writer reloads Formal PIT, frozen protocol, Panel/Dataset and persists immutable Formal OOS evidence |
| Production evidence floor resolution | Model Governance forces Production not-qualified; engineering RBAC owner exists but authentication, Formal evidence and Broker owners do not | every required kind has an explicit owner Repository and no generic resolver |
| Production Admission Authority | projection is always blocked | authenticated, append-only final writer exists under separate approval and does not imply broker execution |

## P1 remaining engineering completion

| Gap | Current fact | Exit condition |
|---|---|---|
| Exact-window sustained operation | mechanics pass locally; no sustained real 14:30-14:55 series | consecutive real runs replay with no duplicate Provider calls or fence violations |
| Free-data operator deployment evidence | run/settle/strategy/portfolio/report/recovery-audit/replay mechanics exist locally | repeated real PostgreSQL day cycles recover provider, partial-journal and missed-settlement scenarios under an operator runbook |
| Durable prospective sample | attestation mechanism exists but proves zero real sessions | nonzero trusted-clock/live-origin outcomes satisfy frozen-before-available semantics |
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
