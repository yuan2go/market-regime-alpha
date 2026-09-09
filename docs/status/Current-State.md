# Current implementation state

> **Status:** CURRENT_STATUS
> **Code Evidence:** `pyproject.toml`, `src/market_regime_alpha/bootstrap.py`, `src/market_regime_alpha/infrastructure/postgres/schema.py`, `tests/contracts`

This page describes checked-out implementation, not an operational database or
research qualification. Verification results must match the affected implementation and consumer
scope; earlier hygiene evidence remains in the archive index.

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
| Retained execution/account | Decision/account and formal governance commands remain installed; separate research CLI dispatch is retired | No account Runtime migration or broker admission |

No live service, operational evidence database, Provider capture or research
result is changed or requalified by repository maintenance. Current operational
facts must be obtained through the runbook's exact-scope status/health/replay
commands under the relevant authorization.

## Consumer convergence

Four commands are installed: `mra`, `decision-system`, `model-governance` and
`pit-authority`. The canonical research import closure does not depend on
`research`, `platform`, `application/historical_corpus` or `persistence`.
The generated inventory includes the complete executable consumer matrix and
SQL-adapter closures. Historical tools are outside current execution; exact
readers and the observed-account/governance exceptions remain explicit.

No released SQL bytes, schema membership, research formula, Model/Outcome
identity or operational database is changed. Source retirement does not prove
live deployment or authorize account Runtime cutover.

## Research Runtime cutover verification

Baseline: `a8cf743dc504f9574f490a64e2dc96e68025371c`.
Implementation: `4b65c14cc445034b340c83e34aa9277c7e67151f`.
Source tree: `9a45fb76c44b104a89929fa3a4adb813a053b89e`.
Tests tree: `a7ca20db9e4b4fd5f0acee4ff80a5264106b2377`.
The final delivery commit changes only current status/runbook prose; the source,
tests, SQL, dependencies and executable templates match this implementation.

New current research enters `mra` through `bootstrap_application`. The remaining
all-day runner and FreeData service wiring are removed. Account journal values,
observed-Fill commands, formal Model/PIT governance and explicit historical
inspection/verification retain their distinct owners.

Installed execution requires a verified source/wheel/package/dependency receipt
and exact operation profile. Canonical non-Attempt owner commands and retained
write connections participate in reservation admission. Runtime inspection uses
a database-enforced read-only UoW. Original daily plans remain recoverable after
installation or Model-use changes; completed settlement/report recovery does not
reacquire Market inputs or repeat completed Evaluation.

| Check / scope | Executed evidence at this implementation |
|---|---|
| Canonical contracts, architecture, repository scripts | 1,229 passed in 1,075 seconds; includes Runtime/fence, daily normal/missing/crash, Outcome/Evaluation, schema/upgrade and historical decoder contracts |
| Retained persistence, CLI, account, execution and formal governance | 664 passed in 579 seconds; rerun after the shared connection change |
| Independent installed wheel | 23 checks passed; four installed commands, verified profile generation, old profile/new implementation refusal, wrong scope/extra installed file refusal |
| Preserved vertical slice and independent restore | 32-member prediction → mature Outcome → Evaluation → report/replay; new restore DB/root, complete table/Artifact reconciliation and repeated installed CLI replay match with zero business writes |
| Query scope | 11 actual EXPLAIN ANALYZE/BUFFERS JSON plans; replay/health/worklist 0.10 seconds on the 32-member fixture; not a production-load benchmark |
| Static/build/docs | Frozen sync, Ruff, mypy (635 configured files), inventory/hygiene, links and diff checks pass; isolated build/install pass using cached offline dependencies after an online TLS failure |
| Schema/dependencies | All 113 SQL resources and dependency lock unchanged; 194 canonical tables, no new migration |
| Repository collection / full execution | 4,138 collected; full repository execution NOT_RUN under the explicitly bounded regression scope |
| Operational mutation / real prospective proof | NOT_AUTHORIZED / NOT_RUN; no actual service, LaunchAgent, writer or operational database changed |

The source-bound incremental bundle `canonical-runtime-cutover-20260909.tar.gz`
contains `verification.json`, raw failures and repairs, exact commands/exit codes,
CLI/owner inventory, wheel and installed identities, disposable DB/Artifact
identities, backup bytes, restore/replay receipts and query plans. The engineering
research Runtime cutover gate passes. This does not establish live activation,
sustained collection, formal qualification or research validity.

Previous consumer-convergence evidence remains in
`canonical-consumer-convergence-20260908.tar.gz`; its source-bound verification
SHA256 is `1af0b50072d40bb3ed4be0851b39f09cb25f4a2ca73f3bbde91337f9af25ed8f`.
Prior failures and released SQL retain their original bytes and meaning.

## Prior repository hygiene evidence

The source-bound cleanup completed default and explicit historical PostgreSQL
regression, static checks, archive integrity and independent installed-schema/CLI
verification. Exact revisions, counts, failures and build identities are retained
in the [archive index](../archive/README.md). Future changes must run their own
affected checks; this record does not establish current operational health.

## Evidence limits

Code presence, canonical wiring, executed tests, runtime observation, research
qualification and Production admission remain distinct. Historical passing
counts cannot establish this revision's PASS. Unproved formal Provider/PIT/OOS,
model value, sustained service and Alpha are not promoted by this cleanup.
Production admission remains closed. New business work follows the
[Roadmap](Roadmap.md), not archived task instructions.
