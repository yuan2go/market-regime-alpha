# Current implementation state

> **Status:** CURRENT_STATUS
> **Code Evidence:** `pyproject.toml`, `src/market_regime_alpha/bootstrap.py`, `src/market_regime_alpha/infrastructure/postgres/schema.py`, `tests/contracts`

This page describes checked-out implementation, not an operational database or
research qualification. Exact local verification results belong to the hygiene
execution record reached through the archive index.

## Reproducible schema facts

<!-- schema-facts:start -->
Epoch: `MRA_REFOUNDATION_1`.
Research table count: **194**.
<!-- schema-facts:end -->

These values are checked against the executable SchemaManager contract.
The schema inventory records SQL checksums; fresh PostgreSQL bootstrap/verify
checks the complete catalog. There is no hardcoded index/constraint count or
mixed-version operational checksum table here.

## Current execution

| Surface | Implemented/wired fact | Limit |
|---|---|---|
| Generic Backtest | Specification, Runtime action execution, owner reconciliation, Model lineage, report and comparison are composed by `bootstrap_application` | A declared/finished Runtime is not sufficient without complete owner replay |
| Prospective collection | Guarded serve, DB due query, atomic writer admission, lease/fence, overdue and planning-gap recovery | Current service/due/success cannot be inferred from source, old status or a running process |
| Daily research | Post-close DataReady; exact experimental Model use; independent forecasts; frozen publication; pending Outcome/evaluation and delivery recovery | Availability, actual publication time and real maturation are separately observed facts |
| Economics | Typed deterministic fully funded independent episodes; root/child field reconciliation and full-path slicing | No continuous-account/tradability/Alpha claim; historical formula meanings remain unchanged |
| Evidence operations | Exact database/Artifact identity, backup, integrity and restore/replay operations | A successful copy is a separate scope; missing original evidence remains missing |
| Retained execution/account | Legacy CLIs and PostgreSQL owners remain installed and tested | No full Runtime/CLI cutover or broker admission |

No live service, operational evidence database, Provider capture or research
result is changed or requalified by repository hygiene. Current operational
facts must be obtained through the runbook's exact-scope status/health/replay
commands under the relevant authorization.

## Evidence limits

Code presence, canonical wiring, executed tests, runtime observation, research
qualification and Production admission remain distinct. Historical passing
counts cannot establish this revision's PASS. Unproved formal Provider/PIT/OOS,
model value, sustained service and Alpha are not promoted by this cleanup.
Production admission remains closed. New business work follows the
[Roadmap](Roadmap.md), not archived task instructions.
