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
| Retained execution/account | Decision/account and formal governance commands remain installed; separate research CLI dispatch is retired | No full Runtime/CLI cutover or broker admission |

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

## Consumer verification at the frozen implementation

Baseline: `50c81f107dae0520f47896dfed8c03d2d9a2a554`.
Implementation: `56dce2f312e2b97c5cd1618d300a25178466908b`.
Source tree: `c4f7d1e9c4886962a2d93146850d5ee660316f06`.
Tests tree: `10cb64cb092ece93df5082924103c9db426a0755`.
Later status-only commits do not change those implementation identities.

| Check / scope | Executed evidence |
|---|---|
| Installed commands / executable file-API roots | 7 → 4 / 68 → 55; every surviving root has a disposition |
| Roots reaching retained persistence / direct source importers | 37 → 24 / 113 → 105; current `mra` research closure has zero such dependencies |
| Retained PostgreSQL, account, CLI and formal governance | 677 passed at the first frozen consumer revision; unchanged owner/schema/test scopes are reused explicitly |
| Canonical composition, schema, replay and tooling | 192 passed and 2 architecture failures at the intermediate revision; both failures corrected without relaxing the forbidden dependency contract |
| Final affected architecture/history/recovery scope | 58 passed in 119 seconds at the implementation above, including populated Shadow report/replay |
| Repository test collection | 4,154 collected; full execution NOT_RUN under risk-directed scope |
| Static, environment and documentation | Frozen sync, Ruff, mypy (636 configured files plus 4 explicit files), docs, hygiene and diff checks PASS |
| Build and isolated installed wheel | PASS: four commands import/help, removed modules absent, all 113 SQL resources match source bytes |
| Historical resources | 19 moved tools retain bytes; all released SQL, dependency lock and archived evidence unchanged |
| Operational / external history | NOT_RUN: no service, operational database or external completed campaign modified/requalified |

Source-bound verification is recorded in the external incremental evidence
bundle `canonical-consumer-convergence-20260908.tar.gz`, including raw failures,
command/exit-code logs, temporary database identities, consumer matrices,
file-level reuse assessment and built artifacts. Its `verification.json` has
SHA256 `1af0b50072d40bb3ed4be0851b39f09cb25f4a2ca73f3bbde91337f9af25ed8f`.
This is engineering consumer-convergence evidence, not research validity or
operational admission. The implementation's convergence gate is PASS.

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
