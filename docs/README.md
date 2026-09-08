# Current documentation

> **Status:** CURRENT_STATUS
> **Code Evidence:** `pyproject.toml`, `src/market_regime_alpha/bootstrap.py`, `tests`

This is the complete current documentation set. Read the first four entries for
development; consult the others for the affected contract. Documents describe
code and constraints, not independent business facts or qualification.

| Document | Responsibility |
|---|---|
| [Architecture](architecture/Canonical-Overall-Design.md) | Actual entry points, composition, call chains and boundaries |
| [Authority Map](architecture/Authority-Map.md) | Concrete owner, writer, reader and invariant |
| [Current State](status/Current-State.md) | Reproducible implementation facts and evidence limits |
| [Roadmap](status/Roadmap.md) | One active plan and remaining architectural debt |
| [Data and Evidence](architecture/Data-and-Evidence-Architecture.md) | Schema, time, Artifact and recovery contracts |
| [Development and Testing](Development.md) | Environment, test contracts, regression and cleanup rules |
| [Runtime Runbook](operations/Runtime-Runbook.md) | Authorized startup, inspection, recovery and backup |

The generated [code and test inventory](architecture/code-inventory.json) is a
read-only index. It lists source symbols/imports/SQL references and each test's
contract; it cannot establish that a path is deployed or a test is sufficient.

Normative authority order: latest explicit user request, `AGENTS.md` invariants,
then this current set. Implementation fact authority order: executable code,
schema and real consumers, executed tests, reproducible evidence, then prose.

[Historical archive](archive/README.md) is opt-in, non-normative provenance.
Its frozen claims, instructions and relative links belong to their original
revision. Do not use archived status, plans or passing counts as current facts.
