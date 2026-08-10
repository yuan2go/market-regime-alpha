# Gap Register

> **Status:** CURRENT_STATUS
> **Authority:** Current unresolved engineering and evidence gaps
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-10
> **Code Evidence:** Current code, schema and tests

## P0 Authority and architecture correctness

| Gap | Current fact | Exit condition |
|---|---|---|
| Owner-resolved Historical Sample transitions | migration 046 allows `UNQUALIFIED` only | a narrow writer reloads PIT/OOS/Governance owners and binds exact sample lineage/time |
| Owner-resolved Formal OOS writer | metric harness is engineering-only | PostgreSQL writer reloads Formal PIT, frozen protocol, Panel/Dataset and persists immutable Formal OOS evidence |
| Production evidence floor resolution | Model Governance forces Production not-qualified | every required kind has an explicit owner Repository; operator/RBAC/broker owners exist; no generic resolver |
| Production Admission Authority | projection is always blocked | authenticated, append-only final writer exists under separate approval and does not imply broker execution |
| Internal executable inventory | 18 CLI modules have main guards but 12 scripts are installed | classify each internal main as operator tool, research harness or remove it |

## P1 remaining engineering completion

| Gap | Current fact | Exit condition |
|---|---|---|
| Exact-window sustained operation | mechanics pass locally; no sustained real 14:30-14:55 series | consecutive real runs replay with no duplicate Provider calls or fence violations |
| Durable prospective sample | attestation mechanism exists but proves zero real sessions | nonzero trusted-clock/live-origin outcomes satisfy frozen-before-available semantics |
| State/Pool/Signal model validation preparation | mechanics and policies exist | frozen protocols and qualified inputs exist without parameter tuning in implementation code |
| Authentication and RBAC | absent | authenticated principals and role-separated approvals are durable and audited |
| Backup/restore and observability operations | partial local mechanics | repeated restore and alert drills meet declared RPO/RTO on the deployed environment |
| Legacy retirement evidence | Canonical imports are clean, but legacy Readers/UI remain | consumer inventory proves which modules can be deleted without breaking replay/migration |

## External/evidence blockers

- qualified formal Provider and complete PIT fact history;
- operational PIT Theme/ETF membership and security-status coverage;
- formal locked OOS evidence and calibrated probabilities;
- sustained Strategy Shadow evidence;
- authenticated operator approval, RBAC and broker readiness;
- any separately authorized live broker architecture.

These are blockers, not implicit future permissions.
